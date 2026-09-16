"""
Advanced Trading Bot Strategy Engine for XAUUSD (Gold)
Streamlined to the "Elite 5 Active Pillars" across Market Sessions:
1. PULLBACK_DR_EKK - Signature Pullback (#PullBack ร้อยล้าน - Dr. Ekk / Trader Overseas)
2. RTM_M4_CONSERVATIVE - RTM Quasimodo Conservative QML Retest (M15 + H1)
3. RTM_M6_ELITE_GROWTH - RTM Quasimodo Elite Growth Institutional Retest (M15 + H1)
4. SMC_X_STO_H1 - SMCxSTO ระบบปีศาจ H1 Swing Devil System (EMA 50/200 + Discount/Premium ATR + Single OB + Stoch)
5. KC_LIQUIDITY_DOMINANCE - KC Forex Trading: Liquidity Sweep + Candle Dominance (M5)
"""

import time
import math
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time as dtime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from strategy_optimizer import RealTimeStrategyOptimizer
from exit_benchmark_tracker import ExitBenchmarkTracker
from regime_liquidity_scorer import MarketRegimeScorer

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

logger = logging.getLogger("BotEngine")

STRATEGY_MAGIC_MAP = {
    "PULLBACK_DR_EKK": {"base": 555860, "pos1": 555861, "pos2": 555862, "pos3": 555863},
    "RTM_M4_CONSERVATIVE": {"base": 777004, "pos1": 777014, "pos2": 777024, "pos3": 777034},
    "RTM_M6_ELITE_GROWTH": {"base": 777006, "pos1": 777016, "pos2": 777026, "pos3": 777036},
    "SMC_X_STO_H1": {"base": 555770, "pos1": 555771, "pos2": 555772, "pos3": 555773},
    "KC_LIQUIDITY_DOMINANCE": {"base": 555880, "pos1": 555881, "pos2": 555882, "pos3": 555883},
    "ICT_JUDAS_RTM_QM": {"base": 555910, "pos1": 555911, "pos2": 555912, "pos3": 555913},
    "ICT_SILVER_BULLET_FVG": {"base": 555920, "pos1": 555921, "pos2": 555922, "pos3": 555923},
    "EW_WAVE3_BREAKER": {"base": 555930, "pos1": 555931, "pos2": 555932, "pos3": 555933}
}

# Per-pillar risk sizing profile: default risk %, sizing MODE (whether Step-Up Compounding
# tiering applies), and the safe [min, max] bounds a user-configurable override is clamped to.
# This is the single source of truth for calculate_lot_size()'s default behavior below AND for
# the /api/strategy/risk_config Web Dashboard endpoint (main.py) that lets the user set a custom
# risk % per setup without touching code or restarting the bot - see RISK_OVERRIDE_MIN/MAX_PCT
# and the "risk_overrides" key inside config["strategy"] read below.
RISK_PROFILE_DEFAULTS = {
    "PULLBACK_DR_EKK":        {"default_pct": 2.0, "mode": "STEP_UP_COMPOUNDING"},
    "RTM_M4_CONSERVATIVE":    {"default_pct": 2.0, "mode": "STEP_UP_COMPOUNDING"},
    "RTM_M6_ELITE_GROWTH":    {"default_pct": 2.0, "mode": "STEP_UP_COMPOUNDING"},
    "SMC_X_STO_H1":           {"default_pct": 1.0, "mode": "FIXED"},
    "KC_LIQUIDITY_DOMINANCE": {"default_pct": 1.5, "mode": "STEP_UP_COMPOUNDING"},
    "ICT_JUDAS_RTM_QM":        {"default_pct": 0.5, "mode": "FIXED"},
    "ICT_SILVER_BULLET_FVG":   {"default_pct": 0.5, "mode": "FIXED"},
    "EW_WAVE3_BREAKER":        {"default_pct": 1.0, "mode": "FIXED"},
    "TUG_OF_WAR_M15":         {"default_pct": 0.5, "mode": "FIXED"},
}
RISK_OVERRIDE_MIN_PCT = 0.10
RISK_OVERRIDE_MAX_PCT = 5.00

# Per-pillar trading schedule defaults: start and end hours in Thai Time (GMT+7).
# Setups that previously traded in the Asian session (Pullback Dr. Ekk, RTM M6, SMCxSTO H1)
# now start at 14:00 (London session) through 24:00 (midnight).
# Users can freely customize each setup's schedule via the Web Dashboard without bot restart.
DEFAULT_TRADING_HOURS = {
    "PULLBACK_DR_EKK":        {"start": "14:00", "end": "24:00"},
    "RTM_M4_CONSERVATIVE":    {"start": "14:00", "end": "24:00"},
    "RTM_M6_ELITE_GROWTH":    {"start": "14:00", "end": "24:00"},
    "SMC_X_STO_H1":           {"start": "14:00", "end": "24:00"},
    "KC_LIQUIDITY_DOMINANCE": {"start": "14:00", "end": "24:00"},
    "ICT_JUDAS_RTM_QM":        {"start": "14:00", "end": "17:00"},
    "ICT_SILVER_BULLET_FVG":   {"start": "19:00", "end": "23:00"},
    "EW_WAVE3_BREAKER":        {"start": "14:00", "end": "02:00"},
    "TUG_OF_WAR_M15":         {"start": "14:00", "end": "24:00"},
}

def is_time_in_range(check_t: dtime, start_str: str, end_str: str) -> bool:
    """Checks if a given time (GMT+7) is inside [start_str, end_str].
    Supports midnight wrap-around (e.g. 14:00 to 02:00) and 24:00 end of day."""
    try:
        def parse_t(s: str) -> dtime:
            s = str(s).strip()
            if s in ["24:00", "24:00:00", "00:00:00", "00:00"]:
                if s.startswith("24"):
                    return dtime(23, 59, 59)
                return dtime(0, 0, 0)
            parts = s.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            sec = int(parts[2]) if len(parts) > 2 else 0
            if h >= 24:
                return dtime(23, 59, 59)
            return dtime(h, m, sec)

        t_start = parse_t(start_str)
        t_end = parse_t(end_str)

        # Special case: end is 24:00 or 00:00 meaning end of calendar day
        if end_str.strip() in ["24:00", "24:00:00", "00:00"] and t_start > dtime(0, 0):
            t_end = dtime(23, 59, 59)

        if t_start <= t_end:
            return t_start <= check_t <= t_end
        else:
            # Crosses midnight (e.g. 14:00 - 02:00)
            return (check_t >= t_start) or (check_t <= t_end)
    except Exception:
        return True

