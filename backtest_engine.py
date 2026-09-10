"""
Historical Multi-Strategy Backtesting Engine for XAUUSD (Gold) - Elite 6 Pillars Edition

Design goal: ZERO logic duplication. This engine does not reimplement any strategy rule,
AI-gating threshold, SL/TP formula, or lot-sizing rule. Instead it builds a paper-trading
"connector" that implements the exact same interface as mt5_connector.MT5Connector
(get_rates, get_market_info, get_account_info, get_open_positions, open_order,
modify_position, close_position) and runs the REAL bot_engine.GoldScalpingBot against it,
calling its real run_iteration() every simulated M5 bar close - the identical entry point
main.py's scheduler calls in production. This guarantees the backtest exercises the exact
same code path as live trading: MarketRegimeScorer quality filter, RealTimeStrategyOptimizer
dynamic R:R / AI throttle, execute_buy/execute_sell SL-TP construction, calculate_lot_size
risk sizing, and manage_open_positions trailing/BE-lock - for all 6 active pillars
(PULLBACK_DR_EKK, RTM_M4_CONSERVATIVE, RTM_M6_ELITE_GROWTH, SMC_X_STO_H1, KC_LIQUIDITY_DOMINANCE,
CONFLUENCE_SQUEEZE_M15).

Two data sources are supported:
  1. CSV files exported from MT5 (History Center "Export" button, or chart right-click ->
     "Save As" CSV). Works with the standard MT5 tab-separated export format
     (<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>) as well as generic
     Date/Time/Open/High/Low/Close[/Volume] CSVs. No network access required - this is the
     path to use from a sandboxed / network-restricted environment.
  2. Live MT5 terminal (MetaTrader5 python package + a running, logged-in terminal) via
     load_from_mt5() - unchanged in spirit from the original version of this file. This is
     the path to use on the VPS / a machine with the real Exness MT5 terminal installed,
     where genuine broker-feed historical data is available.

Known simplifications (documented, not hidden):
  - Fixed spread assumption (spread_points, default 20.0) rather than a real historical
    spread series - MT5 exports rarely include reliable historical spread anyway.
  - Same-bar SL+TP conflict resolves to SL first (pessimistic/conservative convention).
  - Account equity for the daily target/max-loss guard tracks REALIZED balance only (no
    intra-bar floating P&L mark-to-market of open positions).
  - RealTimeStrategyOptimizer / MarketRegimeScorer / ExitBenchmarkTracker are instantiated
    with isolated, throwaway state files (never the live strategy_learning_data.json /
    regime_scorer_stats.json / exit_benchmark_history.json) so a backtest run can never
    pollute production learning data.
  - get_current_session() / check_new_day() are overridden to use the SIMULATED bar clock
    instead of the real wall clock (production reads datetime.now()), and time.time() is
    monkeypatched for the duration of the run so the RTM pending-setup expiry (45 min) and
    anti-clustering cooldown (15 min) - both wall-clock based in production - are evaluated
    against simulated market time instead of real elapsed process time.
"""

import os
import sys
import json
import copy
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

import bot_engine as bot_engine_module
from bot_engine import GoldScalpingBot, STRATEGY_MAGIC_MAP

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BacktestEngine")

