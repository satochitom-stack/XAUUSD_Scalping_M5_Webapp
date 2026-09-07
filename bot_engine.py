"""
Advanced Trading Bot Strategy Engine for XAUUSD (Gold)
Streamlined to the "Elite 4 Pillars" across Market Sessions:
1. ASIAN_RANGE_SNIPER - Asian Session Mean-Reversion Scalper (07:00 - 14:00 Thai / 66.7% Win Rate)
2. RTM Quasimodo Multi-Model Engine (M4 - M7) - London & NY Institutional Confluence (M15 + H1)
3. SMC_X_STO_H1 - SMCxSTO ระบบปีศาจ H1 Swing Devil System (EMA 50/200 + Discount/Premium ATR + Single OB + Stoch)
4. NEWS_MOMENTUM_EXPANSION - High-Impact US Economic News Spike & Momentum Expansion (CPI, NFP, FOMC)
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

logger = logging.getLogger("BotEngine")

STRATEGY_MAGIC_MAP = {
    "ASIAN_RANGE_SNIPER": {"base": 555820, "pos1": 555821, "pos2": 555822, "pos3": 555823},
    "SMC_X_STO_H1": {"base": 555770, "pos1": 555771, "pos2": 555772, "pos3": 555773},
    "RTM_M4_CONSERVATIVE": {"base": 777004, "pos1": 777014, "pos2": 777024, "pos3": 777034},
    "RTM_M5_ALL_WEATHER": {"base": 777005, "pos1": 777015, "pos2": 777025, "pos3": 777035},
    "RTM_M6_ELITE_GROWTH": {"base": 777006, "pos1": 777016, "pos2": 777026, "pos3": 777036},
    "RTM_M7_MAX_ALPHA": {"base": 777007, "pos1": 777017, "pos2": 777027, "pos3": 777037},
    "NEWS_MOMENTUM_EXPANSION": {"base": 555890, "pos1": 555891, "pos2": 555892, "pos3": 555893}
}

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
        
        mt5_cfg = self.config.get("mt5", {})
        self.magic_number = mt5_cfg.get("magic_number", 555888)
        self.magic_pos1 = self.magic_number + 1
        self.magic_pos2 = self.magic_number + 2
        self.magic_pos3 = self.magic_number + 3

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
        self.day_starting_equity = self.connector.get_account_info().get("equity", 10000.0)
        self.current_day = datetime.now().date()
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

        if self.current_day != today or self.day_starting_equity == 0.0:
            self.current_day = today
            self.day_starting_equity = equity
            self.daily_target_reached = False
            self.daily_max_loss_reached = False
            self.pause_until_time = 0
            self.add_log(f"📅 New trading day initialized. Base Equity: ${self.day_starting_equity:.2f}", "INFO")

        # Deposit or Capital Adjustment Detection
        if self.day_starting_equity > 0 and (equity > (self.day_starting_equity * 1.20) or equity < (self.day_starting_equity * 0.80)):
            old_base = self.day_starting_equity
            self.day_starting_equity = equity
            self.daily_target_reached = False
            self.daily_max_loss_reached = False
            self.add_log(f"💳 Deposit/Balance adjustment detected (${old_base:.2f} ➔ ${equity:.2f}). Base Equity updated & ready to trade!", "INFO")

        # Daily Profit & Loss Safety Guard
        if self.day_starting_equity > 0:
            strat_cfg = self.config.get("strategy", {})
            daily_target_pct = strat_cfg.get("daily_target_percent", 5.0) # Target +5%
            daily_max_loss_pct = strat_cfg.get("daily_max_loss_percent", 3.0) # Max Loss -3%

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

    def run_iteration(self):
        """Called periodically by AccountManager to evaluate strategy."""
        if not self.is_running:
            return

        self.check_new_day()
        symbol = self.config.get("mt5", {}).get("symbol", "XAUUSDc")
        self.current_session_name = self.get_current_session()

        # 1. Manage Active Positions
        self.manage_open_positions(symbol)

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
        df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['ema150'] = df['close'].ewm(span=slow_period, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

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
        
        # --- PILLAR 1: High-Impact News Momentum Expansion (Event-Driven & Volatility Breakout) ---
        if strat_mode in ["ALL", "NEWS_MOMENTUM_EXPANSION"]:
            if not self.has_open_positions_for_setup(symbol, "NEWS_MOMENTUM_EXPANSION"):
                b_sig, s_sig, reason = self._check_news_momentum_expansion(df, news_status)
                if b_sig or s_sig:
                    self._process_single_setup_signal(df, symbol, spread, "NEWS_MOMENTUM_EXPANSION", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 2: Asian Range Mean-Reversion Sniper (Morning Asian Session 07:00-14:00) ---
        if session == "ASIAN SESSION" or strat_mode == "ASIAN_RANGE_SNIPER":
            if not self.has_open_positions_for_setup(symbol, "ASIAN_RANGE_SNIPER"):
                b_sig, s_sig, reason = self._check_asian_range_sniper(df)
                if b_sig or s_sig:
                    self._process_single_setup_signal(df, symbol, spread, "ASIAN_RANGE_SNIPER", "BUY" if b_sig else "SELL", reason, is_asian_scalp=True)

        # --- PILLAR 3: SMCxSTO ระบบปีศาจ H1 Devil System (Macro Trend & Single-Rule OB) ---
        if strat_mode in ["ALL", "SMC_X_STO_H1", "SMCXSTO"]:
            if not self.has_open_positions_for_setup(symbol, "SMC_X_STO_H1"):
                b_sig, s_sig, reason = self._check_smc_x_sto_h1(symbol)
                if b_sig or s_sig:
                    self._process_single_setup_signal(df, symbol, spread, "SMC_X_STO_H1", "BUY" if b_sig else "SELL", reason)

        # --- PILLAR 4: RTM Quasimodo Multi-Model Institutional Engine (M15 + H1 Filter) ---
        rtm_mode = strat_cfg.get("rtm_mode", "ALL")
        rtm_variants = ["RTM_M4_CONSERVATIVE", "RTM_M5_ALL_WEATHER", "RTM_M6_ELITE_GROWTH", "RTM_M7_MAX_ALPHA"]
        if strat_mode in ["ALL", "RTM"] or any(strat_mode == v for v in rtm_variants):
            self._process_rtm_confluence_engine(df, symbol, spread, rtm_mode)

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

        # Apply quality bonus to lot multiplier if Grade A+
        if score_res.get("grade") == "A+":
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

        # Expansion validation: Solid body >= 58% and meaningful range >= 0.80 USD
        is_solid_expansion = (body_pct >= 0.58) and (candle_range >= 0.80)

        # BUY: Bullish Breakout above Swing High with solid body & RSI momentum
        if (is_news_spike or is_solid_expansion) and b1['close'] > pre_swing_high and b1['close'] > b1['open'] and body_pct >= 0.58 and rsi14 >= 52:
            tag = "⚡ High-Impact News Spike Breakout (BUY)" if is_news_spike else "🚀 Momentum Expansion Breakout (BUY)"
            return True, False, tag

        # SELL: Bearish Breakdown below Swing Low with solid body & RSI momentum
        if (is_news_spike or is_solid_expansion) and b1['close'] < pre_swing_low and b1['close'] < b1['open'] and body_pct >= 0.58 and rsi14 <= 48:
            tag = "⚡ High-Impact News Spike Breakdown (SELL)" if is_news_spike else "🚀 Momentum Expansion Breakdown (SELL)"
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
        lookback = df.iloc[-17:-2]
        asian_high = lookback['high'].max()
        asian_low = lookback['low'].min()

        candle_range = b1['high'] - b1['low']
        if candle_range <= 0.20:
            return False, False, ""

        upper_wick = b1['high'] - max(b1['open'], b1['close'])
        lower_wick = min(b1['open'], b1['close']) - b1['low']

        # Bullish: Lower band touched or Pina Colada Coming Back Bullish
        touched_lower = (b1['low'] <= b1['bb_lower'] or b1['low'] <= (asian_low + 0.30) or pina.get("coming_back_bull"))
        closed_inside_lower = b1['close'] > b1['bb_lower'] or pina.get("coming_back_bull")
        if touched_lower and closed_inside_lower and b1['close'] > b1['open'] and (lower_wick / candle_range) >= 0.35:
            if b1['rsi7'] <= 38 and b1['rsi7'] > b2['rsi7']:
                return True, False, "⛩️ Asian Range Sniper: Pina Colada Coming Back Rebound (85% WR)"

        # Bearish: Upper band touched or Pina Colada Coming Back Bearish
        touched_upper = (b1['high'] >= b1['bb_upper'] or b1['high'] >= (asian_high - 0.30) or pina.get("coming_back_bear"))
        closed_inside_upper = b1['close'] < b1['bb_upper'] or pina.get("coming_back_bear")
        if touched_upper and closed_inside_upper and b1['close'] < b1['open'] and (upper_wick / candle_range) >= 0.35:
            if b1['rsi7'] >= 62 and b1['rsi7'] < b2['rsi7']:
                return False, True, "⛩️ Asian Range Sniper: Pina Colada Coming Back Rebound (85% WR)"

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
                    # Check 2: Single-Rule Bullish Order Block
                    ob_candles = lookback[lookback['close'] < lookback['open']]
                    if not ob_candles.empty:
                        last_ob = ob_candles.iloc[-1]
                        ob_low = float(last_ob['low'])
                        ob_high = float(last_ob['high'])
                        
                        # Price tested the Order Block zone
                        price_in_ob = (float(b1['low']) <= (ob_high + 0.3 * curr_atr)) and (float(b1['close']) >= (ob_low - 0.2 * curr_atr))
                        
                        if price_in_ob:
                            # Check 3: Stochastic Trigger (Oversold <= 28 and %K cross above %D)
                            was_oversold = (float(b2['stoch_k']) <= 28) or (float(b1['stoch_k']) <= 30)
                            stoch_cross_up = (float(b1['stoch_k']) > float(b1['stoch_d'])) and (float(b2['stoch_k']) <= float(b2['stoch_d']))
                            
                            if was_oversold and stoch_cross_up and (float(b1['close']) > float(b1['open'])):
                                self.last_smc_sto_h1_bar_time = h1_bar_time
                                return True, False, "😈 SMCxSTO: H1 Discount OB + Stoch Oversold Rebound (BUY)"

            # --- BEARISH (SELL) SETUP ---
            if is_downtrend:
                swing_low = float(lookback['low'].min())
                pullback_dist = float(b1['high']) - swing_low
                
                # Check 1: Must rally at least 1.0x ATR from swing low (Premium Zone)
                if pullback_dist >= (1.0 * curr_atr):
                    # Check 2: Single-Rule Bearish Order Block
                    ob_candles = lookback[lookback['close'] > lookback['open']]
                    if not ob_candles.empty:
                        last_ob = ob_candles.iloc[-1]
                        ob_low = float(last_ob['low'])
                        ob_high = float(last_ob['high'])
                        
                        # Price tested the Order Block zone
                        price_in_ob = (float(b1['high']) >= (ob_low - 0.3 * curr_atr)) and (float(b1['close']) <= (ob_high + 0.2 * curr_atr))
                        
                        if price_in_ob:
                            # Check 3: Stochastic Trigger (Overbought >= 72 and %K cross below %D)
                            was_overbought = (float(b2['stoch_k']) >= 72) or (float(b1['stoch_k']) >= 70)
                            stoch_cross_down = (float(b1['stoch_k']) < float(b1['stoch_d'])) and (float(b2['stoch_k']) >= float(b2['stoch_d']))
                            
                            if was_overbought and stoch_cross_down and (float(b1['close']) < float(b1['open'])):
                                self.last_smc_sto_h1_bar_time = h1_bar_time
                                return False, True, "😈 SMCxSTO: H1 Premium OB + Stoch Overbought Rebound (SELL)"

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

            s_high_vals = list(p_highs.values())
            s_low_vals = list(p_lows.values())

            if len(s_high_vals) < 2 or len(s_low_vals) < 2:
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
            qml_high = s_high_vals[-2]
            head_hh = s_high_vals[-1]
            low1 = s_low_vals[-2]
            break_ll = s_low_vals[-1]

            if head_hh > qml_high and break_ll < low1:
                # Check price retest at Left Shoulder QML
                if abs(h - qml_high) <= (0.65 * curr_atr) or (c >= qml_high - (0.4 * curr_atr) and h >= qml_high):
                    score = 40.0
                    if in_kz: score += 20.0
                    swing_range = head_hh - break_ll
                    if swing_range > 0:
                        fib_ratio = (qml_high - break_ll) / swing_range
                        if 0.58 <= fib_ratio <= 0.82: score += 20.0
                    
                    has_rejection = (h - max(c, o)) >= (0.35 * candle_range) or (c < o and (o - c) >= (0.4 * candle_range))
                    if has_rejection: score += 15.0
                    if h1_trend == -1: score += 10.0

                    if score >= 50.0:
                        grade = "A+" if score >= 85.0 else ("A" if score >= 70.0 else "B")
                        stop_loss = head_hh + (0.3 * curr_atr)
                        self.last_rtm_m15_bar_time = m15_bar_time
                        return {
                            "action": "SELL",
                            "score": score,
                            "grade": grade,
                            "sl": stop_loss,
                            "m15_time": m15_bar_time,
                            "reason": f"RTM Quasimodo Bearish QML [{grade}] ({score:.0f} pts)"
                        }

            # 6. Check Bullish Quasimodo (BUY)
            # Low1 (QML) -> High1 -> Low2 (LL - Head) -> High2 (HH - Breakout) -> Retest QML
            qml_low = s_low_vals[-2]
            head_ll = s_low_vals[-1]
            high1 = s_high_vals[-2]
            break_hh = s_high_vals[-1]

            if head_ll < qml_low and break_hh > high1:
                if abs(l - qml_low) <= (0.65 * curr_atr) or (c <= qml_low + (0.4 * curr_atr) and l <= qml_low):
                    score = 40.0
                    if in_kz: score += 20.0
                    swing_range = break_hh - head_ll
                    if swing_range > 0:
                        fib_ratio = (break_hh - qml_low) / swing_range
                        if 0.58 <= fib_ratio <= 0.82: score += 20.0

                    has_rejection = (min(c, o) - l) >= (0.35 * candle_range) or (c > o and (c - o) >= (0.4 * candle_range))
                    if has_rejection: score += 15.0
                    if h1_trend == 1: score += 10.0

                    if score >= 50.0:
                        grade = "A+" if score >= 85.0 else ("A" if score >= 70.0 else "B")
                        stop_loss = head_ll - (0.3 * curr_atr)
                        self.last_rtm_m15_bar_time = m15_bar_time
                        return {
                            "action": "BUY",
                            "score": score,
                            "grade": grade,
                            "sl": stop_loss,
                            "m15_time": m15_bar_time,
                            "reason": f"RTM Quasimodo Bullish QML [{grade}] ({score:.0f} pts)"
                        }

        except Exception as e:
            logger.error(f"Error checking RTM Confluence M15: {e}")

        return {}

    def _process_rtm_confluence_engine(self, df: pd.DataFrame, symbol: str, spread: float, rtm_mode: str = "ALL"):
        """Dispatches RTM signals to the selected active mode or ALL modes concurrently."""
        sig = self._check_rtm_confluence_m15(symbol)
        if not sig:
            return

        action = sig["action"]
        grade = sig["grade"]
        score = sig["score"]
        sl = sig["sl"]
        reason = sig["reason"]

        # Eligible models configuration
        eligible_models = []
        if rtm_mode in ["ALL", "MODEL_4"]:
            if grade in ["A+", "A"]:
                eligible_models.append({
                    "strat_id": "RTM_M4_CONSERVATIVE",
                    "lot_mult": 1.0,
                    "tp_ratio": 3.0
                })

        if rtm_mode in ["ALL", "MODEL_5"]:
            if grade in ["A+", "A", "B"]:
                lot_m = 2.0 if grade == "A+" else (1.0 if grade == "A" else 0.5)
                eligible_models.append({
                    "strat_id": "RTM_M5_ALL_WEATHER",
                    "lot_mult": lot_m,
                    "tp_ratio": 3.0
                })

        if rtm_mode in ["ALL", "MODEL_6"]:
            if grade in ["A+", "A"]:
                lot_m = 2.0 if grade == "A+" else 1.0
                eligible_models.append({
                    "strat_id": "RTM_M6_ELITE_GROWTH",
                    "lot_mult": lot_m,
                    "tp_ratio": 3.0
                })

        if rtm_mode in ["ALL", "MODEL_7"]:
            if grade in ["A+", "A"]:
                lot_m = 2.0 if grade == "A+" else 1.0
                eligible_models.append({
                    "strat_id": "RTM_M7_MAX_ALPHA",
                    "lot_mult": lot_m,
                    "tp_ratio": 3.5
                })

        for m in eligible_models:
            s_id = m["strat_id"]
            if not self.has_open_positions_for_setup(symbol, s_id):
                opt = {
                    "custom_sl": sl,
                    "tp_ratio": m["tp_ratio"],
                    "lot_multiplier": m["lot_mult"]
                }
                if action == "BUY":
                    self.execute_buy(df, symbol, f"{reason} | {s_id}", opt_params=opt, strat_id=s_id)
                elif action == "SELL":
                    self.execute_sell(df, symbol, f"{reason} | {s_id}", opt_params=opt, strat_id=s_id)

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

    def execute_buy(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None, strat_id: str = "RTM_M5_ALL_WEATHER", **kwargs):
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
            tp2 = ask + (sl_dist * 1.8)
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
            tp2 = ask + (sl_dist * 2.0)
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
            if sl_dist < 3.50: sl = ask - 3.50; sl_dist = 3.50
            if sl_dist > 8.50: sl = ask - 8.50; sl_dist = 8.50
            target_rr = opt.get("tp_ratio", 3.0)
            if custom_tp and custom_tp > ask:
                tp2 = float(custom_tp)
            else:
                tp2 = ask + (sl_dist * target_rr)
        else:
            # News Momentum Expansion / Default
            lowest_low = df['low'].iloc[-10:-1].min()
            sl_buffer = 0.50 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 3.50: sl = ask - 3.50; sl_dist = 3.50
            if sl_dist > 7.00: sl = ask - 7.00; sl_dist = 7.00
            tp2 = ask + (sl_dist * 1.8)

        total_lot = self.calculate_lot_size(sl_dist, lot_mult=lot_mult)

        # Single Position Plan across ALL Setups: 1.0% Risk for Clean Statistical Benchmarking
        res1 = self.connector.open_order(symbol, "BUY", total_lot, sl, tp2, magic_p1, f"Gold_{strat_id[:8]}")
        t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
        self.benchmark_tracker.register_trade(t1, 0, symbol, "BUY", ask, sl, total_lot, strat_id)
        self.add_log(f"🟢 [BUY OPENED] [{strat_id}] {reason} | Single 1.0% Risk: TP {tp2:.2f} (+{abs(tp2-ask)*100:.0f} pts) / SL {sl:.2f} (-{sl_dist*100:.0f} pts) | Lot: {total_lot}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("BUY", symbol, total_lot, ask, sl, tp2, reason)

    def execute_sell(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None, strat_id: str = "RTM_M5_ALL_WEATHER", **kwargs):
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
            tp2 = bid - (sl_dist * 1.8)
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
            tp2 = bid - (sl_dist * 2.0)
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
            if sl_dist < 3.50: sl = bid + 3.50; sl_dist = 3.50
            if sl_dist > 8.50: sl = bid + 8.50; sl_dist = 8.50
            target_rr = opt.get("tp_ratio", 3.0)
            if custom_tp and custom_tp < bid:
                tp2 = float(custom_tp)
            else:
                tp2 = bid - (sl_dist * target_rr)
        else:
            # News Momentum Expansion / Default
            highest_high = df['high'].iloc[-10:-1].max()
            sl_buffer = 0.50 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 3.50: sl = bid + 3.50; sl_dist = 3.50
            if sl_dist > 7.00: sl = bid + 7.00; sl_dist = 7.00
            tp2 = bid - (sl_dist * 1.8)

        total_lot = self.calculate_lot_size(sl_dist, lot_mult=lot_mult)

        # Single Position Plan across ALL Setups: 1.0% Risk for Clean Statistical Benchmarking
        res1 = self.connector.open_order(symbol, "SELL", total_lot, sl, tp2, magic_p1, f"Gold_{strat_id[:8]}")
        t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
        self.benchmark_tracker.register_trade(t1, 0, symbol, "SELL", bid, sl, total_lot, strat_id)
        self.add_log(f"🔴 [SELL OPENED] [{strat_id}] {reason} | Single 1.0% Risk: TP {tp2:.2f} (+{abs(bid-tp2)*100:.0f} pts) / SL {sl:.2f} (-{sl_dist*100:.0f} pts) | Lot: {total_lot}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("SELL", symbol, total_lot, bid, sl, tp2, reason)

    def calculate_lot_size(self, sl_dist: float, lot_mult: float = 1.0) -> float:
        risk_pct = self.config.get("strategy", {}).get("risk_percent", 1.0)
        acc = self.connector.get_account_info()
        balance = acc.get("balance", 10000.0)
        risk_money = balance * (risk_pct / 100.0)

        lot = (risk_money / (sl_dist * 100.0 + 1e-9)) * lot_mult

        # Dynamic Lot Reduction (Only if enabled in config, default false for Option A)
        dynamic_reduction = self.config.get("strategy", {}).get("dynamic_lot_reduction", False)
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

        # Iterate through every strategy setup independently
        for strat_id, s_magics in STRATEGY_MAGIC_MAP.items():
            pos1_magic = s_magics["pos1"]
            pos2_magic = s_magics["pos2"]
            pos3_magic = s_magics["pos3"]

            pos1_list = [p for p in positions if p.get('magic') == pos1_magic]
            pos2_list = [p for p in positions if p.get('magic') == pos2_magic]
            pos3_list = [p for p in positions if p.get('magic') == pos3_magic]

            # Multi-Stage R-Step Trailing Lock:
            # 1. At >= 1.0R -> Lock Break-Even (+0.30 USD)
            # 2. At >= 2.0R -> Lock +1.0R Profit
            # 3. At >= 2.6R -> Lock +1.8R Profit
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
                        target_rr = 3.5 if strat_id == "RTM_M7_MAX_ALPHA" else (3.0 if strat_id.startswith("RTM_") else (2.0 if strat_id == "SMC_X_STO_H1" else 1.8))
                        initial_r = abs(open_p - tp) / target_rr
                        self.initial_risk_map[t_id] = initial_r
                    else:
                        initial_r = 5.0

                if initial_r <= 0.50:
                    continue

                if ptype == "BUY":
                    profit_dist = bid - open_p
                    r_profit = profit_dist / initial_r

                    # Step 3: At >= 2.6R -> Lock +1.8R Profit
                    if r_profit >= 2.6:
                        target_sl = round(open_p + (initial_r * 1.8), 2)
                        if sl < target_sl - 0.10:
                            self.connector.modify_position(t_id, target_sl, tp)
                            self.add_log(f"🎯 [PROFIT LOCKED +1.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.8R ({target_sl:.2f})", "SUCCESS")
                    # Step 2: At >= 2.0R -> Lock +1.0R Profit
                    elif r_profit >= 2.0:
                        target_sl = round(open_p + (initial_r * 1.0), 2)
                        if sl < target_sl - 0.10:
                            self.connector.modify_position(t_id, target_sl, tp)
                            self.add_log(f"💰 [PROFIT LOCKED +1.0R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.0R ({target_sl:.2f})", "SUCCESS")
                    # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                    elif r_profit >= 1.0:
                        target_sl = round(open_p + 0.30, 2)
                        if sl < target_sl - 0.10:
                            self.connector.modify_position(t_id, target_sl, tp)
                            self.add_log(f"🛡️ [BREAK-EVEN LOCKED] [{strat_id}] Ticket #{t_id} reached 1.0R | SL locked to BE ({target_sl:.2f})", "SUCCESS")

                elif ptype == "SELL":
                    profit_dist = open_p - ask
                    r_profit = profit_dist / initial_r

                    # Step 3: At >= 2.6R -> Lock +1.8R Profit
                    if r_profit >= 2.6:
                        target_sl = round(open_p - (initial_r * 1.8), 2)
                        if sl == 0 or sl > target_sl + 0.10:
                            self.connector.modify_position(t_id, target_sl, tp)
                            self.add_log(f"🎯 [PROFIT LOCKED +1.8R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.8R ({target_sl:.2f})", "SUCCESS")
                    # Step 2: At >= 2.0R -> Lock +1.0R Profit
                    elif r_profit >= 2.0:
                        target_sl = round(open_p - (initial_r * 1.0), 2)
                        if sl == 0 or sl > target_sl + 0.10:
                            self.connector.modify_position(t_id, target_sl, tp)
                            self.add_log(f"💰 [PROFIT LOCKED +1.0R] [{strat_id}] Ticket #{t_id} at {r_profit:.1f}R | SL locked to +1.0R ({target_sl:.2f})", "SUCCESS")
                    # Step 1: At >= 1.0R -> Lock Break-Even (+0.30 USD)
                    elif r_profit >= 1.0:
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