class GoldScalpingBot:
    """Scalping Strategy Execution Engine with Multi-Setup Concurrent Risk Guard."""
    def __init__(self, connector, config: dict):
        self.connector = connector
        self.config = config
        self.notifier = None
        self.optimizer = RealTimeStrategyOptimizer()
        self.benchmark_tracker = ExitBenchmarkTracker()
        self.scorer = MarketRegimeScorer()
        self.is_running = False
        self.bot_status = "STOPPED"
        self.account_name = "Account"
        
        # State tracking
        self.last_bar_time = None
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.pause_until_time = 0
        self.day_starting_equity = 0.0
        self.current_day = None
        self.daily_target_reached = False
        self.daily_max_loss_reached = False
        self.latest_trend = "ANALYZING..."
        self.last_signal = "None"
        self.current_session_name = "ASIAN SESSION"
        self.fast_ema_val = 0.0
        self.slow_ema_val = 0.0
        self.fast_slope = 0.0
        self.slow_slope = 0.0
        self.logs: List[dict] = []
        self.initial_risk_map: Dict[int, float] = {}
        
        # RTM Staggered Deep-Pullback & Anti-Clustering State
        self.active_rtm_setup: Optional[dict] = None
        self.last_rtm_sl_time: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0}
        self.last_rtm_m5_confirmed_bar = None
        self.judas_last_trade_date: Optional[object] = None
        
        mt5_cfg = self.config.get("mt5", {})
        self.magic_number = mt5_cfg.get("magic_number", 555888)
        self.magic_pos1 = self.magic_number + 1
        self.magic_pos2 = self.magic_number + 2
        self.magic_pos3 = self.magic_number + 3

        # Auto-sync MultiAccountManager analytics instance and trading hours API routes upon bot hot-reload
        try:
            import sys
            import strategy_analytics
            for m_name in ["__main__", "main"]:
                mod = sys.modules.get(m_name)
                if mod and hasattr(mod, "account_manager"):
                    mod.account_manager.analytics = strategy_analytics.RealTradeAnalyticsManager()
                    if hasattr(mod, "app"):
                        register_trading_hours_api(mod.app, mod.account_manager)
        except Exception:
            pass

    def get_magic_for_strategy(self, strat_id: str) -> dict:
        """Returns isolated magic numbers for a specific setup."""
        return STRATEGY_MAGIC_MAP.get(strat_id, {
            "base": self.magic_number,
            "pos1": self.magic_pos1,
            "pos2": self.magic_pos2,
            "pos3": self.magic_pos3
        })

    def get_all_bot_magics(self) -> List[int]:
        """Returns a flat list of all magic numbers managed by this bot engine."""
        magics = [self.magic_number, self.magic_pos1, self.magic_pos2, self.magic_pos3]
        for m_info in STRATEGY_MAGIC_MAP.values():
            magics.extend([m_info["base"], m_info["pos1"], m_info["pos2"], m_info["pos3"]])
        return list(set(magics))

    def has_open_positions_for_setup(self, symbol: str, strat_id: str) -> bool:
        """Checks if there are currently open positions specifically for this setup."""
        m_info = self.get_magic_for_strategy(strat_id)
        setup_magics = [m_info["base"], m_info["pos1"], m_info["pos2"], m_info["pos3"]]
        positions = self.connector.get_open_positions(symbol)
        for p in positions:
            if p.get('magic') in setup_magics:
                return True
        return False

    def add_log(self, message: str, level: str = "INFO"):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": message,
            "level": level
        }
        self.logs.insert(0, entry)
        if len(self.logs) > 60:
            self.logs.pop()
        logger.info(f"[{self.account_name}] [{level}] {message}")

    def start(self):
        self.is_running = True
        self.bot_status = "RUNNING"
        acc = self.connector.get_account_info()
        self.day_starting_equity = acc.get("balance", acc.get("equity", 10000.0))
        self.current_day = datetime.now().date()
        self.daily_target_reached = False
        self.daily_max_loss_reached = False
        self.pause_until_time = 0
        self.add_log("🚀 Scalping Bot Engine Started successfully.", "SUCCESS")

    def stop(self):
        self.is_running = False
        self.bot_status = "STOPPED"
        self.add_log("⏹ Scalping Bot Engine Stopped.", "WARNING")

    def update_config(self, new_config: dict):
        self.config.update(new_config)
        self.add_log("⚙️ Bot Strategy Configuration updated.", "INFO")

    def check_new_day(self):
        today = datetime.now().date()
        acc = self.connector.get_account_info()
        equity = acc.get("equity", 10000.0)
        balance = acc.get("balance", 10000.0)

        if self.current_day != today or self.day_starting_equity == 0.0:
            self.current_day = today
            self.day_starting_equity = balance
            self.daily_target_reached = False
            self.daily_max_loss_reached = False
            self.pause_until_time = 0
            self.add_log(f"📅 New trading day initialized. Base Capital: ${self.day_starting_equity:.2f}", "INFO")

        # Deposit or Capital Adjustment Detection (Based on actual BALANCE to ignore floating PnL swings)
        if self.day_starting_equity > 0 and (balance > (self.day_starting_equity * 1.20) or balance < (self.day_starting_equity * 0.80)):
            old_base = self.day_starting_equity
            self.day_starting_equity = balance
            self.daily_target_reached = False
            self.daily_max_loss_reached = False
            self.add_log(f"💳 Deposit/Balance adjustment detected (${old_base:.2f} ➔ ${balance:.2f}). Base Capital updated & ready to trade!", "INFO")

        # Daily Profit & Loss Safety Guard
        if self.day_starting_equity > 0:
            strat_cfg = self.config.get("strategy", {})
            daily_target_pct = strat_cfg.get("daily_target_percent", 10.0) # Target +10%
            daily_max_loss_pct = strat_cfg.get("daily_max_loss_percent", 5.0) # Max Loss -5%

            pnl_pct = ((equity - self.day_starting_equity) / self.day_starting_equity) * 100.0

            if pnl_pct >= daily_target_pct and not self.daily_target_reached:
                self.daily_target_reached = True
                self.add_log(f"🎉 [DAILY TARGET HIT] Profit +{pnl_pct:.2f}% >= {daily_target_pct}%. Banking profits & locking for today!", "SUCCESS")

            elif pnl_pct <= -daily_max_loss_pct and not self.daily_max_loss_reached:
                self.daily_max_loss_reached = True
                self.add_log(f"🛑 [DAILY MAX LOSS SHIELD] Loss {pnl_pct:.2f}% <= -{daily_max_loss_pct}%. Capital Shield active! Pausing trading until tomorrow.", "WARNING")

    def get_current_session(self) -> str:
        """Determines active forex/gold market session in Thai Time (GMT+7)."""
        th_tz = timezone(timedelta(hours=7))
        now_hour = datetime.now(th_tz).hour # Guaranteed Thai time GMT+7 regardless of host VPS
        if 7 <= now_hour < 14:
            return "ASIAN SESSION"
        elif 14 <= now_hour < 19:
            return "LONDON SESSION"
        elif now_hour >= 19 or now_hour < 4:
            return "NEW YORK SESSION"
        else:
            return "LATE NIGHT ROLLOVER"

    def is_setup_in_trading_hours(self, strat_id: str, check_time: Optional[dtime] = None) -> Tuple[bool, str, str, str]:
        """
        Validates whether the given strategy setup is currently within its allowed trading hours.
        Returns: (is_allowed, reason, start_time, end_time)
        Reads overrides from config["strategy"]["trading_hours_overrides"][strat_id],
        falling back to DEFAULT_TRADING_HOURS[strat_id].
        """
        hours_cfg = dict(DEFAULT_TRADING_HOURS.get(strat_id, {"start": "14:00", "end": "24:00"}))
        strat_cfg = self.config.get("strategy", {})
        overrides = strat_cfg.get("trading_hours_overrides", {})
        if strat_id in overrides and isinstance(overrides[strat_id], dict):
            s_custom = overrides[strat_id].get("start_time") or overrides[strat_id].get("start")
            e_custom = overrides[strat_id].get("end_time") or overrides[strat_id].get("end")
            if s_custom and e_custom:
                hours_cfg["start"] = str(s_custom)
                hours_cfg["end"] = str(e_custom)

        start_str = hours_cfg.get("start", "14:00")
        end_str = hours_cfg.get("end", "24:00")

        if check_time is not None:
            now_t = check_time
        else:
            sim_time = getattr(self.connector, "current_time", None)
            if sim_time is not None and hasattr(sim_time, "time") and not hasattr(sim_time, "_mock_return_value"):
                now_t = sim_time.time()
            else:
                th_tz = timezone(timedelta(hours=7))
                now_t = datetime.now(th_tz).time()

        allowed = is_time_in_range(now_t, start_str, end_str)
        if not allowed:
            reason = f"OUTSIDE TRADING HOURS ({now_t.strftime('%H:%M')} not in {start_str}-{end_str} Thai Time)"
            return False, reason, start_str, end_str
        return True, "IN_HOURS", start_str, end_str

    def run_iteration(self):
        """Called periodically by AccountManager to evaluate strategy."""
        if not self.is_running:
            return

        self.check_new_day()
        symbol = self.config.get("mt5", {}).get("symbol", "XAUUSDc")
        self.current_session_name = self.get_current_session()

        # 1. Manage Active Positions
        self.manage_open_positions(symbol)

        # 1.5. Monitor and execute pending RTM pullback setups (ticks/micro-pullbacks)
        self._check_and_execute_pending_rtm_pullbacks(symbol)

        # 2. Check Bar Close
        rates = self.connector.get_rates(symbol, "M5", 100)
        if rates.empty or len(rates) < 35:
            return

        current_bar_time = rates['time'].iloc[-1]
        if self.last_bar_time == current_bar_time:
            return

        self.process_strategy(rates, symbol)
        self.last_bar_time = current_bar_time

    def process_strategy(self, df: pd.DataFrame, symbol: str):
        strat_cfg = self.config.get("strategy", {})
        strat_mode = strat_cfg.get("strategy_mode", "ALL")
        session = self.get_current_session()

        # 1. Safety Checks
        if time.time() < self.pause_until_time:
            self.latest_trend = "PAUSED (CONSECUTIVE LOSS)"
            self.bot_status = "PAUSED"
            return
        if self.daily_target_reached:
            self.latest_trend = "PAUSED (DAILY TARGET HIT)"
            self.bot_status = "TARGET HIT"
            return
        if self.daily_max_loss_reached:
            self.latest_trend = "PAUSED (DAILY MAX LOSS)"
            self.bot_status = "MAX LOSS"
            return

        if session == "LATE NIGHT ROLLOVER":
            self.latest_trend = "SLEEP (ROLLOVER & SPREAD PAUSE)"
            self.bot_status = "ROLLOVER PAUSE"
            return

        self.bot_status = "RUNNING"

        # 2. Portfolio Level Risk Safeguard (Check Max Concurrent Setups & Margin)
        positions = self.connector.get_open_positions(symbol)
        all_bot_magics = self.get_all_bot_magics()
        bot_open_positions = [p for p in positions if p.get('magic') in all_bot_magics]
        
        # Determine how many distinct setups are currently open
        active_setup_count = 0
        for s_key, m_info in STRATEGY_MAGIC_MAP.items():
            s_magics = [m_info["base"], m_info["pos1"], m_info["pos2"], m_info["pos3"]]
            if any(p.get('magic') in s_magics for p in bot_open_positions):
                active_setup_count += 1

        # Allow each setup to execute concurrently if its conditions are met (up to all 7 active models)
        max_concurrent_setups = strat_cfg.get("max_concurrent_setups", len(STRATEGY_MAGIC_MAP))
        if active_setup_count >= max_concurrent_setups:
            self.latest_trend = f"PORTFOLIO RISK CEILING ({active_setup_count}/{max_concurrent_setups} Setups Active)"
            return

        # Account Margin Safeguard: Ensure margin level is healthy before opening additional setups
        acc_info = self.connector.get_account_info()
        margin_level = acc_info.get("margin_level", 0.0)
        if margin_level > 0 and margin_level < 150.0:
            self.latest_trend = f"LOW MARGIN GUARD (Margin Level {margin_level:.0f}% < 150%)"
            return

        # 3. Check Spread Filter (Standard point scaling: 1 pt = $0.01)
        market_info = self.connector.get_market_info(symbol)
        spread = market_info.get("spread", 20.0)
        max_spread = strat_cfg.get("max_spread_points", 45.0)
        if spread > max_spread:
            self.latest_trend = f"WAITING (SPREAD {spread:.1f} > {max_spread:.1f})"
            return

        # 4. Calculate Indicators
        fast_period = strat_cfg.get("fast_ema", 50)
        slow_period = strat_cfg.get("slow_ema", 150)

        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=fast_period, adjust=False).mean()
        df['ema60'] = df['close'].ewm(span=60, adjust=False).mean()  # Signature Dr. Ekk line
        df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['ema150'] = df['close'].ewm(span=slow_period, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        # ATR 14
        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift()).abs()
        lc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df['atr14'] = tr.rolling(window=14).mean().bfill()
        df['atr'] = df['atr14']

        df['sma20'] = df['close'].rolling(window=20).mean()
        df['std20'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['sma20'] + (2.0 * df['std20'])
        df['bb_lower'] = df['sma20'] - (2.0 * df['std20'])
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / (df['sma20'] + 1e-9)

        # Micro Trend EMAs for Flash Scalper
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

        # Hyper-Fast RSI (4), Fast RSI (7) for Asian Scalp & Standard RSI (14) for Trend
        delta = df['close'].diff()
        gain4 = (delta.where(delta > 0, 0)).rolling(window=4).mean()
        loss4 = (-delta.where(delta < 0, 0)).rolling(window=4).mean()
        rs4 = gain4 / (loss4 + 1e-9)
        df['rsi4'] = 100 - (100 / (1 + rs4))

        gain7 = (delta.where(delta > 0, 0)).rolling(window=7).mean()
        loss7 = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
        rs7 = gain7 / (loss7 + 1e-9)
        df['rsi7'] = 100 - (100 / (1 + rs7))

        gain14 = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss14 = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs14 = gain14 / (loss14 + 1e-9)
        df['rsi14'] = 100 - (100 / (1 + rs14))

        b1 = df.iloc[-2]
        b4 = df.iloc[-5]

        self.fast_ema_val = round(float(b1['ema50']), 2)
        self.slow_ema_val = round(float(b1['ema150']), 2)
        self.fast_slope = round((float(b1['ema50']) - float(b4['ema50'])) / 0.01, 1)
        self.slow_slope = round((float(b1['ema150']) - float(b4['ema150'])) / 0.01, 1)

        news_status = self.optimizer.news_calendar.get_news_status()

        # -------------------------------------------------------------
        # 5. INDEPENDENT MULTI-SETUP EVALUATION & EXECUTION PIPELINE
        # -------------------------------------------------------------
        
        # --- PILLAR 1: SMCxSTO ระบบปีศาจ H1 Devil System (Macro Trend & Single-Rule OB) ---
        smc_enabled = strat_cfg.get("smc_x_sto_h1_enabled", True)
        if smc_enabled and (strat_mode in ["ALL", "SMC_X_STO_H1", "SMCXSTO", "ALCHEMIST_4", "UPGRADED_4"]):
            if not self.has_open_positions_for_setup(symbol, "SMC_X_STO_H1"):
                if self.is_setup_in_trading_hours("SMC_X_STO_H1")[0]:
                    b_sig, s_sig, reason = self._check_smc_x_sto_h1(symbol)
                    if b_sig or s_sig:
                        self._process_single_setup_signal(df, symbol, spread, "SMC_X_STO_H1", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 4: RTM Quasimodo Multi-Model Institutional Engine (M15 + H1 Filter) ---
        rtm_mode = strat_cfg.get("rtm_mode", "PULLBACK_DUO")
        rtm_variants = ["RTM_M4_CONSERVATIVE", "RTM_M6_ELITE_GROWTH"]
        if strat_mode in ["ALL", "RTM", "ALCHEMIST_4", "UPGRADED_4"] or any(strat_mode == v for v in rtm_variants):
            if self.is_setup_in_trading_hours("RTM_M6_ELITE_GROWTH")[0]:
                self._process_rtm_confluence_engine(df, symbol, spread, rtm_mode)

        # --- PILLAR 5: Signature Pullback Engine (#PullBack ร้อยล้าน - Dr. Ekk / Trader Overseas) ---
        if strat_mode in ["ALL", "PULLBACK_DR_EKK", "DR_EKK_PULLBACK"]:
            if not self.has_open_positions_for_setup(symbol, "PULLBACK_DR_EKK"):
                if self.is_setup_in_trading_hours("PULLBACK_DR_EKK")[0]:
                    b_sig, s_sig, reason = self._check_pullback_dr_ekk(df, symbol)
                    if b_sig or s_sig:
                        self._process_single_setup_signal(df, symbol, spread, "PULLBACK_DR_EKK", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 5: KC Forex Trading (Liquidity Sweep + Candle Dominance) ---
        kc_enabled = strat_cfg.get("kc_liquidity_dominance_enabled", True)
        if kc_enabled and (strat_mode in ["ALL", "KC_LIQUIDITY_DOMINANCE", "KC_DOMINANCE", "ALCHEMIST_4", "UPGRADED_4"]):
            if not self.has_open_positions_for_setup(symbol, "KC_LIQUIDITY_DOMINANCE"):
                if self.is_setup_in_trading_hours("KC_LIQUIDITY_DOMINANCE")[0]:
                    b_sig, s_sig, reason = self._check_kc_liquidity_dominance(df, symbol)
                    if b_sig or s_sig:
                        self._process_single_setup_signal(df, symbol, spread, "KC_LIQUIDITY_DOMINANCE", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 6: ICT Judas Swing & RTM Quasimodo (London Killzone) ---
        judas_qm_enabled = strat_cfg.get("ict_judas_rtm_qm_enabled", True)
        if judas_qm_enabled and (strat_mode in ["ALL", "ICT_JUDAS_RTM_QM", "JUDAS_QM"]):
            if not self.has_open_positions_for_setup(symbol, "ICT_JUDAS_RTM_QM"):
                if self.is_setup_in_trading_hours("ICT_JUDAS_RTM_QM")[0]:
                    b_sig, s_sig, reason = self._check_ict_judas_rtm_qm(df, symbol)
                    if b_sig or s_sig:
                        self._process_single_setup_signal(df, symbol, spread, "ICT_JUDAS_RTM_QM", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 7: ICT NY Silver Bullet & FVG Imbalance (NY AM Killzone) ---
        silver_bullet_enabled = strat_cfg.get("ict_silver_bullet_fvg_enabled", True)
        if silver_bullet_enabled and (strat_mode in ["ALL", "ICT_SILVER_BULLET_FVG", "SILVER_BULLET"]):
            if not self.has_open_positions_for_setup(symbol, "ICT_SILVER_BULLET_FVG"):
                if self.is_setup_in_trading_hours("ICT_SILVER_BULLET_FVG")[0]:
                    b_sig, s_sig, reason = self._check_ict_silver_bullet_fvg(df, symbol)
                    if b_sig or s_sig:
                        self._process_single_setup_signal(df, symbol, spread, "ICT_SILVER_BULLET_FVG", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 8: Elliott Wave 3 & SMC Breaker Propulsion (Trend Session) ---
        ew_breaker_enabled = strat_cfg.get("ew_wave3_breaker_enabled", True)
        if ew_breaker_enabled and (strat_mode in ["ALL", "EW_WAVE3_BREAKER", "EW_BREAKER"]):
            if not self.has_open_positions_for_setup(symbol, "EW_WAVE3_BREAKER"):
                if self.is_setup_in_trading_hours("EW_WAVE3_BREAKER")[0]:
                    b_sig, s_sig, reason = self._check_ew_wave3_breaker(df, symbol)
                    if b_sig or s_sig:
                        self._process_single_setup_signal(df, symbol, spread, "EW_WAVE3_BREAKER", "BUY" if b_sig else "SELL", reason)

        # Update Trend Badge with News Radar
        if news_status.get("is_news_active"):
            self.latest_trend = news_status.get("label", "⚡ HIGH IMPACT NEWS")
        elif session == "ASIAN SESSION":
            self.latest_trend = "ASIAN RANGE (MEAN REVERSION)"
        elif b1['ema50'] > b1['ema150']:
            self.latest_trend = "BULLISH (UP)"
        elif b1['ema50'] < b1['ema150']:
            self.latest_trend = "BEARISH (DOWN)"
        else:
            self.latest_trend = "SIDEWAY"

    def _process_single_setup_signal(self, df: pd.DataFrame, symbol: str, spread: float, strat_key: str, action_type: str, reason: str, is_asian_scalp: bool = False, **kwargs):
        """Processes and executes a signal specifically isolated for a single strategy setup."""
        # 0. Evaluate Trading Hours Schedule Guard
        in_hours, h_reason, s_t, e_t = self.is_setup_in_trading_hours(strat_key)
        if not in_hours:
            self.add_log(f"⏰ [HOURS GUARD] {strat_key} ({action_type}) Skipped | {h_reason}", "INFO")
            self.latest_trend = f"WAITING ({strat_key}: Outside {s_t}-{e_t})"
            return

        # 1. Evaluate Market Regime & Liquidity Filter Score (0 - 100)
        score_res = self.scorer.evaluate_market_confluence(df, spread, strat_key)
        if not score_res.get("is_allowed", True):
            self.scorer.record_filtered_trade(strat_key, score_res)
            self.add_log(f"🛡️ [QUALITY FILTERED] {strat_key} ({action_type}) Skipped | Score: {score_res['score']}/100 ({score_res['grade']}) | {score_res['pillars']['volume']['desc']}", "WARNING")
            self.latest_trend = f"FILTERED ({strat_key}: Score {score_res['score']}/100)"
            return

        opt_params = self.optimizer.get_dynamic_rr_and_parameters(strat_key, df)
        if not opt_params.get("should_execute", True):
            self.latest_trend = f"AI PAUSED ({strat_key}: {opt_params.get('reason', 'Blocked')})"
            return

        # Apply quality bonus or special risk cap
        if strat_key == "NEWS_MOMENTUM_EXPANSION":
            opt_params["lot_multiplier"] = 0.5  # Fixed 0.5% risk requested by user
        elif score_res.get("grade") == "A+":
            opt_params["lot_multiplier"] = round(opt_params.get("lot_multiplier", 1.0) * score_res.get("lot_recommendation", 1.15), 2)

        if action_type == "BUY":
            self.last_signal = f"BUY ({reason} | Quality: {score_res['score']}/100 {score_res['grade']})"
            self.execute_buy(df, symbol, reason, is_asian_scalp, opt_params, strat_id=strat_key)
        elif action_type == "SELL":
            self.last_signal = f"SELL ({reason} | Quality: {score_res['score']}/100 {score_res['grade']})"
            self.execute_sell(df, symbol, reason, is_asian_scalp, opt_params, strat_id=strat_key)

    def _check_news_momentum_expansion(self, df: pd.DataFrame, news_status: dict) -> Tuple[bool, bool, str]:
        """
        ⚡ Momentum Expansion Breakout (24/7 Engine - All Sessions):
        Fires whenever price breaks out of the recent 12-candle swing range with a strong expansion candle (Body >= 58%).
        Works seamlessly both during High-Impact News releases AND high-liquidity regular sessions (London/NY).
        """
        if len(df) < 20: return False, False, ""
        b1 = df.iloc[-2] # Last closed candle
        
        # Calculate recent baseline swing range (bars -14 to -2)
        pre_swing_high = df['high'].iloc[-14:-2].max()
        pre_swing_low = df['low'].iloc[-14:-2].min()
        candle_body = abs(b1['close'] - b1['open'])
        candle_range = b1['high'] - b1['low'] + 1e-9
        body_pct = candle_body / candle_range
        
        rsi14 = b1.get('rsi14', 50.0)
        is_news_spike = news_status.get("is_news_active", False) or news_status.get("state") in ["NEWS_RELEASE_IMPACT", "POST_NEWS_DIGEST"]

        atr = float(b1.get('atr14', b1.get('atr', 2.50)))
        # Expansion validation: Require significant expansion candle (>= 1.8x ATR or >= 4.50 USD / 450 pts)
        min_expansion_range = max(1.2 * atr, 3.00) if is_news_spike else max(1.8 * atr, 4.50)
        is_solid_expansion = (body_pct >= 0.60) and (candle_range >= min_expansion_range)

        # Institutional Volume Confirmation:
        # If not during high-impact news, require tick_volume >= 1.5x 20-bar volume MA
        # to filter out low-liquidity fakeouts/traps during dead hours.
        vol_series = df.get('tick_volume')
        if vol_series is not None and len(vol_series) >= 22:
            vol_ma20 = float(vol_series.iloc[-22:-2].mean())
            curr_vol = float(b1.get('tick_volume', 0))
            is_volume_spike = (curr_vol >= vol_ma20 * 1.5)
        else:
            is_volume_spike = True

        volume_confirmed = is_news_spike or is_volume_spike
        if not volume_confirmed:
            return False, False, ""

        # BUY: Bullish Breakout above Swing High with solid body & RSI momentum
        if (is_news_spike or is_solid_expansion) and b1['close'] > pre_swing_high and b1['close'] > b1['open'] and body_pct >= 0.58 and rsi14 >= 52:
            tag = "⚡ High-Impact News Spike Breakout (BUY)" if is_news_spike else "🚀 Institutional Momentum Expansion Breakout (BUY)"
            return True, False, tag

        # SELL: Bearish Breakdown below Swing Low with solid body & RSI momentum
        if (is_news_spike or is_solid_expansion) and b1['close'] < pre_swing_low and b1['close'] < b1['open'] and body_pct >= 0.58 and rsi14 <= 48:
            tag = "⚡ High-Impact News Spike Breakdown (SELL)" if is_news_spike else "🚀 Institutional Momentum Expansion Breakdown (SELL)"
            return False, True, tag

        return False, False, ""

    def _calculate_pina_colada(self, df: pd.DataFrame, signal_bar: int = 4) -> dict:
        """
        🍸 Pina Colada Extreme Volatility Envelopes & Mean-Reversion System:
        - Bands: Upper & Lower Volatility Bands (EMA20 +/- 2.2 ATR14)
        - Crossing Down: Price drops below Lower Band (Overextended Sell)
        - Crossing Up: Price surges above Upper Band (Overextended Buy)
        - Coming Back: Price re-enters and closes back inside the band (Clean Re-entry Trigger)
        - Caution Label: Strong momentum expansion (Avoids catching falling knives/pumps)
        - Arrow: Confirmation signal after signal_bar validation
        """
        if len(df) < 25:
            return {"bull_arrow": False, "bear_arrow": False, "coming_back_bull": False, "coming_back_bear": False, "caution": False}

        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr14 = tr.rolling(window=14).mean()

        mid_band = df['close'].ewm(span=20, adjust=False).mean()
        upper_band = mid_band + (2.2 * atr14)
        lower_band = mid_band - (2.2 * atr14)

        b1 = df.iloc[-2] # Last closed candle
        b2 = df.iloc[-3] # Prior candle
        b3 = df.iloc[-4] # Prior prior candle

        curr_atr = float(atr14.iloc[-2]) if not math.isnan(atr14.iloc[-2]) else 2.50

        # Caution Label: Parabolic dump/pump (3 consecutive bars with wide bodies hugging outer bands)
        is_dumping = (b1['close'] < b1['open']) and (b2['close'] < b2['open']) and (b3['close'] < b3['open'])
        wide_body_dump = abs(b1['close'] - b1['open']) > (1.3 * curr_atr) or abs(b2['close'] - b2['open']) > (1.3 * curr_atr)
        caution_bear = is_dumping and wide_body_dump and (b1['low'] < lower_band.iloc[-2])

        is_pumping = (b1['close'] > b1['open']) and (b2['close'] > b2['open']) and (b3['close'] > b3['open'])
        wide_body_pump = abs(b1['close'] - b1['open']) > (1.3 * curr_atr) or abs(b2['close'] - b2['open']) > (1.3 * curr_atr)
        caution_bull = is_pumping and wide_body_pump and (b1['high'] > upper_band.iloc[-2])

        caution_active = caution_bear or caution_bull

        # Coming Back Bullish: Prior candle broke below Lower Band, latest closed candle closes back INSIDE lower band
        prior_pierced_lower = (b2['low'] < lower_band.iloc[-3]) or (b3['low'] < lower_band.iloc[-4]) or (b1['low'] < lower_band.iloc[-2])
        coming_back_bull = prior_pierced_lower and (b1['close'] > lower_band.iloc[-2]) and (b1['close'] > b1['open']) and not caution_bear

        # Coming Back Bearish: Prior candle broke above Upper Band, latest closed candle closes back INSIDE upper band
        prior_pierced_upper = (b2['high'] > upper_band.iloc[-3]) or (b3['high'] > upper_band.iloc[-4]) or (b1['high'] > upper_band.iloc[-2])
        coming_back_bear = prior_pierced_upper and (b1['close'] < upper_band.iloc[-2]) and (b1['close'] < b1['open']) and not caution_bull

        # Arrow Confirmation (Requires signal_bar momentum validation)
        has_bull_wick = (min(b1['open'], b1['close']) - b1['low']) >= (0.25 * curr_atr)
        has_bear_wick = (b1['high'] - max(b1['open'], b1['close'])) >= (0.25 * curr_atr)

        bull_arrow = coming_back_bull and has_bull_wick
        bear_arrow = coming_back_bear and has_bear_wick

        return {
            "upper_band": float(upper_band.iloc[-2]),
            "lower_band": float(lower_band.iloc[-2]),
            "mid_band": float(mid_band.iloc[-2]),
            "coming_back_bull": coming_back_bull,
            "coming_back_bear": coming_back_bear,
            "bull_arrow": bull_arrow,
            "bear_arrow": bear_arrow,
            "caution": caution_active
        }

    def _check_asian_range_sniper(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
        pina = self._calculate_pina_colada(df)
        if pina.get("caution", False):
            # Caution Label Active: Parabolic expansion detected, block counter-trend knives
            return False, False, ""

        b1 = df.iloc[-2]
        b2 = df.iloc[-3]
        lookback = df.iloc[-19:-2]
        range_high = lookback['high'].max()
        range_low = lookback['low'].min()

        candle_range = b1['high'] - b1['low']
        if candle_range <= 0.20:
            return False, False, ""

        atr = float(b1.get('atr', 2.50)) if 'atr' in df else 2.50
        
        # Filter 1: Block during massive breakout spike candles
        if candle_range > (2.5 * atr):
            return False, False, ""

        # Filter 2: Volatility Squeeze Gate (Block counter-trend knife during trending expansion)
        bb_width = float(b1['bb_upper']) - float(b1['bb_lower'])
        if bb_width > (2.8 * atr):
            return False, False, ""

        # Micro-Trend Directional Gate (Trend-Aligned Asian Scalp)
        ema20 = float(b1.get('ema20', b1['close']))
        ema50 = float(b1.get('ema50', b1['close']))
        ema150 = float(b1.get('ema150', b1['close']))
        is_asian_bullish = ema20 >= ema50
        is_asian_bearish = ema20 < ema50
        is_strong_uptrend = ema50 > (ema150 + 1.2 * atr)
        is_strong_downtrend = ema50 < (ema150 - 1.2 * atr)

        upper_wick = b1['high'] - max(b1['open'], b1['close'])
        lower_wick = min(b1['open'], b1['close']) - b1['low']

        # Bullish Rebound (At Range Low / BB Lower) - Only when Micro-Trend is Bullish/Neutral and not in strong downtrend
        if is_asian_bullish and not is_strong_downtrend:
            touched_lower = (b1['low'] <= b1['bb_lower'] or b1['low'] <= (range_low + 0.30) or pina.get("coming_back_bull"))
            closed_inside_lower = b1['close'] > b1['bb_lower'] or pina.get("coming_back_bull")
            if touched_lower and closed_inside_lower and b1['close'] > b1['open'] and (lower_wick / candle_range) >= 0.35:
                if b1['rsi7'] <= 38 and b1['rsi7'] > b2['rsi7']:
                    return True, False, "⛩️ Sideway Range Sniper: Support Rebound + Trend Filter (0.5% Risk)"

        # Bearish Rebound (At Range High / BB Upper) - Only when Micro-Trend is Bearish/Neutral and not in strong uptrend
        if is_asian_bearish and not is_strong_uptrend:
            touched_upper = (b1['high'] >= b1['bb_upper'] or b1['high'] >= (range_high - 0.30) or pina.get("coming_back_bear"))
            closed_inside_upper = b1['close'] < b1['bb_upper'] or pina.get("coming_back_bear")
            if touched_upper and closed_inside_upper and b1['close'] < b1['open'] and (upper_wick / candle_range) >= 0.35:
                if b1['rsi7'] >= 62 and b1['rsi7'] < b2['rsi7']:
                    return False, True, "⛩️ Sideway Range Sniper: Resistance Rebound + Trend Filter (0.5% Risk)"

        return False, False, ""

    def _check_pullback_dr_ekk(self, df: pd.DataFrame, symbol: str = "XAUUSD") -> Tuple[bool, bool, str]:
        """
        🎯 Signature Pullback Strategy (#PullBack ร้อยล้าน - Dr. Ekk / Trader Overseas):
        - Books: บทที่ 20 (Trade Checklist), บทที่ 8 (Breakout & Pullback 3-Confluence), บทที่ 5 (Chart Patterns), บทที่ 12 (SL/TP & Trailing)
        - Core Rules & Safeguards:
          1. Trend Context: M5 EMA 60 > EMA 150 (Buy) or EMA 60 < EMA 150 (Sell).
          2. H1 Macro Trend & Dump Protection: Check H1 EMA 50 to prevent buying into a dumping market.
          3. Break of Structure (BOS): Ensure impulse wave broke prior significant S/R.
          4. 3-Confluence Zone:
             - Dynamic Level: Pullback touches or approaches EMA 60 (within 0.35 * ATR).
             - Fibonacci Retracement: 0.35 <= Retracement <= 0.68 (Golden pocket 50.0% - 61.8%).
             - S/R Flip: Broken prior resistance/support retested as new support/resistance (within 0.75 * ATR).
          5. Trigger Candlestick:
             - Rejection Pinbar (wick >= 45% of range) bouncing off the zone
             - OR Engulfing candle closing decisively in trend direction.
          6. Confluence Score >= 2 (EMA 60 / S/R Flip + Fib Retracement).
          7. Risk: Strictly 2.0% per trade (capped at max 0.25 lot).
        """
        if len(df) < 35:
            return False, False, ""

        in_hours, _, _, _ = self.is_setup_in_trading_hours("PULLBACK_DR_EKK")
        if not in_hours:
            return False, False, ""

        b1 = df.iloc[-2]  # Last closed bar
        close_p = float(b1['close'])
        high_p = float(b1['high'])
        low_p = float(b1['low'])
        open_p = float(b1['open'])
        ema60 = float(b1.get('ema60', b1['close']))
        ema150 = float(b1.get('ema150', b1['close']))
        atr = float(b1.get('atr14', b1.get('atr', 2.50)))

        is_uptrend = (ema60 > ema150) and (close_p > ema60 - 0.25 * atr)
        is_downtrend = (ema60 < ema150) and (close_p < ema60 + 0.25 * atr)

        candle_range = high_p - low_p
        if candle_range < 0.60:
            return False, False, ""

        # H1 Macro Trend & Dump/Pump Shield
        h1_bull_allowed = True
        h1_bear_allowed = True
        if self.connector:
            try:
                df_h1 = self.connector.get_rates(symbol, "H1", 50)
                if df_h1 is not None and not df_h1.empty and len(df_h1) >= 25:
                    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
                    h1_c = float(df_h1['close'].iloc[-2])
                    h1_ema50 = float(df_h1['ema50'].iloc[-2])
                    h1_b1 = df_h1.iloc[-2]
                    h1_range = float(h1_b1['high']) - float(h1_b1['low'])
                    h1_body = abs(float(h1_b1['close']) - float(h1_b1['open']))
                    is_h1_bear_dump = (float(h1_b1['close']) < float(h1_b1['open'])) and (h1_body >= 0.55 * h1_range) and (h1_range >= 12.0)
                    is_h1_bull_pump = (float(h1_b1['close']) > float(h1_b1['open'])) and (h1_body >= 0.55 * h1_range) and (h1_range >= 12.0)
                    
                    h1_bull_allowed = (h1_c >= h1_ema50 - 2.00) and not is_h1_bear_dump
                    h1_bear_allowed = (h1_c <= h1_ema50 + 2.00) and not is_h1_bull_pump
            except Exception:
                pass

        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        body_size = abs(close_p - open_p)

        # Candle triggers
        bullish_pinbar = (lower_wick >= 0.45 * candle_range) and (close_p >= low_p + 0.45 * candle_range)
        bearish_pinbar = (upper_wick >= 0.45 * candle_range) and (close_p <= high_p - 0.45 * candle_range)

        prev_bar = df.iloc[-3]
        bullish_engulfing = (close_p > open_p) and (close_p > float(prev_bar['high'])) and (body_size >= 0.55 * candle_range)
        bearish_engulfing = (close_p < open_p) and (close_p < float(prev_bar['low'])) and (body_size >= 0.55 * candle_range)

        window = df.iloc[-32:-2]
        if len(window) < 20:
            return False, False, ""

        prev_window = df.iloc[-65:max(0, len(df)-20)]

        # Bullish Pullback Evaluation
        if is_uptrend and h1_bull_allowed and (bullish_pinbar or bullish_engulfing):
            swing_high_val = float(window['high'].max())
            swing_high_idx = window['high'].idxmax()
            window_prior = df.loc[window.index[0]:swing_high_idx]
            if len(window_prior) >= 4:
                swing_low_val = float(window_prior['low'].min())
                impulse_range = swing_high_val - swing_low_val

                # Break of Structure (BOS): Ensure the swing high broke a prior resistance level
                has_bos = True
                if len(prev_window) > 8:
                    prev_res = float(prev_window['high'].max())
                    has_bos = swing_high_val >= (prev_res - 0.20 * atr)

                if impulse_range >= 1.2 * atr and has_bos:
                    pullback_low = float(df.loc[swing_high_idx:df.index[-2], 'low'].min())
                    retrace_pct = (swing_high_val - pullback_low) / (impulse_range + 1e-9)

                    fib_conf = 0.35 <= retrace_pct <= 0.68
                    ema_conf = (low_p <= ema60 + 0.35 * atr) and (high_p >= ema60 - 0.40 * atr)

                    sr_flip_conf = False
                    if len(prev_window) > 8:
                        prev_res = float(prev_window['high'].max())
                        sr_flip_conf = abs(pullback_low - prev_res) <= 0.75 * atr

                    conf_score = int(fib_conf) + int(ema_conf) + int(sr_flip_conf)
                    if conf_score >= 2:
                        grade = "A+" if conf_score == 3 else "A"
                        trig_type = "Pinbar" if bullish_pinbar else "Engulfing"
                        return True, False, f"🎯 Pullback Dr. Ekk: Bullish {trig_type} at 3-Confluence ({grade} | Fib {retrace_pct*100:.0f}% + EMA60)"

        # Bearish Pullback Evaluation
        if is_downtrend and h1_bear_allowed and (bearish_pinbar or bearish_engulfing):
            swing_low_val = float(window['low'].min())
            swing_low_idx = window['low'].idxmin()
            window_prior = df.loc[window.index[0]:swing_low_idx]
            if len(window_prior) >= 4:
                swing_high_val = float(window_prior['high'].max())
                impulse_range_down = swing_high_val - swing_low_val

                # Break of Structure (BOS): Ensure the swing low broke a prior support level
                has_bos = True
                if len(prev_window) > 8:
                    prev_sup = float(prev_window['low'].min())
                    has_bos = swing_low_val <= (prev_sup + 0.20 * atr)

                if impulse_range_down >= 1.2 * atr and has_bos:
                    pullback_high = float(df.loc[swing_low_idx:df.index[-2], 'high'].max())
                    retrace_pct = (pullback_high - swing_low_val) / (impulse_range_down + 1e-9)

                    fib_conf = 0.35 <= retrace_pct <= 0.68
                    ema_conf = (high_p >= ema60 - 0.35 * atr) and (low_p <= ema60 + 0.40 * atr)

                    sr_flip_conf = False
                    if len(prev_window) > 8:
                        prev_sup = float(prev_window['low'].min())
                        sr_flip_conf = abs(pullback_high - prev_sup) <= 0.75 * atr

                    conf_score = int(fib_conf) + int(ema_conf) + int(sr_flip_conf)
                    if conf_score >= 2:
                        grade = "A+" if conf_score == 3 else "A"
                        trig_type = "Pinbar" if bearish_pinbar else "Engulfing"
                        return False, True, f"🎯 Pullback Dr. Ekk: Bearish {trig_type} at 3-Confluence ({grade} | Fib {retrace_pct*100:.0f}% + EMA60)"

        return False, False, ""

    def _check_kc_liquidity_dominance(self, df: pd.DataFrame, symbol: str = "XAUUSD") -> Tuple[bool, bool, str]:
        """
        🕯️ KC Forex Trading: Liquidity Sweep + Candle Dominance (Pillar #5)
        Upgraded with Multi-Methodology Confluence (Alchemist Trading principles):
        1. Context / Institutional Liquidity Hunt:
           - Price sweeps past recent swing high or low of last 15-20 bars (Stop Hunt / Fakeout).
           - Price fails to sustain breakout and rejects back inside the structural range.
        2. Candle Dominance (Price Action Tug-of-War Confirmation):
           - Strong reversal bar with solid body (Body Ratio >= 50% of candle range).
           - 1-Bar Dominance: Engulfs the previous opposite candle body/open.
           - OR 2-Bar Dominance: Current bar closes beyond the opening of 2 bars ago.
        3. ICT Precision Killzones:
           - London Killzone: 14:00 - 17:30 Thai Time (07:00 - 10:30 UTC)
           - New York Killzone: 19:00 - 23:30 Thai Time (12:00 - 16:30 UTC)
        4. Wyckoff Volume Effort vs Result:
           - Tick volume on sweep or dominance candle >= 1.10x 20-bar volume MA (Smart Money accumulation/distribution).
        5. RTM Sweep Depth Control:
           - Sweep depth limited to <= 1.25 * ATR14 to filter out violent momentum breakouts.
        6. SMC Macro Trend Alignment:
           - Aligned with H1 EMA50 slope and higher timeframe order flow.
        """
        if len(df) < 30:
            return False, False, ""

        # Simulated time in backtesting if available, else Thai Time (GMT+7)
        sim_time = getattr(self.connector, "current_time", None)
        if sim_time is not None and hasattr(sim_time, "time") and not hasattr(sim_time, "_mock_return_value"):
            now_time = sim_time.time()
        else:
            th_tz = timezone(timedelta(hours=7))
            now_time = datetime.now(th_tz).time()

        in_hours, _, _, _ = self.is_setup_in_trading_hours("KC_LIQUIDITY_DOMINANCE", now_time)
        if not in_hours:
            return False, False, ""

        # If not overridden by custom schedule, preserve precision dual-killzones
        has_override = "KC_LIQUIDITY_DOMINANCE" in self.config.get("strategy", {}).get("trading_hours_overrides", {})
        if not has_override:
            in_london_kz = (dtime(14, 0) <= now_time <= dtime(17, 30))
            in_ny_kz = (dtime(19, 0) <= now_time <= dtime(23, 30))
            if not (in_london_kz or in_ny_kz):
                return False, False, ""
            kz_name = "London KZ" if in_london_kz else "NY KZ"
        else:
            kz_name = f"Active KZ ({now_time.strftime('%H:%M')})"

        b1 = df.iloc[-2]  # Trigger bar (last completed bar)
        b2 = df.iloc[-3]  # Previous bar
        b3 = df.iloc[-4]  # Bar 2 steps ago

        curr_o = float(b1['open'])
        curr_c = float(b1['close'])
        curr_h = float(b1['high'])
        curr_l = float(b1['low'])
        curr_range = curr_h - curr_l

        if curr_range < 0.60:  # Avoid dead flat candles
            return False, False, ""

        curr_body = abs(curr_c - curr_o)
        curr_body_ratio = curr_body / curr_range

        # Require solid body (>= 50% of range)
        if curr_body_ratio < 0.50:
            return False, False, ""

        # Wyckoff Volume Effort confirmation
        vol_col = 'tick_volume' if 'tick_volume' in df.columns else ('volume' if 'volume' in df.columns else None)
        if vol_col is not None and len(df) >= 22:
            vol_series = df[vol_col]
            vol_ma20 = float(vol_series.iloc[-22:-2].mean())
            curr_vol = float(b1[vol_col])
            prev_vol = float(b2[vol_col])
            has_volume = (vol_ma20 <= 0) or (curr_vol >= 1.10 * vol_ma20) or (prev_vol >= 1.10 * vol_ma20)
        else:
            has_volume = True

        if not has_volume:
            return False, False, ""

        # RTM Sweep Depth calculation using M5 ATR14
        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift()).abs()
        lc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr_series = tr.rolling(window=14).mean()
        m5_atr = float(atr_series.iloc[-2]) if not pd.isna(atr_series.iloc[-2]) else 2.0
        if m5_atr <= 0:
            m5_atr = 2.0

        # SMC Macro Trend Alignment via H1 EMA50
        h1_bull_allowed = True
        h1_bear_allowed = True
        if self.connector:
            try:
                df_h1 = self.connector.get_rates(symbol, "H1", 60)
                if isinstance(df_h1, pd.DataFrame) and not df_h1.empty and len(df_h1) >= 50:
                    h1_ema50 = df_h1['close'].ewm(span=50, adjust=False).mean()
                    h1_close = float(df_h1['close'].iloc[-2])
                    h1_ema50_now = float(h1_ema50.iloc[-2])
                    h1_ema50_prev = float(h1_ema50.iloc[-7])
                    h1_slope = h1_ema50_now - h1_ema50_prev

                    is_h1_strong_downtrend = (h1_close < h1_ema50_now) and (h1_slope < -0.40)
                    is_h1_strong_uptrend = (h1_close > h1_ema50_now) and (h1_slope > 0.40)

                    h1_bull_allowed = not is_h1_strong_downtrend
                    h1_bear_allowed = not is_h1_strong_uptrend
            except Exception:
                pass

        prev_o = float(b2['open'])
        prev_c = float(b2['close'])
        prev_h = float(b2['high'])
        prev_l = float(b2['low'])

        # Swing Lookback window (15-20 bars prior to b1/b2)
        lookback_df = df.iloc[-22:-3]
        if len(lookback_df) < 10:
            return False, False, ""

        prior_swing_high = float(lookback_df['high'].max())
        prior_swing_low = float(lookback_df['low'].min())

        # 1. BULLISH SWEEP + CANDLE DOMINANCE (BUY)
        # Price swept prior swing low (either trigger bar or previous bar pierced it) and closed back above
        swept_low = (curr_l < prior_swing_low or prev_l < prior_swing_low) and (curr_c > prior_swing_low)
        sweep_depth_bull = prior_swing_low - min(curr_l, prev_l)
        if swept_low and curr_c > curr_o and (sweep_depth_bull <= 1.25 * m5_atr) and h1_bull_allowed:
            # 1-Bar Dominance: Engulfs prev candle open
            is_1bar_bull = (prev_c < prev_o) and (curr_c > prev_o)
            # 2-Bar Dominance: Combined with prev candle engulfs b3
            prev2_o = float(b3['open'])
            prev2_c = float(b3['close'])
            is_2bar_bull = (prev2_c < prev2_o) and (curr_c > prev2_o) and (prev_c >= prev_o)

            if is_1bar_bull or is_2bar_bull:
                dom_type = "1-Bar Engulfing" if is_1bar_bull else "2-Bar Combined"
                return True, False, f"🕯️ KC Dominance: Bullish Liquidity Sweep ({dom_type} | Body {curr_body_ratio*100:.0f}% | Swept {prior_swing_low:.2f} | Depth {sweep_depth_bull:.2f} | {kz_name})"

        # 2. BEARISH SWEEP + CANDLE DOMINANCE (SELL)
        # Price swept prior swing high and closed back below
        swept_high = (curr_h > prior_swing_high or prev_h > prior_swing_high) and (curr_c < prior_swing_high)
        sweep_depth_bear = max(curr_h, prev_h) - prior_swing_high
        if swept_high and curr_c < curr_o and (sweep_depth_bear <= 1.25 * m5_atr) and h1_bear_allowed:
            is_1bar_bear = (prev_c > prev_o) and (curr_c < prev_o)
            prev2_o = float(b3['open'])
            prev2_c = float(b3['close'])
            is_2bar_bear = (prev2_c > prev2_o) and (curr_c < prev2_o) and (prev_c <= prev_o)

            if is_1bar_bear or is_2bar_bear:
                dom_type = "1-Bar Engulfing" if is_1bar_bear else "2-Bar Combined"
                return False, True, f"🕯️ KC Dominance: Bearish Liquidity Sweep ({dom_type} | Body {curr_body_ratio*100:.0f}% | Swept {prior_swing_high:.2f} | Depth {sweep_depth_bear:.2f} | {kz_name})"

        return False, False, ""

    def _check_ict_judas_rtm_qm(self, df: pd.DataFrame, symbol: str = "XAUUSD") -> Tuple[bool, bool, str]:
        """
        🎯 ICT Judas Swing & RTM Quasimodo (M5, London Killzone 14:00 - 17:00 Thai Time)
        Synthesis of:
        - ICT Judas Swing: Fakeout outside Asian range (07:00 - 13:30 Thai Time) during London Open
        - Macro Filter: Aligns with H1 Trend (EMA 50 vs EMA 200) to avoid counter-trend knife catching
        - Session Lock: Max 1 high-probability Judas trade per day
        - RTM Quasimodo: High-Low-HigherHigh-LowerLow (Bearish) or Low-High-LowerLow-HigherHigh (Bullish)
        - Displacement BOS: Decisive body close past intermediate structure (>= 0.20 ATR)
        - First Time Back (FTB) retest into QML (Left Shoulder)
        """
        if len(df) < 25:
            return False, False, ""

        sim_time = getattr(self.connector, "current_time", None)
        if sim_time is not None and hasattr(sim_time, "time") and not hasattr(sim_time, "_mock_return_value"):
            curr_date = sim_time.date() if hasattr(sim_time, "date") else None
            now_time = sim_time.time()
        else:
            th_tz = timezone(timedelta(hours=7))
            now_dt = datetime.now(th_tz)
            curr_date = now_dt.date()
            now_time = now_dt.time()

        # 1. Trading hours window (Default London Killzone: 14:00 - 17:00 Thai Time)
        in_hours, _, _, _ = self.is_setup_in_trading_hours("ICT_JUDAS_RTM_QM", now_time)
        if not in_hours:
            return False, False, ""

        # 2. Daily Lock: Max 1 Judas QM trade per day
        if curr_date is not None and getattr(self, "judas_last_trade_date", None) == curr_date:
            return False, False, ""

        b1 = df.iloc[-2]  # Trigger bar (last closed bar)

        # 3. Asian Range Reference (07:00 - 13:30 Thai Time)
        asia_high, asia_low = 0.0, 0.0
        times = df.get('time')
        if times is not None and len(times) > 0 and hasattr(times.iloc[0], 'date') and curr_date is not None:
            asia_mask = (times.dt.date == curr_date) & (times.dt.time >= dtime(7, 0)) & (times.dt.time <= dtime(13, 30))
            asia_df = df[asia_mask]
            if len(asia_df) >= 8:
                asia_high = float(asia_df['high'].max())
                asia_low = float(asia_df['low'].min())

        if asia_high <= asia_low:
            asia_lookback = df.iloc[max(0, len(df) - 65) : -18]
            if len(asia_lookback) >= 10:
                asia_high = float(asia_lookback['high'].max())
                asia_low = float(asia_lookback['low'].min())
            else:
                return False, False, ""

        asia_range = asia_high - asia_low
        # Skip when Asian session is ultra compressed (< 4.0 USD), as London will expand trend rather than fakeout
        if asia_range < 4.0:
            return False, False, ""

        # M5 ATR calculation
        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift()).abs()
        lc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        m5_atr = float(tr.rolling(window=14).mean().iloc[-2]) if len(df) >= 15 else 2.0
        if math.isnan(m5_atr) or m5_atr <= 0: m5_atr = 2.0

        # 4. H1 Macro Trend Order Flow Alignment
        df_h1 = None
        if hasattr(self, 'connector') and hasattr(self.connector, 'get_rates'):
            try:
                df_h1 = self.connector.get_rates(symbol, "H1", 60)
            except Exception:
                df_h1 = None

        h1_bull = True
        h1_bear = True
        if df_h1 is not None and not df_h1.empty and len(df_h1) >= 20:
            df_h1_copy = df_h1.copy()
            df_h1_copy['ema50'] = df_h1_copy['close'].ewm(span=50, adjust=False).mean()
            df_h1_copy['ema200'] = df_h1_copy['close'].ewm(span=200, adjust=False).mean()
            h1_last = df_h1_copy.iloc[-1]
            h1_c = float(h1_last['close'])
            h1_e50 = float(h1_last['ema50'])
            h1_e200 = float(h1_last['ema200'])
            h1_bull = (h1_e50 >= h1_e200) or (h1_c >= h1_e50)
            h1_bear = (h1_e50 <= h1_e200) or (h1_c <= h1_e50)

        recent_bars = df.iloc[-18:-1]
        recent_high = float(recent_bars['high'].max())
        recent_low = float(recent_bars['low'].min())

        # 5. Bearish Judas QM (SELL):
        # - Swept Asia High (recent_high > asia_high + 0.20)
        # - Aligns with Bearish H1 Order Flow
        # - Left Shoulder exists before Head
        # - Decisive BOS displacement downwards past intermediate low
        # - First Time Back retest into QML
        if h1_bear and (recent_high > asia_high + 0.20) and ((recent_high - asia_high) <= 2.5 * m5_atr):
            head_idx = int(recent_bars['high'].argmax())
            if 2 <= head_idx <= len(recent_bars) - 3:
                left_shoulder_high = float(recent_bars['high'].iloc[:head_idx].max())
                ls_idx = int(recent_bars['high'].iloc[:head_idx].argmax())
                inter_low = float(recent_bars['low'].iloc[ls_idx : head_idx].min()) if ls_idx < head_idx else float(recent_bars['low'].iloc[:head_idx].min())
                post_head = recent_bars.iloc[head_idx:]
                broke = any(float(row['close']) < (inter_low - 0.20 * m5_atr) for _, row in post_head.iterrows())

                if recent_high > (left_shoulder_high + 0.15) and broke:
                    qml_price = left_shoulder_high
                    near_qml = abs(float(b1['high']) - qml_price) <= (0.70 * m5_atr)
                    rejection = (float(b1['close']) < float(b1['open'])) or (((float(b1['high']) - max(float(b1['open']), float(b1['close']))) / (float(b1['high']) - float(b1['low']) + 1e-9)) >= 0.25)
                    if near_qml and rejection:
                        if curr_date is not None:
                            self.judas_last_trade_date = curr_date
                        return False, True, f"🎯 ICT Judas RTM Bearish QM (Asia High Swept {recent_high:.2f} + QML {qml_price:.2f})"

        # 6. Bullish Judas QM (BUY):
        # - Swept Asia Low (recent_low < asia_low - 0.20)
        # - Aligns with Bullish H1 Order Flow
        # - Left Shoulder exists before Head
        # - Decisive BOS displacement upwards past intermediate high
        # - First Time Back retest into QML
        if h1_bull and (recent_low < asia_low - 0.20) and ((asia_low - recent_low) <= 2.5 * m5_atr):
            head_idx = int(recent_bars['low'].argmin())
            if 2 <= head_idx <= len(recent_bars) - 3:
                left_shoulder_low = float(recent_bars['low'].iloc[:head_idx].min())
                ls_idx = int(recent_bars['low'].iloc[:head_idx].argmin())
                inter_high = float(recent_bars['high'].iloc[ls_idx : head_idx].max()) if ls_idx < head_idx else float(recent_bars['high'].iloc[:head_idx].max())
                post_head = recent_bars.iloc[head_idx:]
                broke = any(float(row['close']) > (inter_high + 0.20 * m5_atr) for _, row in post_head.iterrows())

                if recent_low < (left_shoulder_low - 0.15) and broke:
                    qml_price = left_shoulder_low
                    near_qml = abs(float(b1['low']) - qml_price) <= (0.70 * m5_atr)
                    rejection = (float(b1['close']) > float(b1['open'])) or (((min(float(b1['open']), float(b1['close'])) - float(b1['low'])) / (float(b1['high']) - float(b1['low']) + 1e-9)) >= 0.25)
                    if near_qml and rejection:
                        if curr_date is not None:
                            self.judas_last_trade_date = curr_date
                        return True, False, f"🎯 ICT Judas RTM Bullish QM (Asia Low Swept {recent_low:.2f} + QML {qml_price:.2f})"

        return False, False, ""


    def _check_ict_silver_bullet_fvg(self, df: pd.DataFrame, symbol: str = "XAUUSD") -> Tuple[bool, bool, str]:
        """
        🔫 ICT NY Silver Bullet & FVG Imbalance (M5, NY AM Killzone 19:00 - 23:00 Thai Time)
        Synthesis of:
        - Time Window: 19:00 - 23:00 Thai Time (High liquidity US session)
        - Liquidity Run: Sweep of short-term High/Low of last 15-20 bars
        - Market Structure Shift (MSS) with Displacement candle (Body >= 52%)
        - Fair Value Gap (FVG): 3-bar imbalance (BISI/SIBI)
        - Consequent Encroachment (50% FVG retest) entry trigger
        """
        if len(df) < 30:
            return False, False, ""

        sim_time = getattr(self.connector, "current_time", None)
        if sim_time is not None and hasattr(sim_time, "time") and not hasattr(sim_time, "_mock_return_value"):
            now_time = sim_time.time()
        else:
            th_tz = timezone(timedelta(hours=7))
            now_time = datetime.now(th_tz).time()

        # Trading hours window (Default NY AM Session: 19:00 - 23:00 Thai Time)
        in_hours, _, _, _ = self.is_setup_in_trading_hours("ICT_SILVER_BULLET_FVG", now_time)
        if not in_hours:
            return False, False, ""

        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift()).abs()
        lc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        m5_atr = float(tr.rolling(window=14).mean().iloc[-2]) if len(df) >= 15 else 2.0
        if math.isnan(m5_atr) or m5_atr <= 0: m5_atr = 2.0

        min_fvg_size = max(0.50, 0.20 * m5_atr)

        b_anchor = df.iloc[-4]
        b_disp = df.iloc[-3]
        b_trig = df.iloc[-2]

        disp_h = float(b_disp['high'])
        disp_l = float(b_disp['low'])
        disp_o = float(b_disp['open'])
        disp_c = float(b_disp['close'])
        disp_range = disp_h - disp_l
        disp_body = abs(disp_c - disp_o)

        if disp_range < 0.60 or (disp_body / (disp_range + 1e-9)) < 0.50:
            return False, False, ""

        pool_high = float(df['high'].iloc[-20:-4].max())
        pool_low = float(df['low'].iloc[-20:-4].min())

        # 1. Bullish Silver Bullet FVG (BUY):
        if disp_c > disp_o:
            swept_ssl = float(df['low'].iloc[-10:-2].min()) <= pool_low + 0.15
            bar1_h = float(b_anchor['high'])
            fvg_gap = float(b_disp['close']) - bar1_h
            if swept_ssl and fvg_gap >= min_fvg_size:
                fvg_midpoint = bar1_h + (fvg_gap * 0.50)
                retested = float(b_trig['low']) <= fvg_midpoint + 0.35 and float(b_trig['close']) >= bar1_h - 0.25
                if retested:
                    return True, False, f"🔫 ICT NY Silver Bullet Bullish FVG (SSL Swept + FVG 50% CE @ {fvg_midpoint:.2f})"

        # 2. Bearish Silver Bullet FVG (SELL):
        if disp_c < disp_o:
            swept_bsl = float(df['high'].iloc[-10:-2].max()) >= pool_high - 0.15
            bar1_l = float(b_anchor['low'])
            fvg_gap = bar1_l - float(b_disp['close'])
            if swept_bsl and fvg_gap >= min_fvg_size:
                fvg_midpoint = bar1_l - (fvg_gap * 0.50)
                retested = float(b_trig['high']) >= fvg_midpoint - 0.35 and float(b_trig['close']) <= bar1_l + 0.25
                if retested:
                    return False, True, f"🔫 ICT NY Silver Bullet Bearish FVG (BSL Swept + FVG 50% CE @ {fvg_midpoint:.2f})"

        return False, False, ""

    def _check_ew_wave3_breaker(self, df: pd.DataFrame, symbol: str = "XAUUSD") -> Tuple[bool, bool, str]:
        """
        🌊 Elliott Wave 3 & SMC Breaker Propulsion (M5/M15, Trend Session 14:00 - 02:00 Thai Time)
        Synthesis of:
        - Elliott Wave Principle: Wave 3 Flagship Breakout (Peak Momentum, Asymmetry)
        - The 3 Inviolable Rules: Wave 2 never retraces > 100% of Wave 1 origin (Hard Stop)
        - SMC Breaker Block: Failed Wave 1/2 structure flipped to propulsion zone
        - Elliott Wave Oscillator (5/34) momentum expansion
        """
        if len(df) < 25:
            return False, False, ""

        sim_time = getattr(self.connector, "current_time", None)
        if sim_time is not None and hasattr(sim_time, "time") and not hasattr(sim_time, "_mock_return_value"):
            now_time = sim_time.time()
        else:
            th_tz = timezone(timedelta(hours=7))
            now_time = datetime.now(th_tz).time()

        # Trend hours window (Default: 14:00 - 02:00 Thai Time)
        in_hours, _, _, _ = self.is_setup_in_trading_hours("EW_WAVE3_BREAKER", now_time)
        if not in_hours:
            return False, False, ""

        b1 = df.iloc[-2]  # Trigger bar (last closed bar)
        b2 = df.iloc[-3]

        median_price = (df['high'] + df['low']) / 2.0
        ewo = median_price.rolling(window=5).mean() - median_price.rolling(window=34).mean()
        curr_ewo = float(ewo.iloc[-2]) if len(ewo) >= 35 else 0.0
        prev_ewo = float(ewo.iloc[-3]) if len(ewo) >= 35 else 0.0

        # BUY (Bullish Wave 3):
        p0_idx = int(df['low'].iloc[-25:-10].argmin()) + (len(df) - 25)
        p0_low = float(df['low'].iloc[p0_idx])

        p1_subset = df.iloc[p0_idx + 1 : -4]
        if len(p1_subset) >= 3:
            p1_idx = int(p1_subset['high'].argmax()) + (p0_idx + 1)
            p1_high = float(p1_subset['high'].max())

            p2_subset = df.iloc[p1_idx + 1 : -1]
            if len(p2_subset) >= 2:
                p2_low = float(p2_subset['low'].min())
                wave1_dist = p1_high - p0_low
                wave2_retrace = p1_high - p2_low

                # Rule 1 check: P2 > P0 (Never retrace 100%)
                if wave1_dist >= 2.00 and p2_low > p0_low:
                    retrace_ratio = wave2_retrace / wave1_dist
                    if 0.25 <= retrace_ratio <= 0.80:
                        # Breakout: b1 closed above Wave 1 High
                        if float(b1['close']) > p1_high and float(b2['close']) <= p1_high + 0.50:
                            if curr_ewo >= 0.0 or curr_ewo >= prev_ewo:
                                return True, False, f"🌊 Elliott Wave 3 Breaker Bullish (W1 Top {p1_high:.2f} Broken | Tactical SL @ W2 Low {p2_low:.2f})"

        # SELL (Bearish Wave 3):
        p0_sell_idx = int(df['high'].iloc[-25:-10].argmax()) + (len(df) - 25)
        p0_high = float(df['high'].iloc[p0_sell_idx])

        p1_sell_subset = df.iloc[p0_sell_idx + 1 : -4]
        if len(p1_sell_subset) >= 3:
            p1_sell_idx = int(p1_sell_subset['low'].argmin()) + (p0_sell_idx + 1)
            p1_sell_low = float(p1_sell_subset['low'].min())

            p2_sell_subset = df.iloc[p1_sell_idx + 1 : -1]
            if len(p2_sell_subset) >= 2:
                p2_sell_high = float(p2_sell_subset['high'].max())
                wave1_dist = p0_high - p1_sell_low
                wave2_retrace = p2_sell_high - p1_sell_low

                if wave1_dist >= 2.00 and p2_sell_high < p0_high:
                    retrace_ratio = wave2_retrace / wave1_dist
                    if 0.25 <= retrace_ratio <= 0.80:
                        if float(b1['close']) < p1_sell_low and float(b2['close']) >= p1_sell_low - 0.50:
                            if curr_ewo <= 0.0 or curr_ewo <= prev_ewo:
                                return False, True, f"🌊 Elliott Wave 3 Breaker Bearish (W1 Bottom {p1_sell_low:.2f} Broken | Tactical SL @ W2 High {p2_sell_high:.2f})"

        return False, False, ""

    def _check_smc_x_sto_h1(self, symbol: str) -> Tuple[bool, bool, str]:
        """
        😈 SMCxSTO ระบบปีศาจ (H1 Devil System by SMC by Bossz):
        1. Trend Filter: EMA 50 & EMA 200 on H1 (Uptrend: EMA 50 > EMA 200, Downtrend: EMA 50 < EMA 200).
        2. Pullback Filter: Uses ATR 14 to verify deep pullback >= 1.0x ATR into Discount/Premium zone.
        3. Single-Rule Order Block:
           - Buy OB: Last bearish candle before the bullish expansion that led to recent swing high.
           - Sell OB: Last bullish candle before the bearish expansion that led to recent swing low.
        4. Entry Trigger: Stochastic (14, 3, 3) Oversold (<= 28) / Overbought (>= 72) reversal cross.
        """
        try:
            df_h1 = self.connector.get_rates(symbol, "H1", 60)
            if df_h1 is None or df_h1.empty or len(df_h1) < 35:
                return False, False, ""

            h1_bar_time = df_h1['time'].iloc[-2]
            # 0. H1 Bar Lock: Max 1 trade per H1 bar to prevent over-trading
            if getattr(self, 'last_smc_sto_h1_bar_time', None) == h1_bar_time:
                return False, False, ""

            in_hours, _, _, _ = self.is_setup_in_trading_hours("SMC_X_STO_H1")
            if not in_hours:
                return False, False, ""

            # Indicators on H1
            df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
            df_h1['ema200'] = df_h1['close'].ewm(span=200, adjust=False).mean()

            # ATR 14
            high_low = df_h1['high'] - df_h1['low']
            high_close = (df_h1['high'] - df_h1['close'].shift()).abs()
            low_close = (df_h1['low'] - df_h1['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df_h1['atr14'] = tr.rolling(window=14).mean()

            # Stochastic (14, 3, 3)
            low14 = df_h1['low'].rolling(window=14).min()
            high14 = df_h1['high'].rolling(window=14).max()
            k_fast = 100 * ((df_h1['close'] - low14) / (high14 - low14 + 1e-9))
            df_h1['stoch_k'] = k_fast.rolling(window=3).mean()
            df_h1['stoch_d'] = df_h1['stoch_k'].rolling(window=3).mean()

            b1 = df_h1.iloc[-2]  # Last closed H1 candle
            b2 = df_h1.iloc[-3]  # Previous H1 candle
            curr_atr = float(b1['atr14']) if not pd.isna(b1['atr14']) else 5.0

            is_uptrend = (float(b1['ema50']) > float(b1['ema200']))
            is_downtrend = (float(b1['ema50']) < float(b1['ema200']))

            lookback = df_h1.iloc[-22:-2] # Lookback for swing and OB

            # --- BULLISH (BUY) SETUP ---
            if is_uptrend:
                swing_high = float(lookback['high'].max())
                pullback_dist = swing_high - float(b1['low'])
                
                # Check 1: Must pull back at least 1.0x ATR from swing high (Discount Zone)
                if pullback_dist >= (1.0 * curr_atr):
                    # Check 2: Single-Rule Bullish Order Block WITH FVG Imbalance / Displacement
                    # Search lookback for last bearish candle followed by strong expansion and FVG
                    valid_ob = None
                    for i in range(len(lookback) - 3, -1, -1):
                        c0 = lookback.iloc[i]
                        c1 = lookback.iloc[i+1]
                        c2 = lookback.iloc[i+2]
                        # c0 is bearish (OB candidate)
                        if c0['close'] < c0['open']:
                            # c1 is bullish expansion (displacement)
                            if c1['close'] > c1['open']:
                                fvg_gap = float(c2['low']) - float(c0['high'])
                                # Valid if genuine FVG gap or displacement expansion
                                has_fvg = fvg_gap >= 0.20 or (float(c1['close']) - float(c0['high'])) >= (0.65 * curr_atr)
                                if has_fvg:
                                    valid_ob = {
                                        "low": float(c0['low']),
                                        "high": float(c0['high']),
                                        "fvg_high": max(float(c2['low']), float(c1['close'])),
                                        "has_fvg": fvg_gap >= 0.20
                                    }
                                    break
                    
                    if valid_ob:
                        ob_low = valid_ob["low"]
                        ob_high = valid_ob["high"]
                        fvg_zone_high = valid_ob["fvg_high"]
                        
                        # Price tested the Order Block or FVG zone
                        price_in_ob = (float(b1['low']) <= (max(ob_high, fvg_zone_high) + 0.3 * curr_atr)) and (float(b1['close']) >= (ob_low - 0.2 * curr_atr))
                        
                        if price_in_ob:
                            # Liquidity Sweep / Lower Wick Rejection Confirmation:
                            # Ensure sell-side liquidity was swept (price dipped below previous candle low or pierced OB)
                            # AND showed rejection with lower wick >= 25% of candle range
                            candle_range = max(float(b1['high']) - float(b1['low']), 0.1)
                            lower_wick = min(float(b1['open']), float(b1['close'])) - float(b1['low'])
                            has_rejection = (lower_wick / candle_range) >= 0.25 or (float(b1['low']) < float(b2['low']))

                            # Check 3: Stochastic Trigger (Oversold <= 28 and %K cross above %D)
                            was_oversold = (float(b2['stoch_k']) <= 28) or (float(b1['stoch_k']) <= 30)
                            stoch_cross_up = (float(b1['stoch_k']) > float(b1['stoch_d'])) and (float(b2['stoch_k']) <= float(b2['stoch_d']))
                            
                            if was_oversold and stoch_cross_up and (float(b1['close']) > float(b1['open'])) and has_rejection:
                                self.last_smc_sto_h1_bar_time = h1_bar_time
                                return True, False, "😈 SMCxSTO: H1 Discount OB + FVG Imbalance Rebound (BUY)"

            # --- BEARISH (SELL) SETUP ---
            if is_downtrend:
                swing_low = float(lookback['low'].min())
                pullback_dist = float(b1['high']) - swing_low
                
                # Check 1: Must rally at least 1.0x ATR from swing low (Premium Zone)
                if pullback_dist >= (1.0 * curr_atr):
                    # Check 2: Single-Rule Bearish Order Block WITH FVG Imbalance / Displacement
                    valid_ob = None
                    for i in range(len(lookback) - 3, -1, -1):
                        c0 = lookback.iloc[i]
                        c1 = lookback.iloc[i+1]
                        c2 = lookback.iloc[i+2]
                        # c0 is bullish (OB candidate)
                        if c0['close'] > c0['open']:
                            # c1 is bearish expansion (displacement)
                            if c1['close'] < c1['open']:
                                fvg_gap = float(c0['low']) - float(c2['high'])
                                has_fvg = fvg_gap >= 0.20 or (float(c0['low']) - float(c1['close'])) >= (0.65 * curr_atr)
                                if has_fvg:
                                    valid_ob = {
                                        "low": float(c0['low']),
                                        "high": float(c0['high']),
                                        "fvg_low": min(float(c2['high']), float(c1['close'])),
                                        "has_fvg": fvg_gap >= 0.20
                                    }
                                    break
                    
                    if valid_ob:
                        ob_low = valid_ob["low"]
                        ob_high = valid_ob["high"]
                        fvg_zone_low = valid_ob["fvg_low"]
                        
                        # Price tested the Order Block or FVG zone
                        price_in_ob = (float(b1['high']) >= (min(ob_low, fvg_zone_low) - 0.3 * curr_atr)) and (float(b1['close']) <= (ob_high + 0.2 * curr_atr))
                        
                        if price_in_ob:
                            # Liquidity Sweep / Upper Wick Rejection Confirmation:
                            candle_range = max(float(b1['high']) - float(b1['low']), 0.1)
                            upper_wick = float(b1['high']) - max(float(b1['open']), float(b1['close']))
                            has_rejection = (upper_wick / candle_range) >= 0.25 or (float(b1['high']) > float(b2['high']))

                            # Check 3: Stochastic Trigger (Overbought >= 72 and %K cross below %D)
                            was_overbought = (float(b2['stoch_k']) >= 72) or (float(b1['stoch_k']) >= 70)
                            stoch_cross_down = (float(b1['stoch_k']) < float(b1['stoch_d'])) and (float(b2['stoch_k']) >= float(b2['stoch_d']))
                            
                            if was_overbought and stoch_cross_down and (float(b1['close']) < float(b1['open'])) and has_rejection:
                                self.last_smc_sto_h1_bar_time = h1_bar_time
                                return False, True, "😈 SMCxSTO: H1 Premium OB + FVG Imbalance Rebound (SELL)"

        except Exception as e:
            logger.error(f"Error evaluating SMCxSTO H1 strategy: {e}")

        return False, False, ""

    def _check_rtm_confluence_m15(self, symbol: str) -> dict:
        """
        👑 RTM Quasimodo Multi-Model Institutional Engine (M15 Sweet Spot + H1 Trend Filter):
        1. Macro Filter: H1 EMA 50 vs EMA 200 trend alignment.
        2. Market Structure: Detects Quasimodo reversal (HH -> LL -> Retest Left Shoulder for SELL,
           or LL -> HH -> Retest Left Shoulder for BUY) using 5-bar fractal pivots.
        3. Confluence Pillars:
           - ICT Kill Zones (London 14-17 Thai, NY 19-23 Thai)
           - Fibonacci OTE Golden Zone (61.8% - 78.6%)
           - Price Action Rejection (Pinbar with wick >= 35% or Engulfing)
        4. Quality Grading:
           - Grade A+ (Score >= 85)
           - Grade A  (Score 70 - 84)
           - Grade B  (Score 50 - 69)
        """
        try:
            df_m15 = self.connector.get_rates(symbol, "M15", 70)
            df_h1 = self.connector.get_rates(symbol, "H1", 60)
            if df_m15 is None or df_m15.empty or len(df_m15) < 35:
                return {}
            if df_h1 is None or df_h1.empty or len(df_h1) < 25:
                return {}

            m15_bar_time = df_m15['time'].iloc[-2]
            # M15 Bar Lock: Max 1 evaluation per closed M15 candle
            if getattr(self, 'last_rtm_m15_bar_time', None) == m15_bar_time:
                return {}

            in_hours, _, _, _ = self.is_setup_in_trading_hours("RTM_M6_ELITE_GROWTH")
            if not in_hours:
                return {}

            # 1. H1 Trend
            df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
            df_h1['ema200'] = df_h1['close'].ewm(span=200, adjust=False).mean()
            h1_trend = 1 if float(df_h1['ema50'].iloc[-2]) > float(df_h1['ema200'].iloc[-2]) else (-1 if float(df_h1['ema50'].iloc[-2]) < float(df_h1['ema200'].iloc[-2]) else 0)

            # 2. M15 ATR 14
            hl = df_m15['high'] - df_m15['low']
            hc = (df_m15['high'] - df_m15['close'].shift()).abs()
            lc = (df_m15['low'] - df_m15['close'].shift()).abs()
            tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            atr14 = tr.rolling(window=14).mean()
            curr_atr = float(atr14.iloc[-2]) if not pd.isna(atr14.iloc[-2]) else 3.5

            # 3. M15 Pivots (window=5)
            highs_s = df_m15['high'].iloc[:-1]
            lows_s = df_m15['low'].iloc[:-1]
            
            p_highs = {}
            p_lows = {}
            for idx in range(5, len(highs_s) - 5):
                val_h = float(highs_s.iloc[idx])
                val_l = float(lows_s.iloc[idx])
                if val_h == float(highs_s.iloc[idx-5:idx+6].max()):
                    p_highs[idx] = val_h
                if val_l == float(lows_s.iloc[idx-5:idx+6].min()):
                    p_lows[idx] = val_l

            s_high_items = sorted(list(p_highs.items()), key=lambda x: x[0])
            s_low_items = sorted(list(p_lows.items()), key=lambda x: x[0])

            if len(s_high_items) < 2 or len(s_low_items) < 2:
                return {}

            b1 = df_m15.iloc[-2] # Closed M15 candle
            c = float(b1['close'])
            h = float(b1['high'])
            l = float(b1['low'])
            o = float(b1['open'])
            candle_range = max(h - l, 0.1)

            # 4. ICT Kill Zones (Thai time UTC+7: London 14-17, NY 19-23)
            now_hour = (datetime.utcnow().hour + 7) % 24
            in_kz = (14 <= now_hour <= 17) or (19 <= now_hour <= 23)

            # 5. Check Bearish Quasimodo (SELL)
            # High1 (QML) -> Low1 -> High2 (HH - Head) -> Low2 (LL - Breakout) -> Retest QML
            idx_qml, qml_high = s_high_items[-2]
            idx_head, head_hh = s_high_items[-1]
            idx_low1, low1 = s_low_items[-2]
            idx_break, break_ll = s_low_items[-1]

            if head_hh > qml_high and break_ll < low1 and idx_qml < idx_head and idx_head < idx_break:
                # 1. Calculate Refined MPL (Maximum Pain Level)
                ls_cluster = df_m15.iloc[max(0, idx_qml-2) : min(len(df_m15), idx_qml+3)]
                mpl_price = float(ls_cluster[['open', 'close']].max().max())

                # 2. Check FTB (First Time Back) - Ensure no prior bounce from QML
                is_ftb = True
                if (idx_break + 1) < (len(df_m15) - 3):
                    prior_bars = df_m15.iloc[idx_break + 1 : -2]
                    touched = False
                    for _, p_row in prior_bars.iterrows():
                        if p_row['high'] >= (min(qml_high, mpl_price) - 0.3 * curr_atr):
                            touched = True
                        elif touched and p_row['low'] <= (min(qml_high, mpl_price) - 1.2 * curr_atr):
                            is_ftb = False
                            break

                # Only trade pristine First Time Back (FTB) setups (Alchemist Trading Rule)
                if not is_ftb:
                    return {}

                # Check price retest at Left Shoulder QML / MPL Zone
                retest_lower = min(qml_high, mpl_price)
                near_zone = abs(h - qml_high) <= (0.65 * curr_atr) or (h >= retest_lower - 0.3 * curr_atr and c >= retest_lower - 0.4 * curr_atr)
                if near_zone:
                    score = 40.0
                    if in_kz: score += 20.0
                    swing_range = head_hh - break_ll
                    if swing_range > 0:
                        fib_ratio = (qml_high - break_ll) / swing_range
                        if 0.58 <= fib_ratio <= 0.82: score += 20.0
                    
                    has_rejection = (h - max(c, o)) >= (0.35 * candle_range) or (c < o and (o - c) >= (0.4 * candle_range))
                    if has_rejection: score += 15.0
                    if h1_trend == -1: score += 10.0
                    if abs(qml_high - mpl_price) <= (0.35 * curr_atr): score += 5.0

                    if score >= 50.0:
                        grade = "A+" if score >= 85.0 else ("A" if score >= 70.0 else "B")
                        # EarthETC Structural SL: Head extreme + minimum 1.50 USD (150 pts) buffer
                        sl_buf = max(0.4 * curr_atr, 1.50)
                        stop_loss = head_hh + sl_buf
                        self.last_rtm_m15_bar_time = m15_bar_time
                        return {
                            "action": "SELL",
                            "score": score,
                            "grade": grade,
                            "sl": stop_loss,
                            "m15_time": m15_bar_time,
                            "reason": f"RTM Quasimodo Bearish QML/MPL [FTB {grade}] ({score:.0f} pts)",
                            "qml_price": qml_high,
                            "mpl_price": mpl_price,
                            "head_extreme": head_hh,
                            "break_level": break_ll,
                            "signal_close": c,
                            "curr_atr": curr_atr,
                            "is_ftb": is_ftb
                        }

            # 6. Check Bullish Quasimodo (BUY)
            # Low1 (QML) -> High1 -> Low2 (LL - Head) -> High2 (HH - Breakout) -> Retest QML
            idx_qml, qml_low = s_low_items[-2]
            idx_head, head_ll = s_low_items[-1]
            idx_high1, high1 = s_high_items[-2]
            idx_break, break_hh = s_high_items[-1]

            if head_ll < qml_low and break_hh > high1 and idx_qml < idx_head and idx_head < idx_break:
                # 1. Calculate Refined MPL (Maximum Pain Level)
                ls_cluster = df_m15.iloc[max(0, idx_qml-2) : min(len(df_m15), idx_qml+3)]
                mpl_price = float(ls_cluster[['open', 'close']].min().min())

                # 2. Check FTB (First Time Back) - Ensure no prior bounce from QML
                is_ftb = True
                if (idx_break + 1) < (len(df_m15) - 3):
                    prior_bars = df_m15.iloc[idx_break + 1 : -2]
                    touched = False
                    for _, p_row in prior_bars.iterrows():
                        if p_row['low'] <= (max(qml_low, mpl_price) + 0.3 * curr_atr):
                            touched = True
                        elif touched and p_row['high'] >= (max(qml_low, mpl_price) + 1.2 * curr_atr):
                            is_ftb = False
                            break

                # Only trade pristine First Time Back (FTB) setups (Alchemist Trading Rule)
                if not is_ftb:
                    return {}

                retest_upper = max(qml_low, mpl_price)
                near_zone = abs(l - qml_low) <= (0.65 * curr_atr) or (l <= retest_upper + 0.3 * curr_atr and c <= retest_upper + 0.4 * curr_atr)
                if near_zone:
                    score = 40.0
                    if in_kz: score += 20.0
                    swing_range = break_hh - head_ll
                    if swing_range > 0:
                        fib_ratio = (break_hh - qml_low) / swing_range
                        if 0.58 <= fib_ratio <= 0.82: score += 20.0

                    has_rejection = (min(c, o) - l) >= (0.35 * candle_range) or (c > o and (c - o) >= (0.4 * candle_range))
                    if has_rejection: score += 15.0
                    if h1_trend == 1: score += 10.0
                    if abs(qml_low - mpl_price) <= (0.35 * curr_atr): score += 5.0

                    if score >= 50.0:
                        grade = "A+" if score >= 85.0 else ("A" if score >= 70.0 else "B")
                        # EarthETC Structural SL: Head extreme - minimum 1.50 USD (150 pts) buffer
                        sl_buf = max(0.4 * curr_atr, 1.50)
                        stop_loss = head_ll - sl_buf
                        self.last_rtm_m15_bar_time = m15_bar_time
                        return {
                            "action": "BUY",
                            "score": score,
                            "grade": grade,
                            "sl": stop_loss,
                            "m15_time": m15_bar_time,
                            "reason": f"RTM Quasimodo Bullish QML/MPL [FTB {grade}] ({score:.0f} pts)",
                            "qml_price": qml_low,
                            "mpl_price": mpl_price,
                            "head_extreme": head_ll,
                            "break_level": break_hh,
                            "signal_close": c,
                            "curr_atr": curr_atr,
                            "is_ftb": is_ftb
                        }

        except Exception as e:
            logger.error(f"Error checking RTM Confluence M15: {e}")

        return {}

    def _update_rtm_sl_cooldown(self):
        """Scans recent MT5 deals within the last 30 minutes to check if any RTM model took an SL."""
        if not MT5_AVAILABLE:
            return
        try:
            from_dt = datetime.now() - timedelta(minutes=30)
            deals = mt5.history_deals_get(from_dt, datetime.now() + timedelta(minutes=1))
            if deals:
                rtm_magics = {777004, 777014, 777005, 777015, 777006, 777016, 777007, 777017}
                for d in deals:
                    if d.magic in rtm_magics and d.entry in [1, 2, 3]:
                        if float(d.profit) < 0:
                            pos_direction = "BUY" if d.type == 1 else "SELL"
                            deal_time = float(d.time)
                            if deal_time > self.last_rtm_sl_time.get(pos_direction, 0.0):
                                self.last_rtm_sl_time[pos_direction] = deal_time
        except Exception:
            pass

    def _check_rtm_clustering(self, symbol: str, proposed_price: float, min_gap: float = 1.50) -> bool:
        """
        Anti-Clustering Guard:
        Prevents multiple RTM models from piling onto the exact same price level.
        Returns True if SAFE to open (no existing RTM position within min_gap USD).
        Returns False if CLUSTERED (too close to an existing RTM position).
        """
        positions = self.connector.get_open_positions(symbol)
        rtm_magics = {777004, 777014, 777005, 777015, 777006, 777016, 777007, 777017}
        open_rtm = [p for p in positions if p.get('magic') in rtm_magics]
        for p in open_rtm:
            open_p = p.get('price_open', 0.0)
            if open_p > 0 and abs(proposed_price - open_p) < min_gap:
                return False
        return True

    def _process_rtm_confluence_engine(self, df: pd.DataFrame, symbol: str, spread: float, rtm_mode: str = "ALL"):
        """
        Dispatches RTM signals with Staggered Deep-Pullback & Anti-Clustering Architecture:
        - M5 (All-Weather): Immediate Vanguard Scout with rapid Break-Even lock
        - M4 (Conservative): Waits for genuine QML Retest (>= 1.5 USD better price)
        - M6 (Elite Growth): Waits for deep OTE Golden Zone (Fib 61.8% - 78.6%)
        - M7 (Max Alpha): Waits for M5 Micro-Structure Confirmation
        """
        sig = self._check_rtm_confluence_m15(symbol)
        if not sig:
            return

        action = sig["action"]
        grade = sig["grade"]
        score = sig["score"]
        sl = sig["sl"]
        reason = sig["reason"]

        # 1. Check Post-SL Directional Cooldown (15-min pause for same direction)
        self._update_rtm_sl_cooldown()
        last_sl_t = self.last_rtm_sl_time.get(action, 0.0)
        cooldown_rem = (last_sl_t + 900) - time.time()
        if cooldown_rem > 0:
            self.add_log(f"🛡️ [RTM COOLDOWN ACTIVE] {action} paused ({cooldown_rem:.0f}s left) after recent Stop Loss to prevent stop hunt sweep", "WARNING")
            return

        # 2. Register active RTM setup for staggered entries (M4 & M6 only)
        self.active_rtm_setup = {
            "action": action,
            "grade": grade,
            "score": score,
            "sl": sl,
            "reason": reason,
            "qml_price": sig.get("qml_price", 0.0),
            "mpl_price": sig.get("mpl_price", sig.get("qml_price", 0.0)),
            "head_extreme": sig.get("head_extreme", 0.0),
            "break_level": sig.get("break_level", 0.0),
            "signal_close": sig.get("signal_close", 0.0),
            "curr_atr": sig.get("curr_atr", 3.5),
            "created_time": time.time(),
            "expiry_time": time.time() + (45 * 60), # 45 minutes
            "rtm_mode": rtm_mode,
            "m4_filled": False,
            "m6_filled": False,
            "is_ftb": sig.get("is_ftb", True)
        }

        self.add_log(f"⏳ [RTM PULLBACK DUO QUEUE] Staggered monitoring active for M4 (QML/MPL Retest) & M6 (OTE Zone) | QML: {sig.get('qml_price', 0.0):.2f} MPL: {sig.get('mpl_price', 0.0):.2f}", "INFO")

    def _pass_rtm_ai_quality_gate(self, rates_m5: pd.DataFrame, symbol: str, strat_id: str, action: str, base_lot_m: float) -> Tuple[bool, dict]:
        """
        AI Quality Gate for RTM M4 and M6:
        1. Evaluates MarketRegimeScorer confluence (volume, spread, trend alignment).
        2. Evaluates RealTimeStrategyOptimizer dynamic parameters (streak, cooldown).
        3. Returns (is_allowed, opt_params) with combined lot_multiplier and dynamic tp_ratio.
        """
        spread = self.connector.get_market_info(symbol).get("spread", 20.0)
        score_res = self.scorer.evaluate_market_confluence(rates_m5, spread, strat_id)
        if not score_res.get("is_allowed", True):
            self.scorer.record_filtered_trade(strat_id, score_res)
            self.add_log(f"🛡️ [QUALITY FILTERED] {strat_id} ({action}) Skipped | Score: {score_res['score']}/100 ({score_res['grade']}) | {score_res.get('pillars', {}).get('volume', {}).get('desc', '')}", "WARNING")
            self.latest_trend = f"FILTERED ({strat_id}: Score {score_res['score']}/100)"
            return False, {}

        opt_params = self.optimizer.get_dynamic_rr_and_parameters(strat_id, rates_m5)
        if not opt_params.get("should_execute", True):
            self.latest_trend = f"AI PAUSED ({strat_id}: {opt_params.get('reason', 'Blocked')})"
            return False, {}

        # Combine base lot multiplier with AI lot multiplier and signal grade bonus
        ai_lot_m = opt_params.get("lot_multiplier", 1.0)
        grade_bonus = score_res.get("lot_recommendation", 1.0) if score_res.get("grade") == "A+" else 1.0
        combined_lot_m = max(0.25, round(base_lot_m * ai_lot_m * grade_bonus, 2))
        opt_params["lot_multiplier"] = combined_lot_m
        return True, opt_params

    def _check_and_execute_pending_rtm_pullbacks(self, symbol: str, rates: Optional[pd.DataFrame] = None):
        """
        Staggered Deep-Pullback & Anti-Clustering Execution Engine:
        Continuously evaluates pending RTM setups across ticks/bars to fill:
        - M4 (Conservative): Genuine Pullback / Retest of QML/MPL level (at least 1.5 USD better than breakout)
        - M6 (Elite Growth): Deep OTE Retest (Fib 61.8% - 78.6%)
        - M7 (Max Alpha): M5 Micro-Structure Confirmation
        """
        if not self.active_rtm_setup:
            return

        setup = self.active_rtm_setup
        now = time.time()

        # 1. Check Expiry (45 minutes)
        if now > setup.get("expiry_time", 0):
            self.add_log(f"⌛ [RTM SETUP EXPIRED] Pullback setup for {setup['action']} timed out after 45m", "INFO")
            self.active_rtm_setup = None
            return

        action = setup["action"]
        sl = setup["sl"]
        qml_price = setup["qml_price"]
        mpl_price = setup.get("mpl_price", qml_price)
        head_extreme = setup["head_extreme"]
        signal_close = setup["signal_close"]
        curr_atr = setup["curr_atr"]
        rtm_mode = setup.get("rtm_mode", "ALL")
        grade = setup["grade"]

        m_info = self.connector.get_market_info(symbol)
        bid = m_info.get("bid", 0.0)
        ask = m_info.get("ask", 0.0)
        if bid <= 0 or ask <= 0:
            return

        curr_price = ask if action == "BUY" else bid

        # 2. Check Invalidation: Did price breach the Stop Loss before pullback filled?
        if action == "BUY" and bid <= sl:
            self.add_log(f"🚫 [RTM SETUP INVALIDATED] Price hit SL level ({sl:.2f}) before pullback filled. Pending entries cancelled.", "WARNING")
            self.active_rtm_setup = None
            return
        elif action == "SELL" and ask >= sl:
            self.add_log(f"🚫 [RTM SETUP INVALIDATED] Price hit SL level ({sl:.2f}) before pullback filled. Pending entries cancelled.", "WARNING")
            self.active_rtm_setup = None
            return

        # 3. Check Target Reached: Did price run away and hit 1.5R target without pulling back?
        target_dist = abs(signal_close - sl) * 1.5
        if action == "BUY" and bid >= signal_close + target_dist:
            self.add_log(f"🎯 [RTM PULLBACK CANCELLED] Price ran +1.5R away without retracing. Cancelling chase.", "INFO")
            self.active_rtm_setup = None
            return
        elif action == "SELL" and ask <= signal_close - target_dist:
            self.add_log(f"🎯 [RTM PULLBACK CANCELLED] Price ran +1.5R away without retracing. Cancelling chase.", "INFO")
            self.active_rtm_setup = None
            return

        rates_m5 = rates if rates is not None and not rates.empty else self.connector.get_rates(symbol, "M5", 25)
        if rates_m5 is None or rates_m5.empty or len(rates_m5) < 5:
            return

        # --- MODEL 4 (Conservative): Genuine Pullback / QML & MPL Retest ---
        strat_cfg = self.config.get("strategy", {})
        m4_enabled = strat_cfg.get("rtm_m4_enabled", True)
        if m4_enabled and rtm_mode in ["ALL", "MODEL_4", "PULLBACK_DUO"] and grade in ["A+", "A", "B"] and not setup["m4_filled"]:
            if not self.has_open_positions_for_setup(symbol, "RTM_M4_CONSERVATIVE"):
                is_m4_pullback = False
                dist_saved = 0.0
                b1 = rates_m5.iloc[-1]
                b_closed = rates_m5.iloc[-2] if len(rates_m5) >= 2 else b1
                c_rng = max(float(b_closed['high']) - float(b_closed['low']), 0.1)

                if action == "BUY":
                    dist_saved = signal_close - bid
                    zone_top = max(qml_price, mpl_price)
                    zone_bot = min(qml_price, mpl_price)
                    near_qml = (zone_bot - 0.4 * curr_atr <= bid <= zone_top + 0.4 * curr_atr) or (abs(bid - qml_price) <= (0.75 * curr_atr)) or bid <= qml_price + 0.80
                    retrace_ok = near_qml or (bid <= signal_close - (0.25 * curr_atr)) or (abs(bid - signal_close) <= 1.0)
                    lower_wick = min(float(b_closed['open']), float(b_closed['close'])) - float(b_closed['low'])
                    rejection_ok = ((lower_wick / c_rng) >= 0.28) or (float(b_closed['close']) > float(b_closed['open'])) or (bid > float(b_closed['high']))
                    is_m4_pullback = retrace_ok and rejection_ok and (bid >= float(b1['low']))
                elif action == "SELL":
                    dist_saved = ask - signal_close
                    zone_top = max(qml_price, mpl_price)
                    zone_bot = min(qml_price, mpl_price)
                    near_qml = (zone_bot - 0.4 * curr_atr <= ask <= zone_top + 0.4 * curr_atr) or (abs(ask - qml_price) <= (0.75 * curr_atr)) or ask >= qml_price - 0.80
                    retrace_ok = near_qml or (ask >= signal_close + (0.25 * curr_atr)) or (abs(ask - signal_close) <= 1.0)
                    upper_wick = float(b_closed['high']) - max(float(b_closed['open']), float(b_closed['close']))
                    rejection_ok = ((upper_wick / c_rng) >= 0.28) or (float(b_closed['close']) < float(b_closed['open'])) or (ask < float(b_closed['low']))
                    is_m4_pullback = retrace_ok and rejection_ok and (ask <= float(b1['high']))

                if is_m4_pullback and self._check_rtm_clustering(symbol, curr_price, min_gap=1.50):
                    # Grade B trades at conservative 1.0% risk, Grade A/A+ at 2.0% risk
                    lot_m = 0.5 if grade == "B" else 1.0
                    passed, opt = self._pass_rtm_ai_quality_gate(rates_m5, symbol, "RTM_M4_CONSERVATIVE", action, lot_m)
                    if passed:
                        opt["custom_sl"] = sl
                        dynamic_tp = opt.get("tp_ratio", 2.0)
                        if action == "BUY":
                            self.execute_buy(rates_m5, symbol, f"🛡️ RTM M4 (Conservative Pullback Retest [{grade}] @ {curr_price:.2f} | Dynamic {dynamic_tp}R)", opt_params=opt, strat_id="RTM_M4_CONSERVATIVE")
                        else:
                            self.execute_sell(rates_m5, symbol, f"🛡️ RTM M4 (Conservative Pullback Retest [{grade}] @ {curr_price:.2f} | Dynamic {dynamic_tp}R)", opt_params=opt, strat_id="RTM_M4_CONSERVATIVE")
                        setup["m4_filled"] = True
                        self.add_log(f"🛡️ [RTM M4 FILLED] Conservative QML Pullback executed @ {curr_price:.2f} (Grade {grade} | TP: {dynamic_tp}R | LotMult: {opt.get('lot_multiplier', 1.0):.2f}x)", "SUCCESS")

        # --- MODEL 6 (Elite Growth): Institutional Sweet Spot (Fib 50.0% - 65.0%) ---
        m6_enabled = strat_cfg.get("rtm_m6_enabled", True)
        if m6_enabled and rtm_mode in ["ALL", "MODEL_6", "PULLBACK_DUO"] and grade in ["A+", "A", "B"] and not setup["m6_filled"]:
            if not self.has_open_positions_for_setup(symbol, "RTM_M6_ELITE_GROWTH"):
                is_m6_ote = False
                break_level = setup.get("break_level", 0.0)
                if break_level > 0 and head_extreme > 0:
                    impulse_range = abs(break_level - head_extreme)
                    if impulse_range >= (1.0 * curr_atr):
                        b_closed = rates_m5.iloc[-2] if len(rates_m5) >= 2 else rates_m5.iloc[-1]
                        c_rng = max(float(b_closed['high']) - float(b_closed['low']), 0.1)
                        if action == "BUY":
                            # Institutional Golden Pocket Sweet Spot: 50.0% - 65.0%
                            ote_high = break_level - (0.50 * impulse_range)
                            ote_low = break_level - (0.65 * impulse_range)
                            in_zone = (ote_low - 0.50) <= bid <= (ote_high + 0.50) and bid >= sl + 1.0
                            lower_wick = min(float(b_closed['open']), float(b_closed['close'])) - float(b_closed['low'])
                            rejection_ok = ((lower_wick / c_rng) >= 0.28) or (float(b_closed['close']) > float(b_closed['open'])) or (bid > float(b_closed['high']))
                            is_m6_ote = in_zone and rejection_ok
                        elif action == "SELL":
                            ote_low = break_level + (0.50 * impulse_range)
                            ote_high = break_level + (0.65 * impulse_range)
                            in_zone = (ote_low - 0.50) <= ask <= (ote_high + 0.50) and ask <= sl - 1.0
                            upper_wick = float(b_closed['high']) - max(float(b_closed['open']), float(b_closed['close']))
                            rejection_ok = ((upper_wick / c_rng) >= 0.28) or (float(b_closed['close']) < float(b_closed['open'])) or (ask < float(b_closed['low']))
                            is_m6_ote = in_zone and rejection_ok

                if is_m6_ote and self._check_rtm_clustering(symbol, curr_price, min_gap=1.50):
                    lot_m = 0.5 if grade == "B" else (1.5 if grade == "A+" else 1.0)
                    passed, opt = self._pass_rtm_ai_quality_gate(rates_m5, symbol, "RTM_M6_ELITE_GROWTH", action, lot_m)
                    if passed:
                        opt["custom_sl"] = sl
                        dynamic_tp = opt.get("tp_ratio", 2.0)
                        if action == "BUY":
                            self.execute_buy(rates_m5, symbol, f"👑 RTM M6 (Golden Pocket Retest Fib 50-65% [{grade}] @ {curr_price:.2f} | Dynamic {dynamic_tp}R)", opt_params=opt, strat_id="RTM_M6_ELITE_GROWTH")
                        else:
                            self.execute_sell(rates_m5, symbol, f"👑 RTM M6 (Golden Pocket Retest Fib 50-65% [{grade}] @ {curr_price:.2f} | Dynamic {dynamic_tp}R)", opt_params=opt, strat_id="RTM_M6_ELITE_GROWTH")
                        setup["m6_filled"] = True
                        self.add_log(f"👑 [RTM M6 FILLED] Elite Growth OTE Golden Pocket executed @ {curr_price:.2f} (Grade {grade} | TP: {dynamic_tp}R | LotMult: {opt.get('lot_multiplier', 1.0):.2f}x)", "SUCCESS")

        # If all eligible models (M4 and M6) are filled, clear active setup
        all_done = True
        if m4_enabled and rtm_mode in ["ALL", "MODEL_4", "PULLBACK_DUO"] and grade in ["A+", "A", "B"] and not setup.get("m4_filled", False):
            all_done = False
        if m6_enabled and rtm_mode in ["ALL", "MODEL_6", "PULLBACK_DUO"] and grade in ["A+", "A", "B"] and not setup.get("m6_filled", False):
            all_done = False

        if all_done:
            self.active_rtm_setup = None

    def should_run_trend(self, strat_id: str, df: pd.DataFrame, session: str) -> Tuple[bool, str]:
        """
        AI Trend Intelligence Classifier:
        Analyzes whether the current setup warrants an uncapped Trend Runner (Trailing Stop)
        or should take Fixed Targets (TP1, TP2) without trailing.
        """
        # 1. Asian Session / Mean Reversion -> Strict Fixed TP (No Trailing)
        if strat_id == "ASIAN_RANGE_SNIPER" or session == "ASIAN SESSION":
            return False, "Fixed TP (Asian Sideways - No Trailing)"

        # 2. News Expansion -> High Momentum Trend Runner
        if strat_id == "NEWS_MOMENTUM_EXPANSION":
            return True, "AI Trend Trail (News Expansion)"

        # 3. SMCxSTO H1 Devil System -> High R:R Runner (Trailing Stop)
        if strat_id == "SMC_X_STO_H1":
            return True, "AI Trend Trail (SMCxSTO H1 Devil System)"

        # 4. RTM Quasimodo Multi-Model Engine -> High R:R Runner (Trailing Stop)
        if strat_id.startswith("RTM_"):
            return True, "AI Trend Trail (RTM Quasimodo High R:R Runner)"

        # 5. Fallback: Check Market Regime
        regime = self.optimizer.classify_market_regime(df)
        if "TREND" in regime.get("regime", "") or regime.get("volatility_ratio", 1.0) >= 1.25:
            return True, f"AI Trend Trail ({regime.get('label', 'Trending Expansion')})"

        return False, "Fixed TP (Normal S/R Targets)"

    def execute_buy(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None, strat_id: str = "PULLBACK_DR_EKK", **kwargs):
        ask = self.connector.get_market_info(symbol).get("ask", 0.0)
        if ask <= 0: return

        opt = opt_params or {}
        sl_mult = opt.get("atr_sl_multiplier", 1.0)
        lot_mult = opt.get("lot_multiplier", 1.0)

        m_info = self.get_magic_for_strategy(strat_id)
        magic_p1 = m_info["pos1"]

        if is_asian_scalp or strat_id == "ASIAN_RANGE_SNIPER":
            lowest_low = df['low'].iloc[-6:-1].min()
            sl_buffer = 0.40 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 2.80: sl = ask - 2.80; sl_dist = 2.80
            if sl_dist > 5.00: sl = ask - 5.00; sl_dist = 5.00
            tp2 = ask + (sl_dist * 1.2)
        elif strat_id == "SMC_X_STO_H1" or "SMCxSTO" in reason or "STO" in reason:
            df_h1 = self.connector.get_rates(symbol, "H1", 25)
            if not df_h1.empty and len(df_h1) >= 15:
                ob_low = float(df_h1['low'].iloc[-15:-1].min())
            else:
                ob_low = float(df['low'].iloc[-30:-1].min())
            sl_buffer = 0.80 * sl_mult
            sl = ob_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 5.00: sl = ask - 5.00; sl_dist = 5.00
            if sl_dist > 9.00: sl = ask - 9.00; sl_dist = 9.00
            tp2 = ask + (sl_dist * 2.2)
        elif strat_id.startswith("RTM_") or "RTM" in reason:
            custom_sl = opt.get("custom_sl")
            custom_tp = opt.get("custom_tp")
            if custom_sl and custom_sl < ask:
                sl = float(custom_sl)
                sl_dist = ask - sl
            else:
                lowest_low = float(df['low'].iloc[-15:-1].min())
                sl_buffer = 0.50 * sl_mult
                sl = lowest_low - sl_buffer
                sl_dist = ask - sl
            # EarthETC Structural SL: respect true Swing Head extreme + buffer without artificial 8.50 clamp
            if sl_dist < 2.50: sl = ask - 2.50; sl_dist = 2.50
            if sl_dist > 18.00: sl = ask - 18.00; sl_dist = 18.00
            target_rr = opt.get("tp_ratio", 3.0)
            if custom_tp and custom_tp > ask:
                tp2 = float(custom_tp)
            else:
                tp2 = ask + (sl_dist * target_rr)
        elif strat_id == "PULLBACK_DR_EKK":
            lowest_low = float(df['low'].iloc[-12:-1].min())
            ema60_val = float(df['ema60'].iloc[-2]) if 'ema60' in df else lowest_low
            structural_ref = min(lowest_low, ema60_val)
            sl_buffer = 0.50 * sl_mult
            sl = structural_ref - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 2.50: sl = ask - 2.50; sl_dist = 2.50
            if sl_dist > 12.00: sl = ask - 12.00; sl_dist = 12.00
            target_rr = opt.get("tp_ratio", 2.5)
            tp2 = ask + (sl_dist * target_rr)
        elif strat_id == "KC_LIQUIDITY_DOMINANCE":
            lowest_low = float(df['low'].iloc[-22:-1].min())
            sl_buffer = 0.40 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 2.00: sl = ask - 2.00; sl_dist = 2.00
            if sl_dist > 12.00: sl = ask - 12.00; sl_dist = 12.00
            target_rr = opt.get("tp_ratio", 2.0)
            tp2 = ask + (sl_dist * target_rr)
        elif strat_id == "ICT_JUDAS_RTM_QM":
            lowest_low = float(df['low'].iloc[-18:-1].min())
            sl_buffer = 0.80 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 2.00: sl = ask - 2.00; sl_dist = 2.00
            if sl_dist > 10.00: sl = ask - 10.00; sl_dist = 10.00
            target_rr = opt.get("tp_ratio", 2.2)
            tp2 = ask + (sl_dist * target_rr)
        elif strat_id == "ICT_SILVER_BULLET_FVG":
            lowest_low = float(df['low'].iloc[-8:-1].min())
            sl_buffer = 0.35 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 1.80: sl = ask - 1.80; sl_dist = 1.80
            if sl_dist > 8.00: sl = ask - 8.00; sl_dist = 8.00
            target_rr = opt.get("tp_ratio", 1.5)
            tp2 = ask + (sl_dist * target_rr)
        elif strat_id == "EW_WAVE3_BREAKER":
            lowest_low = float(df['low'].iloc[-8:-1].min())
            sl_buffer = 0.40 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 2.50: sl = ask - 2.50; sl_dist = 2.50
            if sl_dist > 12.00: sl = ask - 12.00; sl_dist = 12.00
            target_rr = opt.get("tp_ratio", 2.5)
            tp2 = ask + (sl_dist * target_rr)
        else:
            # News Momentum Expansion / Default (EarthETC Structural SL)
            if len(df) >= 15:
                hl = df['high'] - df['low']
                hc = (df['high'] - df['close'].shift()).abs()
                lc = (df['low'] - df['close'].shift()).abs()
                tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
                curr_atr = float(tr.rolling(window=14).mean().iloc[-2])
                if math.isnan(curr_atr) or curr_atr <= 0:
                    curr_atr = 2.50
            else:
                curr_atr = 2.50

            lowest_low = float(df['low'].iloc[-10:-1].min())
            sl_buffer = max(0.4 * curr_atr, 1.50) * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 3.50: sl = ask - 3.50; sl_dist = 3.50
            if sl_dist > 18.00: sl = ask - 18.00; sl_dist = 18.00  # EarthETC: wide structural room, no arbitrary 7.00 choke
            tp2 = ask + (sl_dist * 1.8)

        if strat_id in ["ICT_JUDAS_RTM_QM", "ICT_SILVER_BULLET_FVG"]:
            risk_label = "0.5% Risk"
        elif strat_id == "EW_WAVE3_BREAKER":
            risk_label = "1.0% Risk"
        elif strat_id in ["RTM_M4_CONSERVATIVE", "RTM_M6_ELITE_GROWTH", "PULLBACK_DR_EKK", "KC_LIQUIDITY_DOMINANCE"]:
            risk_label = "Step-Up 1.5% Risk" if strat_id == "KC_LIQUIDITY_DOMINANCE" else ("Step-Up 2% Risk" if self.config.get("strategy", {}).get("enable_step_up_compounding", True) else "2.0% Risk")
        elif strat_id in ["NEWS_MOMENTUM_EXPANSION", "ASIAN_RANGE_SNIPER"]:
            lot_mult = 0.5  # Fixed 0.5% risk per user instruction
            risk_label = "0.5% Risk"
        else:
            risk_label = "1.0% Risk"

        total_lot = self.calculate_lot_size(sl_dist, lot_mult=lot_mult, strat_id=strat_id)

        # Single Position Plan across Setups
        res1 = self.connector.open_order(symbol, "BUY", total_lot, sl, tp2, magic_p1, f"Gold_{strat_id[:8]}")
        t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
        self.benchmark_tracker.register_trade(t1, 0, symbol, "BUY", ask, sl, total_lot, strat_id)
        self.add_log(f"🟢 [BUY OPENED] [{strat_id}] {reason} | Single {risk_label}: TP {tp2:.2f} (+{abs(tp2-ask)*100:.0f} pts) / SL {sl:.2f} (-{sl_dist*100:.0f} pts) | Lot: {total_lot}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("BUY", symbol, total_lot, ask, sl, tp2, reason)

    def execute_sell(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None, strat_id: str = "PULLBACK_DR_EKK", **kwargs):
        bid = self.connector.get_market_info(symbol).get("bid", 0.0)
        if bid <= 0: return

        opt = opt_params or {}
        sl_mult = opt.get("atr_sl_multiplier", 1.0)
        lot_mult = opt.get("lot_multiplier", 1.0)

        m_info = self.get_magic_for_strategy(strat_id)
        magic_p1 = m_info["pos1"]

        if is_asian_scalp or strat_id == "ASIAN_RANGE_SNIPER":
            highest_high = df['high'].iloc[-6:-1].max()
            sl_buffer = 0.40 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 2.80: sl = bid + 2.80; sl_dist = 2.80
            if sl_dist > 5.00: sl = bid + 5.00; sl_dist = 5.00
            tp2 = bid - (sl_dist * 1.2)
        elif strat_id == "SMC_X_STO_H1" or "SMCxSTO" in reason or "STO" in reason:
            df_h1 = self.connector.get_rates(symbol, "H1", 25)
            if not df_h1.empty and len(df_h1) >= 15:
                ob_high = float(df_h1['high'].iloc[-15:-1].max())
            else:
                ob_high = float(df['high'].iloc[-30:-1].max())
            sl_buffer = 0.80 * sl_mult
            sl = ob_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 5.00: sl = bid + 5.00; sl_dist = 5.00
            if sl_dist > 9.00: sl = bid + 9.00; sl_dist = 9.00
            tp2 = bid - (sl_dist * 2.2)
        elif strat_id.startswith("RTM_") or "RTM" in reason:
            custom_sl = opt.get("custom_sl")
            custom_tp = opt.get("custom_tp")
            if custom_sl and custom_sl > bid:
                sl = float(custom_sl)
                sl_dist = sl - bid
            else:
                highest_high = float(df['high'].iloc[-15:-1].max())
                sl_buffer = 0.50 * sl_mult
                sl = highest_high + sl_buffer
                sl_dist = sl - bid
            # EarthETC Structural SL: respect true Swing Head extreme + buffer without arbitrary 8.50 clamp
            if sl_dist < 2.50: sl = bid + 2.50; sl_dist = 2.50
            if sl_dist > 18.00: sl = bid + 18.00; sl_dist = 18.00
            target_rr = opt.get("tp_ratio", 3.0)
            if custom_tp and custom_tp < bid:
                tp2 = float(custom_tp)
            else:
                tp2 = bid - (sl_dist * target_rr)
        elif strat_id == "PULLBACK_DR_EKK":
            highest_high = float(df['high'].iloc[-12:-1].max())
            ema60_val = float(df['ema60'].iloc[-2]) if 'ema60' in df else highest_high
            structural_ref = max(highest_high, ema60_val)
            sl_buffer = 0.50 * sl_mult
            sl = structural_ref + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 2.50: sl = bid + 2.50; sl_dist = 2.50
            if sl_dist > 12.00: sl = bid + 12.00; sl_dist = 12.00
            target_rr = opt.get("tp_ratio", 2.5)
            tp2 = bid - (sl_dist * target_rr)
        elif strat_id == "KC_LIQUIDITY_DOMINANCE":
            highest_high = float(df['high'].iloc[-22:-1].max())
            sl_buffer = 0.40 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 2.00: sl = bid + 2.00; sl_dist = 2.00
            if sl_dist > 12.00: sl = bid + 12.00; sl_dist = 12.00
            target_rr = opt.get("tp_ratio", 2.0)
            tp2 = bid - (sl_dist * target_rr)
        elif strat_id == "ICT_JUDAS_RTM_QM":
            highest_high = float(df['high'].iloc[-18:-1].max())
            sl_buffer = 0.80 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 2.00: sl = bid + 2.00; sl_dist = 2.00
            if sl_dist > 10.00: sl = bid + 10.00; sl_dist = 10.00
            target_rr = opt.get("tp_ratio", 2.2)
            tp2 = bid - (sl_dist * target_rr)
        elif strat_id == "ICT_SILVER_BULLET_FVG":
            highest_high = float(df['high'].iloc[-8:-1].max())
            sl_buffer = 0.35 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 1.80: sl = bid + 1.80; sl_dist = 1.80
            if sl_dist > 8.00: sl = bid + 8.00; sl_dist = 8.00
            target_rr = opt.get("tp_ratio", 1.5)
            tp2 = bid - (sl_dist * target_rr)
        elif strat_id == "EW_WAVE3_BREAKER":
            highest_high = float(df['high'].iloc[-8:-1].max())
            sl_buffer = 0.40 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 2.50: sl = bid + 2.50; sl_dist = 2.50
            if sl_dist > 12.00: sl = bid + 12.00; sl_dist = 12.00
            target_rr = opt.get("tp_ratio", 2.5)
            tp2 = bid - (sl_dist * target_rr)
        else:
            # News Momentum Expansion / Default (EarthETC Structural SL)
            if len(df) >= 15:
                hl = df['high'] - df['low']
                hc = (df['high'] - df['close'].shift()).abs()
                lc = (df['low'] - df['close'].shift()).abs()
                tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
                curr_atr = float(tr.rolling(window=14).mean().iloc[-2])
                if math.isnan(curr_atr) or curr_atr <= 0:
                    curr_atr = 2.50
            else:
                curr_atr = 2.50

            highest_high = float(df['high'].iloc[-10:-1].max())
            sl_buffer = max(0.4 * curr_atr, 1.50) * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 3.50: sl = bid + 3.50; sl_dist = 3.50
            if sl_dist > 18.00: sl = bid + 18.00; sl_dist = 18.00  # EarthETC: wide structural room, no arbitrary 7.00 choke
            tp2 = bid - (sl_dist * 1.8)

        if strat_id in ["ICT_JUDAS_RTM_QM", "ICT_SILVER_BULLET_FVG"]:
            risk_label = "0.5% Risk"
        elif strat_id == "EW_WAVE3_BREAKER":
            risk_label = "1.0% Risk"
        elif strat_id in ["RTM_M4_CONSERVATIVE", "RTM_M6_ELITE_GROWTH", "PULLBACK_DR_EKK", "KC_LIQUIDITY_DOMINANCE"]:
            risk_label = "Step-Up 1.5% Risk" if strat_id == "KC_LIQUIDITY_DOMINANCE" else ("Step-Up 2% Risk" if self.config.get("strategy", {}).get("enable_step_up_compounding", True) else "2.0% Risk")
        elif strat_id in ["NEWS_MOMENTUM_EXPANSION", "ASIAN_RANGE_SNIPER"]:
            lot_mult = 0.5  # Fixed 0.5% risk per user instruction
            risk_label = "0.5% Risk"
        else:
            risk_label = "1.0% Risk"

        total_lot = self.calculate_lot_size(sl_dist, lot_mult=lot_mult, strat_id=strat_id)

        # Single Position Plan across Setups (News=0.5%, Others=1.0%)
        res1 = self.connector.open_order(symbol, "SELL", total_lot, sl, tp2, magic_p1, f"Gold_{strat_id[:8]}")
        t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
        self.benchmark_tracker.register_trade(t1, 0, symbol, "SELL", bid, sl, total_lot, strat_id)
        self.add_log(f"🔴 [SELL OPENED] [{strat_id}] {reason} | Single {risk_label}: TP {tp2:.2f} (+{abs(bid-tp2)*100:.0f} pts) / SL {sl:.2f} (-{sl_dist*100:.0f} pts) | Lot: {total_lot}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("SELL", symbol, total_lot, bid, sl, tp2, reason)

    def calculate_lot_size(self, sl_dist: float, lot_mult: float = 1.0, strat_id: str = "RTM_M4_CONSERVATIVE") -> float:
        strat_cfg = self.config.get("strategy", {})
        acc = self.connector.get_account_info()
        balance = float(acc.get("balance", 10000.0))
        equity = float(acc.get("equity", balance))

        profile = RISK_PROFILE_DEFAULTS.get(strat_id)
        if profile is not None:
            # Any of the active pillars: start from its default risk %, then apply a
            # user-configured override from the Web Dashboard if one is set for this setup
            # (config["strategy"]["risk_overrides"][strat_id], written live via
            # /api/strategy/risk_config - no bot restart required, see main.py). Defensively
            # re-clamped here too, even though the API layer already validates on write, so a
            # value that somehow reached config.json through another path can never push risk
            # outside the safe [RISK_OVERRIDE_MIN_PCT, RISK_OVERRIDE_MAX_PCT] band.
            risk_pct = profile["default_pct"]
            risk_overrides = strat_cfg.get("risk_overrides") or {}
            override_val = risk_overrides.get(strat_id)
            if isinstance(override_val, (int, float)) and not isinstance(override_val, bool) and override_val > 0:
                risk_pct = max(RISK_OVERRIDE_MIN_PCT, min(RISK_OVERRIDE_MAX_PCT, float(override_val)))

            if profile["mode"] == "STEP_UP_COMPOUNDING":
                use_step_up = strat_cfg.get("enable_step_up_compounding", True)
                if use_step_up:
                    eval_equity = max(balance, equity)
                    if eval_equity >= 45000.0:
                        tier_base = 45000.0
                    elif eval_equity >= 30000.0:
                        tier_base = 30000.0
                    elif eval_equity >= 20000.0:
                        tier_base = 20000.0
                    elif eval_equity >= 15000.0:
                        tier_base = 15000.0
                    elif eval_equity >= 10000.0:
                        tier_base = 10000.0
                    else:
                        tier_base = max(1000.0, balance)
                    risk_money = tier_base * (risk_pct / 100.0)
                else:
                    risk_money = balance * (risk_pct / 100.0)
            else:  # FIXED
                risk_money = balance * (risk_pct / 100.0)
        elif strat_id in ["NEWS_MOMENTUM_EXPANSION", "ASIAN_RANGE_SNIPER"]:
            risk_pct = 0.5  # Fixed 0.5% risk (retired setups - no override support)
            risk_money = balance * (risk_pct / 100.0)
        else:
            # ALL OTHER/UNKNOWN SETUPS (retired legacy models, etc.) STRICTLY 1.0% RISK
            risk_pct = 1.0
            risk_money = balance * (risk_pct / 100.0)

        lot = (risk_money / (sl_dist * 100.0 + 1e-9)) * lot_mult

        # Safety cap for Asian Range Scalp (prevent runaway lot on ultra-tight SL)
        if strat_id == "ASIAN_RANGE_SNIPER":
            lot = min(lot, 0.25)

        # Dynamic Lot Reduction (Only if enabled in config, default false)
        dynamic_reduction = strat_cfg.get("dynamic_lot_reduction", False)
        if dynamic_reduction:
            if self.consecutive_losses == 1: lot *= 0.50
            elif self.consecutive_losses >= 2: lot *= 0.25

        lot = max(0.01, round(lot, 2))
        return min(lot, 50.0)

    def manage_open_positions(self, symbol: str):
        positions = self.connector.get_open_positions(symbol)
        m_info = self.connector.get_market_info(symbol)
        bid = m_info.get('bid', 0.0)
        ask = m_info.get('ask', 0.0)

        # Lazy-loaded M5 EMA 60 reference for the Dr. Ekk EMA60 Trailing Runner. This method is
        # called with no `df` argument (see run_iteration), so previously the Dr. Ekk trail branch
        # referenced an undefined `df` and raised NameError - silently swallowed by the caller's
        # broad except, which skipped trailing/BE-lock updates for ALL strategies that cycle.
        # Fetched at most once per call, and only if a Dr. Ekk position actually needs it.
        ema60_cache: Dict[str, float] = {}
        def _pullback_ema60() -> float:
            if "value" not in ema60_cache:
                try:
                    df_m5 = self.connector.get_rates(symbol, "M5", 200)
                    if df_m5 is not None and not df_m5.empty and len(df_m5) >= 60:
                        ema60_cache["value"] = float(df_m5['close'].ewm(span=60, adjust=False).mean().iloc[-2])
                    else:
                        ema60_cache["value"] = 0.0
                except Exception:
                    ema60_cache["value"] = 0.0
            return ema60_cache["value"]

        # Iterate through every strategy setup independently
        for strat_id, s_magics in STRATEGY_MAGIC_MAP.items():
            pos1_magic = s_magics["pos1"]
            pos2_magic = s_magics["pos2"]
            pos3_magic = s_magics["pos3"]

            pos1_list = [p for p in positions if p.get('magic') == pos1_magic]
            pos2_list = [p for p in positions if p.get('magic') == pos2_magic]
            pos3_list = [p for p in positions if p.get('magic') == pos3_magic]

            # Multi-Stage R-Step Trailing Lock:
            # - For M4, M5, M6 (Quick Harvest 2.0R):
            #   >= 1.0R -> Break-Even (+0.30 USD)
            #   >= 1.5R -> Lock +0.8R Profit
            # - For M7 (Trend Runner 3.5R):
            #   >= 1.0R -> Break-Even (+0.30 USD)
            #   >= 2.0R -> Lock +1.0R Profit
            #   >= 2.6R -> Lock +1.8R Profit
            #   >= 3.0R -> Lock +2.4R Profit
            for p1 in pos1_list:
                t_id = p1.get('ticket')
                open_p = p1.get('price_open', 0.0)
                sl = p1.get('sl', 0.0)
                tp = p1.get('tp', 0.0)
                ptype = p1.get('type')

                # Resolve initial 1.0R risk distance
                if t_id in self.initial_risk_map:
                    initial_r = self.initial_risk_map[t_id]
                else:
                    if ptype == "BUY" and sl > 0 and sl < open_p:
                        initial_r = abs(open_p - sl)
                        self.initial_risk_map[t_id] = initial_r
                    elif ptype == "SELL" and sl > 0 and sl > open_p:
                        initial_r = abs(open_p - sl)
                        self.initial_risk_map[t_id] = initial_r
                    elif tp > 0:
                        if strat_id in ["RTM_M4_CONSERVATIVE", "RTM_M6_ELITE_GROWTH"]:
                            raw_dist = abs(open_p - tp)
                            initial_r = raw_dist / 3.0 if raw_dist > 20.0 else raw_dist / 2.0
                        elif strat_id == "SMC_X_STO_H1":
                            initial_r = abs(open_p - tp) / 2.2
                        elif strat_id == "PULLBACK_DR_EKK":
                            initial_r = abs(open_p - tp) / 1.5
                        elif strat_id == "KC_LIQUIDITY_DOMINANCE":
                            initial_r = abs(open_p - tp) / 2.0
                        elif strat_id == "ICT_JUDAS_RTM_QM":
                            initial_r = abs(open_p - tp) / 2.0
                        elif strat_id == "ICT_SILVER_BULLET_FVG":
                            initial_r = abs(open_p - tp) / 1.5
                        elif strat_id == "EW_WAVE3_BREAKER":
                            initial_r = abs(open_p - tp) / 2.5
                        else:
                            initial_r = abs(open_p - tp) / 1.8
                        self.initial_risk_map[t_id] = initial_r
                    else:
                        initial_r = 5.0

                if initial_r <= 0.50:
                    continue

                is_quick_harvest = strat_id in ["RTM_M4_CONSERVATIVE", "RTM_M6_ELITE_GROWTH"]
                is_asian_sniper = strat_id == "ASIAN_RANGE_SNIPER"
                is_news_momentum = strat_id == "NEWS_MOMENTUM_EXPANSION"
                is_smc_devil = strat_id == "SMC_X_STO_H1"
                is_pullback_dr_ekk = strat_id == "PULLBACK_DR_EKK"
                is_kc_dominance = strat_id == "KC_LIQUIDITY_DOMINANCE"
                is_judas_qm = strat_id == "ICT_JUDAS_RTM_QM"
                is_silver_bullet = strat_id == "ICT_SILVER_BULLET_FVG"
                is_ew_breaker = strat_id == "EW_WAVE3_BREAKER"

                if ptype == "BUY":
                    profit_dist = bid - open_p
                    r_profit = profit_dist / initial_r

                    if is_quick_harvest:
                        # RTM Quasimodo Multi-Stage Profit Lock (Target 3.0R - 4.5R Runner):
                        # Step 4: At >= 2.8R -> Lock +2.0R Profit
                        if r_profit >= 2.8:
                            target_sl = round(open_p + (initial_r * 2.0), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"💰 [PROFIT LOCKED +2.0R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +2.0R ({target_sl:.2f})", "SUCCESS")
                        # Step 3: At >= 2.0R -> Lock +1.2R Profit
                        elif r_profit >= 2.0:
                            target_sl = round(open_p + (initial_r * 1.2), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +1.2R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.2R ({target_sl:.2f})", "SUCCESS")
                        # Step 2: At >= 1.5R -> Lock +0.8R Profit
                        elif r_profit >= 1.5:
                            target_sl = round(open_p + (initial_r * 0.8), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_asian_sniper:
                        # Asian Range Sniper (Target 1.8R - Clean Mean Reversion Breathing Room)
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD), allows oscillation to hit Full TP 1.8R
                        if r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_news_momentum:
                        # News Momentum (Target 1.8R)
                        # Step 2: At >= 1.4R -> Lock +0.8R Profit (Prevents whipsaw retracement)
                        if r_profit >= 1.4:
                            target_sl = round(open_p + (initial_r * 0.8), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_smc_devil:
                        # SMC H1 Devil System (Target 2.2R)
                        # Step 3: At >= 1.8R -> Lock +1.2R Profit
                        if r_profit >= 1.8:
                            target_sl = round(open_p + (initial_r * 1.2), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"💰 [PROFIT LOCKED +1.2R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.2R ({target_sl:.2f})", "SUCCESS")
                        # Step 2: At >= 1.4R -> Lock +0.8R Profit
                        elif r_profit >= 1.4:
                            target_sl = round(open_p + (initial_r * 0.8), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                    elif is_pullback_dr_ekk:
                        # Dr. Ekk Chapter 12: Mode 3 (EMA 60 Trailing Runner)
                        # Step 2: At >= 1.5R -> Trail behind EMA 60 (or lock +0.8R minimum)
                        if r_profit >= 1.5:
                            ema60_val = _pullback_ema60()
                            target_sl = round(max(open_p + (initial_r * 0.8), ema60_val - 0.50), 2) if ema60_val > open_p else round(open_p + (initial_r * 0.8), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [DR EKK EMA60 TRAIL] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL trailed to {target_sl:.2f}", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [DR EKK BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_kc_dominance:
                        # KC Forex Liquidity Dominance (Target 2.0R)
                        # Step 2: At >= 1.4R -> Lock +0.8R Profit
                        if r_profit >= 1.4:
                            target_sl = round(open_p + (initial_r * 0.8), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [KC DOMINANCE +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [KC DOMINANCE BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_judas_qm:
                        # ICT Judas Swing & RTM Quasimodo (Target 2.0R)
                        if r_profit >= 1.4:
                            target_sl = round(open_p + (initial_r * 0.8), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [JUDAS QM +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [JUDAS QM BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_silver_bullet:
                        # ICT NY Silver Bullet FVG (Target 1.5R)
                        if r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [SILVER BULLET BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_ew_breaker:
                        # Elliott Wave 3 Breaker (Target 2.5R)
                        if r_profit >= 1.8:
                            target_sl = round(open_p + (initial_r * 1.2), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"💰 [EW WAVE3 +1.2R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.2R ({target_sl:.2f})", "SUCCESS")
                        elif r_profit >= 1.2:
                            target_sl = round(open_p + (initial_r * 0.6), 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [EW WAVE3 +0.6R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.6R ({target_sl:.2f})", "SUCCESS")
                        elif r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [EW WAVE3 BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    else:
                        if r_profit >= 1.0:
                            target_sl = round(open_p + 0.30, 2)
                            if sl < target_sl - 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                elif ptype == "SELL":
                    profit_dist = open_p - ask
                    r_profit = profit_dist / initial_r

                    if is_quick_harvest:
                        # RTM Quasimodo Multi-Stage Profit Lock (Target 3.0R - 4.5R Runner):
                        # Step 4: At >= 2.8R -> Lock +2.0R Profit
                        if r_profit >= 2.8:
                            target_sl = round(open_p - (initial_r * 2.0), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"💰 [PROFIT LOCKED +2.0R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +2.0R ({target_sl:.2f})", "SUCCESS")
                        # Step 3: At >= 2.0R -> Lock +1.2R Profit
                        elif r_profit >= 2.0:
                            target_sl = round(open_p - (initial_r * 1.2), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +1.2R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.2R ({target_sl:.2f})", "SUCCESS")
                        # Step 2: At >= 1.5R -> Lock +0.8R Profit
                        elif r_profit >= 1.5:
                            target_sl = round(open_p - (initial_r * 0.8), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_asian_sniper:
                        # Asian Range Sniper (Target 1.8R - Clean Mean Reversion Breathing Room)
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        if r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_news_momentum:
                        # News Momentum (Target 1.8R)
                        # Step 2: At >= 1.4R -> Lock +0.8R Profit (Prevents whipsaw retracement)
                        if r_profit >= 1.4:
                            target_sl = round(open_p - (initial_r * 0.8), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_smc_devil:
                        # SMC H1 Devil System (Target 2.2R)
                        # Step 3: At >= 1.8R -> Lock +1.2R Profit
                        if r_profit >= 1.8:
                            target_sl = round(open_p - (initial_r * 1.2), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"💰 [PROFIT LOCKED +1.2R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.2R ({target_sl:.2f})", "SUCCESS")
                        # Step 2: At >= 1.4R -> Lock +0.8R Profit
                        elif r_profit >= 1.4:
                            target_sl = round(open_p - (initial_r * 0.8), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [PROFIT LOCKED +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                    elif is_pullback_dr_ekk:
                        # Dr. Ekk Chapter 12: Mode 3 (EMA 60 Trailing Runner)
                        # Step 2: At >= 1.5R -> Trail behind EMA 60 (or lock +0.8R minimum)
                        if r_profit >= 1.5:
                            ema60_val = _pullback_ema60()
                            target_sl = round(min(open_p - (initial_r * 0.8), ema60_val + 0.50), 2) if (ema60_val < open_p and ema60_val > 0) else round(open_p - (initial_r * 0.8), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [DR EKK EMA60 TRAIL] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL trailed to {target_sl:.2f}", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [DR EKK BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_kc_dominance:
                        # KC Forex Liquidity Dominance (Target 2.0R)
                        # Step 2: At >= 1.4R -> Lock +0.8R Profit
                        if r_profit >= 1.4:
                            target_sl = round(open_p - (initial_r * 0.8), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [KC DOMINANCE +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [KC DOMINANCE BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_judas_qm:
                        # ICT Judas Swing & RTM Quasimodo (Target 2.0R)
                        if r_profit >= 1.4:
                            target_sl = round(open_p - (initial_r * 0.8), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [JUDAS QM +0.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.8R ({target_sl:.2f})", "SUCCESS")
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [JUDAS QM BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_silver_bullet:
                        # ICT NY Silver Bullet FVG (Target 1.5R)
                        if r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [SILVER BULLET BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    elif is_ew_breaker:
                        # Elliott Wave 3 Breaker (Target 2.5R)
                        if r_profit >= 1.8:
                            target_sl = round(open_p - (initial_r * 1.2), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"💰 [EW WAVE3 +1.2R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.2R ({target_sl:.2f})", "SUCCESS")
                        elif r_profit >= 1.2:
                            target_sl = round(open_p - (initial_r * 0.6), 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🎯 [EW WAVE3 +0.6R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +0.6R ({target_sl:.2f})", "SUCCESS")
                        elif r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [EW WAVE3 BREAK-EVEN] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                    else:
                        if r_profit >= 1.0:
                            target_sl = round(open_p - 0.30, 2)
                            if sl == 0 or sl > target_sl + 0.10:
                                self.connector.modify_position(t_id, target_sl, tp)
                                self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

            # Stage 1: Legacy multi-order support (When Pos 1 closes, move Pos 2 & 3 to BE)
            if len(pos1_list) == 0 and (len(pos2_list) > 0 or len(pos3_list) > 0):
                for p in (pos2_list + pos3_list):
                    open_p = p.get('price_open', 0.0)
                    sl = p.get('sl', 0.0)
                    ptype = p.get('type')

                    if ptype == "BUY" and sl < open_p and bid > (open_p + 0.30):
                        new_sl = open_p + 0.30
                        self.connector.modify_position(p.get('ticket'), new_sl, p.get('tp'))
                        self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Pos #{p.get('ticket')} SL locked at {new_sl:.2f}", "SUCCESS")
                    elif ptype == "SELL" and (sl > open_p or sl == 0) and ask < (open_p - 0.30):
                        new_sl = open_p - 0.30
                        self.connector.modify_position(p.get('ticket'), new_sl, p.get('tp'))
                        self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Pos #{p.get('ticket')} SL locked at {new_sl:.2f}", "SUCCESS")

            # Stage 2: When Pos 2 (TP2) is closed -> Trailing Stop for Pos 3
            if len(pos1_list) == 0 and len(pos2_list) == 0 and len(pos3_list) > 0:
                for p3 in pos3_list:
                    open_p = p3.get('price_open', 0.0)
                    sl = p3.get('sl', 0.0)
                    ptype = p3.get('type')
                    
                    if p3.get('tp', 0.0) == 0.0:
                        trail_dist = 2.50
                        if ptype == "BUY":
                            trail_sl = round(bid - trail_dist, 2)
                            if trail_sl > sl and trail_sl > (open_p + 0.50):
                                self.connector.modify_position(p3.get('ticket'), trail_sl, 0.0)
                                self.add_log(f"📈 [AI TREND TRAILING] [{strat_id}] Pos3 #{p3.get('ticket')} Trailing SL updated to {trail_sl:.2f}", "SUCCESS")
                        elif ptype == "SELL":
                            trail_sl = round(ask + trail_dist, 2)
                            if (sl == 0 or trail_sl < sl) and trail_sl < (open_p - 0.50):
                                self.connector.modify_position(p3.get('ticket'), trail_sl, 0.0)
                                self.add_log(f"📉 [AI TREND TRAILING] [{strat_id}] Pos3 #{p3.get('ticket')} Trailing SL updated to {trail_sl:.2f}", "SUCCESS")

        m_info = self.connector.get_market_info(symbol)
        bid = m_info.get('bid', 0.0)
        ask = m_info.get('ask', 0.0)

        # Parallel Exit Benchmark Price Tracker
        if len(positions) > 0:
            rates = self.connector.get_rates(symbol, "M5", 2)
            if not rates.empty:
                b1 = rates.iloc[-1]
                self.benchmark_tracker.update_price(symbol, float(b1['high']), float(b1['low']), bid, ask)

    def check_and_execute_pyramiding(self, df: pd.DataFrame, symbol: str, ea_positions: list, regime_info: dict):
        """Execute risk-free trend pyramiding (scaling-in) when runner SL is already locked at Break-Even."""
        strat_cfg = self.config.get("strategy", {})
        if not strat_cfg.get("enable_trend_pyramiding", False):
            return

        # 1. Block pyramiding if in ranging or choppy sideway regime
        if regime_info.get("is_choppy") or "SIDEWAY" in regime_info.get("regime", "") or "RANGING" in regime_info.get("regime", ""):
            return

        # 2. Check if runner position exists (Pos 2) and SL is locked at Break-Even
        runner_pos = [p for p in ea_positions if p.get('magic') == self.magic_pos2]
        if not runner_pos:
            return

        p = runner_pos[0]
        open_price = p.get('price_open', 0.0)
        sl = p.get('sl', 0.0)
        ptype = p.get('type')

        # Require SL to be locked at Break-Even or in profit
        if ptype == "BUY" and sl < open_price:
            return
        if ptype == "SELL" and (sl > open_price or sl == 0):
            return

        # Check existing pyramid positions limit
        max_layers = strat_cfg.get("max_pyramid_layers", 2)
        pyramid_magic_base = self.magic_number + 3 # 555891
        existing_pyramids = [pos for pos in ea_positions if pos.get('magic') == pyramid_magic_base]
        if len(existing_pyramids) >= max_layers:
            return

        # Execute Pyramid Layer
        lot_ratio = strat_cfg.get("pyramid_lot_ratio", 0.60)
        lot = max(0.01, round(p.get('volume', 0.02) * lot_ratio, 2))
        
        m_info = self.connector.get_market_info(symbol)
        curr_price = m_info.get('ask' if ptype == "BUY" else 'bid', 0.0)
        pyramid_sl = open_price

        self.connector.open_order(symbol, ptype, lot, pyramid_sl, 0.0, pyramid_magic_base, "Pyramid_L1")
        self.add_log(f"🔺 [TREND PYRAMIDING] Added Layer 1 on {ptype} | Lot: {lot} | Magic: {pyramid_magic_base}", "SUCCESS")

# Alias for backwards compatibility
BotEngine = GoldScalpingBot

REGISTRATION_DEBUG = "Uninitialized"

def register_trading_hours_api(app, acc_mgr):
    """Dynamically registers trading hours GET and POST endpoints into the running FastAPI router."""
    global REGISTRATION_DEBUG
    if not app or not acc_mgr:
        REGISTRATION_DEBUG = f"Failed: app={app is not None}, acc_mgr={acc_mgr is not None}"
        return
    try:
        from fastapi import Query, HTTPException, Request
        from datetime import timezone, timedelta, datetime
        import re

        routes = getattr(app, "routes", [])
        existing_info = [(getattr(r, "path", None), list(getattr(r, "methods", []))) for r in routes if "trading_hours" in str(getattr(r, "path", None))]

        def _build_resp(inst):
            overrides = inst.strategy_cfg.get("trading_hours_overrides") or {}
            registry = getattr(acc_mgr.analytics, "STRATEGY_REGISTRY", {}) if hasattr(acc_mgr, "analytics") else {}
            setups = []
            th_tz = timezone(timedelta(hours=7))
            now_t = datetime.now(th_tz).time()

            for strat_id in STRATEGY_MAGIC_MAP.keys():
                profile = RISK_PROFILE_DEFAULTS.get(strat_id)
                if not profile:
                    continue
                strat_mode = inst.strategy_cfg.get("strategy_mode", "ALL")
                enabled_key = f"{strat_id.lower()}_enabled"
                is_active = inst.strategy_cfg.get(enabled_key, True) and (strat_mode in ["ALL", strat_id])
                if not is_active:
                    continue

                default_hours = DEFAULT_TRADING_HOURS.get(strat_id, {"start": "14:00", "end": "24:00"})
                strat_override = overrides.get(strat_id)

                cur_start = strat_override.get("start_time", default_hours["start"]) if isinstance(strat_override, dict) else default_hours["start"]
                cur_end = strat_override.get("end_time", default_hours["end"]) if isinstance(strat_override, dict) else default_hours["end"]

                is_active_now = is_time_in_range(now_t, cur_start, cur_end)
                reg_entry = registry.get(strat_id, {})

                setups.append({
                    "id": strat_id,
                    "name": reg_entry.get("name", strat_id),
                    "icon": reg_entry.get("icon", ""),
                    "default_start_time": default_hours["start"],
                    "default_end_time": default_hours["end"],
                    "current_start_time": cur_start,
                    "current_end_time": cur_end,
                    "is_overridden": strat_id in overrides,
                    "is_active_now": is_active_now,
                    "current_server_time_thai": now_t.strftime("%H:%M")
                })

            return {
                "status": True,
                "acc_id": inst.id,
                "acc_name": inst.name,
                "current_time_thai": now_t.strftime("%H:%M:%S"),
                "setups": setups,
            }

        async def get_hours(acc_id: Optional[str] = Query(None)):
            inst = acc_mgr.get_account(acc_id)
            if inst is None:
                raise HTTPException(status_code=404, detail="Account not found")
            return _build_resp(inst)

        async def post_hours(req: Request):
            try:
                body = await req.json()
            except Exception:
                body = {}
            target_acc_id = body.get("acc_id")
            inst = acc_mgr.get_account(target_acc_id)
            if inst is None:
                raise HTTPException(status_code=404, detail="Account not found")

            overrides_input = body.get("trading_hours_overrides", {})
            current_overrides = dict(inst.strategy_cfg.get("trading_hours_overrides") or {})
            time_pattern = re.compile(r"^(?:[01]?\d|2[0-4]):[0-5]\d$")
            errors = []

            for strat_id, val in overrides_input.items():
                if strat_id not in DEFAULT_TRADING_HOURS and strat_id not in STRATEGY_MAGIC_MAP:
                    errors.append(f"Unknown strategy id: {strat_id}")
                    continue
                if val is None:
                    current_overrides.pop(strat_id, None)
                    continue

                s_t = val.get("start_time", "").strip() if isinstance(val, dict) else ""
                e_t = val.get("end_time", "").strip() if isinstance(val, dict) else ""

                if not time_pattern.match(s_t):
                    errors.append(f"{strat_id}: Invalid start_time '{s_t}'")
                    continue
                if not time_pattern.match(e_t):
                    errors.append(f"{strat_id}: Invalid end_time '{e_t}'")
                    continue

                current_overrides[strat_id] = {"start_time": s_t, "end_time": e_t}

            if errors:
                raise HTTPException(status_code=400, detail="; ".join(errors))

            acc_mgr.update_strategy_settings(inst.id, {"trading_hours_overrides": current_overrides})
            return _build_resp(inst)

        # Clear any old route for /api/strategy/trading_hours without GET/POST methods
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/api/strategy/trading_hours"]
        app.add_api_route("/api/strategy/trading_hours", get_hours, methods=["GET"])
        app.add_api_route("/api/strategy/trading_hours", post_hours, methods=["POST"])
        REGISTRATION_DEBUG = f"Registered! Old was: {existing_info}, New total routes: {len(app.router.routes)}"
        logger.info(REGISTRATION_DEBUG)
    except Exception as e:
        REGISTRATION_DEBUG = f"ERROR: {e}"
        logger.warning(REGISTRATION_DEBUG)

# Trigger registration on import if running under main/app
try:
    import sys
    found_mods = []
    for m_name, _mod in list(sys.modules.items()):
        if _mod and hasattr(_mod, "app") and hasattr(_mod, "account_manager"):
            found_mods.append(m_name)
            register_trading_hours_api(_mod.app, _mod.account_manager)
    if not found_mods:
        REGISTRATION_DEBUG = f"No module had app+acc_mgr in sys.modules ({list(sys.modules.keys())[:15]})"
except Exception as sys_err:
    REGISTRATION_DEBUG = f"Sys loop error: {sys_err}"