_real_time_time = bot_engine_module.time.time


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ohlc_csv(path: str) -> pd.DataFrame:
    """
    Load an OHLC CSV into the normalized schema (time, open, high, low, close, tick_volume)
    that bot_engine.py's strategy checks expect. Accepts:
      - MT5 History Center export: tab-separated, headers like <DATE> <TIME> <OPEN> <HIGH>
        <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>, date as YYYY.MM.DD.
      - Generic CSV with Date/Time or DateTime + Open/High/Low/Close[/Volume] columns.
    """
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [str(c).strip().strip("<>").lower() for c in df.columns]

    rename_map = {
        "tickvol": "tick_volume", "vol": "tick_volume", "volume": "tick_volume",
        "o": "open", "h": "high", "l": "low", "c": "close",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "time" not in df.columns:
        if "date" in df.columns and "time" in df.columns:
            pass
        if "datetime" in df.columns:
            df["time"] = pd.to_datetime(df["datetime"])
        elif "date" in df.columns and "hour" in df.columns:
            df["time"] = pd.to_datetime(df["date"] + " " + df["hour"].astype(str), errors="coerce")
        elif "date" in df.columns:
            # MT5 export always has separate <DATE> (YYYY.MM.DD) and <TIME> (HH:MM[:SS]) columns
            time_col = df["time"] if "time" in df.columns else "00:00:00"
            df["time"] = pd.to_datetime(
                df["date"].astype(str).str.replace(".", "-", regex=False) + " " + df.get("time", "00:00:00").astype(str),
                errors="coerce"
            )
        else:
            raise ValueError(f"Could not find a date/time column in {path}. Columns found: {list(df.columns)}")
    else:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV {path} is missing required OHLC column(s): {missing}. Columns found: {list(df.columns)}")

    if "tick_volume" not in df.columns:
        df["tick_volume"] = 100

    df = df[["time", "open", "high", "low", "close", "tick_volume"]].dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    for c in ["open", "high", "low", "close", "tick_volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return df


def resample_ohlc(df_m5: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Derive a higher timeframe (e.g. '15min', '1h') from M5 bars by resampling."""
    idx = df_m5.set_index("time")
    agg = idx.resample(rule, label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum"
    })
    agg = agg.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return agg


# ---------------------------------------------------------------------------
# Paper-trading connector (implements the MT5Connector interface)
# ---------------------------------------------------------------------------

class BacktestConnector:
    """Paper-trading connector backed by preloaded historical DataFrames + a virtual account.
    Implements the same method signatures as mt5_connector.MT5Connector so bot_engine's real
    GoldScalpingBot can be driven against it unmodified."""

    def __init__(self, symbol: str, m5_df: pd.DataFrame, m15_df: pd.DataFrame, h1_df: pd.DataFrame,
                 initial_balance: float = 3000.0, spread_points: float = 20.0):
        self.symbol = symbol
        self.m5_df = m5_df.reset_index(drop=True)
        self.m15_df = m15_df.reset_index(drop=True)
        self.h1_df = h1_df.reset_index(drop=True)
        self.spread_points = spread_points

        self.balance = initial_balance
        self.equity = initial_balance

        self.now_idx = 0
        self.current_time: Optional[pd.Timestamp] = None
        self.current_open: Optional[float] = None

        self.positions: List[dict] = []
        self.closed_trades: List[dict] = []
        self._next_ticket = 100000

        self.equity_curve: List[Tuple[pd.Timestamp, float]] = []

    # --- simulated clock ---
    def advance_to(self, i: int):
        self.now_idx = i
        row = self.m5_df.iloc[i]
        self.current_time = row["time"]
        self.current_open = float(row["open"])

    # --- MT5Connector-compatible interface ---
    def get_rates(self, symbol: str, timeframe: str = "M5", count: int = 100) -> pd.DataFrame:
        tf = timeframe.upper()
        src = {"M5": self.m5_df, "M15": self.m15_df, "H1": self.h1_df}.get(tf, self.m5_df)
        if self.current_time is None or src.empty:
            return pd.DataFrame()
        sliced = src[src["time"] <= self.current_time]
        if sliced.empty:
            return pd.DataFrame()
        return sliced.tail(count).reset_index(drop=True)

    def get_market_info(self, symbol: str) -> dict:
        half_spread = (self.spread_points * 0.01) / 2.0
        bid = self.current_open - half_spread
        ask = self.current_open + half_spread
        return {
            "symbol": symbol, "bid": round(bid, 3), "ask": round(ask, 3),
            "spread": self.spread_points, "point": 0.01, "digits": 2, "trade_allowed": True
        }

    def get_account_info(self) -> dict:
        return {
            "login": 0, "server": "Backtest", "currency": "USD",
            "balance": round(self.balance, 2), "equity": round(self.equity, 2),
            "margin": 0.0, "free_margin": round(self.balance, 2),
            "margin_level": 999.0, "profit": 0.0,
            "mode": "Backtest", "connected": True
        }

    def get_open_positions(self, symbol: Optional[str] = None) -> List[dict]:
        return [dict(p) for p in self.positions if symbol is None or p["symbol"] == symbol]

    def open_order(self, symbol: str, order_type: str, volume: float, sl: float, tp: float,
                    magic: int, comment: str = "") -> dict:
        m_info = self.get_market_info(symbol)
        price = m_info["ask"] if order_type.upper() == "BUY" else m_info["bid"]
        ticket = self._next_ticket
        self._next_ticket += 1
        self.positions.append({
            "ticket": ticket, "symbol": symbol, "type": order_type.upper(), "volume": float(volume),
            "price_open": float(price), "sl": float(sl or 0.0), "tp": float(tp or 0.0),
            "price_current": float(price), "profit": 0.0, "swap": 0.0, "comment": comment,
            "magic": int(magic), "open_time": self.current_time
        })
        return {"status": True, "ticket": ticket, "price": price}

    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        for p in self.positions:
            if p["ticket"] == ticket:
                p["sl"] = float(sl or 0.0)
                p["tp"] = float(tp or 0.0)
                return True
        return False

    def close_position(self, ticket: int) -> bool:
        for p in list(self.positions):
            if p["ticket"] == ticket:
                self._close(p, self.current_open, "Manual Close")
                return True
        return False

    def close_all_positions(self, magic: Optional[int] = None) -> int:
        closed = 0
        for p in list(self.positions):
            if magic is None or p["magic"] == magic:
                self._close(p, self.current_open, "Close All")
                closed += 1
        return closed

    # --- exit simulation (called by the walk-forward driver, not by bot_engine itself) ---
    def process_bar_exits(self, bar) -> None:
        """Check every currently open position against this M5 bar's high/low for a TP/SL fill.
        Same-bar SL+TP conflicts resolve to SL first (conservative convention)."""
        high, low = float(bar["high"]), float(bar["low"])
        for p in list(self.positions):
            sl, tp = p["sl"], p["tp"]
            hit_sl = hit_tp = False
            if p["type"] == "BUY":
                if sl > 0 and low <= sl:
                    hit_sl = True
                if tp > 0 and high >= tp:
                    hit_tp = True
            else:
                if sl > 0 and high >= sl:
                    hit_sl = True
                if tp > 0 and low <= tp:
                    hit_tp = True
            if hit_sl:
                self._close(p, sl, "SL")
            elif hit_tp:
                self._close(p, tp, "TP")

    def _close(self, p: dict, exit_price: float, reason: str) -> None:
        direction = 1 if p["type"] == "BUY" else -1
        # $100 per lot per $1.00 move - matches bot_engine.calculate_lot_size's own
        # (risk_money / (sl_dist * 100.0)) convention, so sizing and P&L stay self-consistent.
        pnl = direction * (exit_price - p["price_open"]) * p["volume"] * 100.0
        self.balance += pnl
        self.equity = self.balance
        self.closed_trades.append({
            "ticket": p["ticket"], "magic": p["magic"], "symbol": p["symbol"], "type": p["type"],
            "volume": p["volume"], "price_open": p["price_open"], "price_close": exit_price,
            "open_time": p.get("open_time"), "close_time": self.current_time,
            "profit": round(pnl, 2), "exit_reason": reason, "comment": p.get("comment", "")
        })
        self.equity_curve.append((self.current_time, self.balance))
        if p in self.positions:
            self.positions.remove(p)


# ---------------------------------------------------------------------------
# Bot subclass: redirect wall-clock-dependent methods to the simulated clock
# ---------------------------------------------------------------------------

class BacktestBotEngine(GoldScalpingBot):
    """Identical to GoldScalpingBot in every respect except that check_new_day() and
    get_current_session() read the connector's simulated bar clock instead of the real
    datetime.now() - everything else (all signal detection, AI gating, order execution,
    lot sizing, trailing) is inherited unmodified."""

    def check_new_day(self):
        sim_now = getattr(self.connector, "current_time", None)
        today = sim_now.date() if sim_now is not None else datetime.now().date()
        acc = self.connector.get_account_info()
        equity = acc.get("equity", 10000.0)
        balance = acc.get("balance", 10000.0)

        if self.current_day != today or self.day_starting_equity == 0.0:
            self.current_day = today
            self.day_starting_equity = balance
            self.daily_target_reached = False
            self.daily_max_loss_reached = False
            self.pause_until_time = 0

        if self.day_starting_equity > 0 and (balance > (self.day_starting_equity * 1.20) or balance < (self.day_starting_equity * 0.80)):
            self.day_starting_equity = balance
            self.daily_target_reached = False
            self.daily_max_loss_reached = False

        if self.day_starting_equity > 0:
            strat_cfg = self.config.get("strategy", {})
            daily_target_pct = strat_cfg.get("daily_target_percent", 10.0)
            daily_max_loss_pct = strat_cfg.get("daily_max_loss_percent", 5.0)
            pnl_pct = ((equity - self.day_starting_equity) / self.day_starting_equity) * 100.0

            if pnl_pct >= daily_target_pct and not self.daily_target_reached:
                self.daily_target_reached = True
            elif pnl_pct <= -daily_max_loss_pct and not self.daily_max_loss_reached:
                self.daily_max_loss_reached = True

    def get_current_session(self) -> str:
        sim_now = getattr(self.connector, "current_time", None)
        if sim_now is None:
            return super().get_current_session()
        now_hour = sim_now.hour % 24
        if 7 <= now_hour < 14:
            return "ASIAN SESSION"
        elif 14 <= now_hour < 19:
            return "LONDON SESSION"
        elif now_hour >= 19 or now_hour < 4:
            return "NEW YORK SESSION"
        else:
            return "LATE NIGHT ROLLOVER"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class HistoricalBacktester:
    def __init__(self, symbol: str = "XAUUSDc", initial_balance: float = 3000.0,
                 spread_points: float = 20.0, config: Optional[dict] = None,
                 scratch_dir: Optional[str] = None):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.spread_points = spread_points
        self.scratch_dir = scratch_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".backtest_scratch")
        os.makedirs(self.scratch_dir, exist_ok=True)

        if config is not None:
            self.config = copy.deepcopy(config)
        else:
            self.config = self._load_repo_config()
        self.config.setdefault("mt5", {})["symbol"] = symbol

        self.m5_df: Optional[pd.DataFrame] = None
        self.m15_df: Optional[pd.DataFrame] = None
        self.h1_df: Optional[pd.DataFrame] = None

        self.connector: Optional[BacktestConnector] = None
        self.bot: Optional[BacktestBotEngine] = None

    @staticmethod
    def _load_repo_config() -> dict:
        """Build a config dict shaped exactly like account_manager.py's bot_config
        (mt5 + merged strategy settings) so backtested risk/session/spread parameters match
        production 1:1: global top-level config['strategy'] merged with the live BOT
        account's own strategy overrides, same precedence account_manager.py uses."""
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                full_cfg = json.load(f)
            bot_acc = next((a for a in full_cfg.get("accounts", []) if a.get("type") == "BOT"), None)
            strategy_cfg = dict(full_cfg.get("strategy", {}))
            if bot_acc and isinstance(bot_acc.get("strategy"), dict):
                strategy_cfg.update(bot_acc["strategy"])
            return {
                "mt5": {
                    "symbol": (bot_acc or {}).get("symbol", "XAUUSDc"),
                    "magic_number": (bot_acc or {}).get("magic_number", 555888),
                },
                "strategy": strategy_cfg,
            }
        except Exception as e:
            logger.warning(f"Could not load config.json ({e}); using minimal defaults.")
            return {"mt5": {"symbol": "XAUUSDc", "magic_number": 555888}, "strategy": {"strategy_mode": "ALL"}}

    # --- data loading ---
    def load_from_csv(self, m5_path: str, m15_path: Optional[str] = None, h1_path: Optional[str] = None):
        self.m5_df = load_ohlc_csv(m5_path)
        self.m15_df = load_ohlc_csv(m15_path) if m15_path else resample_ohlc(self.m5_df, "15min")
        self.h1_df = load_ohlc_csv(h1_path) if h1_path else resample_ohlc(self.m5_df, "1h")
        logger.info(f"Loaded {len(self.m5_df)} M5 / {len(self.m15_df)} M15 / {len(self.h1_df)} H1 bars from CSV.")
        return self

    def load_from_mt5(self, bars_count: int = 20000):
        """Live MT5 terminal path - requires the MetaTrader5 python package AND a running,
        logged-in MT5 terminal (VPS / local Windows machine only - not available in a cloud
        sandbox). Antigravity should call this when running the backtest on the VPS."""
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 python package not available in this environment.")
        if not mt5.terminal_info():
            if not mt5.initialize():
                raise RuntimeError("Failed to initialize MetaTrader 5.")

        def _fetch(tf_const, count):
            rates = mt5.copy_rates_from_pos(self.symbol, tf_const, 0, count)
            if rates is None or len(rates) == 0:
                alt_sym = "XAUUSD" if "c" in self.symbol else "XAUUSDc"
                rates = mt5.copy_rates_from_pos(alt_sym, tf_const, 0, count)
                if rates is None or len(rates) == 0:
                    raise RuntimeError(f"Could not retrieve rates for {self.symbol}")
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            return df[["time", "open", "high", "low", "close", "tick_volume"]]

        self.m5_df = _fetch(mt5.TIMEFRAME_M5, bars_count)
        self.m15_df = _fetch(mt5.TIMEFRAME_M15, bars_count // 3 + 100)
        self.h1_df = _fetch(mt5.TIMEFRAME_H1, bars_count // 12 + 100)
        logger.info(f"Loaded {len(self.m5_df)} M5 / {len(self.m15_df)} M15 / {len(self.h1_df)} H1 bars from live MT5.")
        return self

    # --- run ---
    def run(self, warmup_bars: int = 800, progress_every: int = 2000) -> dict:
        if self.m5_df is None or len(self.m5_df) < warmup_bars + 10:
            raise RuntimeError(f"Not enough M5 data loaded (need > {warmup_bars + 10} bars, have {0 if self.m5_df is None else len(self.m5_df)}).")

        self.connector = BacktestConnector(
            self.symbol, self.m5_df, self.m15_df, self.h1_df,
            initial_balance=self.initial_balance, spread_points=self.spread_points
        )
        self.bot = BacktestBotEngine(self.connector, self.config)
        self.bot.is_running = True
        self.bot.current_day = None
        self.bot.day_starting_equity = 0.0

        # Isolate optimizer/scorer/benchmark-tracker state from the live production files,
        # and no-op their per-trade disk writes during the hot loop for speed (persisted once
        # at the end via _flush_learning_state()).
        from strategy_optimizer import RealTimeStrategyOptimizer
        from regime_liquidity_scorer import MarketRegimeScorer
        from exit_benchmark_tracker import ExitBenchmarkTracker
        self.bot.optimizer = RealTimeStrategyOptimizer(data_file_path=os.path.join(self.scratch_dir, "bt_strategy_learning.json"))
        self.bot.scorer = MarketRegimeScorer(data_file_path=os.path.join(self.scratch_dir, "bt_regime_scorer_stats.json"))
        self.bot.benchmark_tracker = ExitBenchmarkTracker(data_file_path=os.path.join(self.scratch_dir, "bt_exit_benchmark_history.json"))
        self._optimizer_save_state = self.bot.optimizer.save_state
        self._scorer_save_state = self.bot.scorer.save_state
        self._benchmark_save_state = self.bot.benchmark_tracker.save_state
        self.bot.optimizer.save_state = lambda: None
        self.bot.scorer.save_state = lambda: None
        self.bot.benchmark_tracker.save_state = lambda: None

        real_time_time = bot_engine_module.time.time
        try:
            bot_engine_module.time.time = lambda: self.connector.current_time.timestamp()
            n = len(self.m5_df)
            for i in range(warmup_bars, n):
                self.connector.advance_to(i)
                bar_i = self.m5_df.iloc[i]
                self.connector.process_bar_exits(bar_i)
                try:
                    self.bot.run_iteration()
                except Exception as e:
                    logger.error(f"run_iteration() error at bar {i} ({bar_i['time']}): {e}")
                if progress_every and (i - warmup_bars) % progress_every == 0:
                    logger.info(f"...bar {i}/{n} ({bar_i['time']}) balance=${self.connector.balance:.2f}")

            # Close anything still open at the end of the dataset at the last bar's close
            last_close = float(self.m5_df.iloc[-1]["close"])
            self.connector.current_time = self.m5_df.iloc[-1]["time"]
            for p in list(self.connector.positions):
                self.connector._close(p, last_close, "End of Backtest")
        finally:
            bot_engine_module.time.time = real_time_time
            self.bot.optimizer.save_state = self._optimizer_save_state
            self.bot.scorer.save_state = self._scorer_save_state
            self.bot.benchmark_tracker.save_state = self._benchmark_save_state
            try:
                self.bot.optimizer.save_state()
                self.bot.scorer.save_state()
                self.bot.benchmark_tracker.save_state()
            except Exception:
                pass

        return self.compute_results()

    # --- results ---
    def compute_results(self) -> dict:
        trades = self.connector.closed_trades
        strat_by_magic = {}
        for strat_id, m_info in STRATEGY_MAGIC_MAP.items():
            for mg in [m_info["base"], m_info["pos1"], m_info["pos2"], m_info["pos3"]]:
                strat_by_magic[mg] = strat_id

        per_strategy: Dict[str, dict] = {sid: {"total_trades": 0, "wins": 0, "losses": 0,
                                                "gross_profit_usd": 0.0, "gross_loss_usd": 0.0,
                                                "net_profit_usd": 0.0} for sid in STRATEGY_MAGIC_MAP}

        gross_profit = gross_loss = 0.0
        wins = losses = 0
        peak = self.initial_balance
        max_dd = 0.0
        running = self.initial_balance
        for t in trades:
            pnl = t["profit"]
            running += pnl
            peak = max(peak, running)
            max_dd = max(max_dd, peak - running)

            sid = strat_by_magic.get(t["magic"], "UNKNOWN")
            if sid not in per_strategy:
                per_strategy[sid] = {"total_trades": 0, "wins": 0, "losses": 0,
                                      "gross_profit_usd": 0.0, "gross_loss_usd": 0.0, "net_profit_usd": 0.0}
            per_strategy[sid]["total_trades"] += 1
            per_strategy[sid]["net_profit_usd"] = round(per_strategy[sid]["net_profit_usd"] + pnl, 2)
            if pnl > 0:
                per_strategy[sid]["wins"] += 1
                per_strategy[sid]["gross_profit_usd"] = round(per_strategy[sid]["gross_profit_usd"] + pnl, 2)
                gross_profit += pnl
                wins += 1
            else:
                per_strategy[sid]["losses"] += 1
                per_strategy[sid]["gross_loss_usd"] = round(per_strategy[sid]["gross_loss_usd"] + pnl, 2)
                gross_loss += pnl
                losses += 1

        for sid, s in per_strategy.items():
            s["winrate_pct"] = round(100.0 * s["wins"] / s["total_trades"], 1) if s["total_trades"] else 0.0
            if s["gross_loss_usd"] < 0:
                s["profit_factor"] = round(s["gross_profit_usd"] / abs(s["gross_loss_usd"]), 2)
            elif s["gross_profit_usd"] > 0:
                s["profit_factor"] = None  # undefined/infinite - no losing trades yet
            else:
                s["profit_factor"] = 0.0

        final_balance = self.connector.balance
        net_profit = final_balance - self.initial_balance
        total_trades = len(trades)

        return {
            "symbol": self.symbol,
            "period_start": str(self.m5_df.iloc[0]["time"]) if self.m5_df is not None and len(self.m5_df) else None,
            "period_end": str(self.m5_df.iloc[-1]["time"]) if self.m5_df is not None and len(self.m5_df) else None,
            "total_m5_bars": int(len(self.m5_df)) if self.m5_df is not None else 0,
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(final_balance, 2),
            "net_profit_usd": round(net_profit, 2),
            "net_profit_pct": round(100.0 * net_profit / self.initial_balance, 2) if self.initial_balance else 0.0,
            "gross_profit_usd": round(gross_profit, 2),
            "gross_loss_usd": round(gross_loss, 2),
            "profit_factor": (round(gross_profit / abs(gross_loss), 2) if gross_loss < 0
                               else (None if gross_profit > 0 else 0.0)),
            "total_trades": total_trades,
            "win_trades": wins,
            "loss_trades": losses,
            "winrate_pct": round(100.0 * wins / total_trades, 1) if total_trades else 0.0,
            "max_drawdown_usd": round(max_dd, 2),
            "max_drawdown_pct": round(100.0 * max_dd / peak, 2) if peak else 0.0,
            "strategy_breakdown": per_strategy,
            "assumptions": {
                "spread_points_fixed": self.spread_points,
                "same_bar_sl_tp_conflict": "SL assumed first (conservative)",
                "trailing_and_be_lock_simulated": True,
                "note": "Public/CSV-sourced or live-MT5-sourced historical data replayed through the real bot_engine.py signal, AI-gating, and execution logic (run_iteration()). Not a substitute for forward/paper testing."
            }
        }

    def save_results(self, path: str, results: Optional[dict] = None):
        results = results or self.compute_results()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backtest the Elite 5 Pillars bot against historical XAUUSD data.")
    parser.add_argument("m5_csv", nargs="?", help="Path to an M5 OHLC CSV (MT5 export or generic). Omit to use --mt5 instead.")
    parser.add_argument("--m15", help="Optional separate M15 CSV (else derived by resampling M5).")
    parser.add_argument("--h1", help="Optional separate H1 CSV (else derived by resampling M5).")
    parser.add_argument("--mt5", action="store_true", help="Load data from a live, logged-in MT5 terminal instead of CSV.")
    parser.add_argument("--bars", type=int, default=20000, help="Bar count to request when using --mt5.")
    parser.add_argument("--symbol", default="XAUUSDc")
    parser.add_argument("--balance", type=float, default=3000.0)
    parser.add_argument("--spread", type=float, default=20.0, help="Fixed spread in points (1pt = $0.01).")
    parser.add_argument("--warmup", type=int, default=800)
    parser.add_argument("--out", default="backtest_results.json")
    args = parser.parse_args()

    bt = HistoricalBacktester(symbol=args.symbol, initial_balance=args.balance, spread_points=args.spread)
    if args.mt5:
        bt.load_from_mt5(bars_count=args.bars)
    elif args.m5_csv:
        bt.load_from_csv(args.m5_csv, args.m15, args.h1)
    else:
        parser.error("Provide either an m5_csv path or --mt5.")

    results = bt.run(warmup_bars=args.warmup)
    bt.save_results(args.out, results)
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {args.out}")
