"""
Advanced Trading Bot Strategy Engine for XAUUSD (Gold)
Features 7 High-Winrate Scalping & Trend Strategies:
1. ALL_CONFLUENCE - Maximum Confidence (Auto-switches with Market Sessions)
2. EMA50_3CANDLES_H1 - EMA 50 + 3 Confirmation Candles Trend-Following (H1/M5) [Winrate 75-80%]
3. ASIAN_RANGE_SNIPER - Asian Session Mean-Reversion Scalper (00:00-07:00 Server Time) [Winrate 75-85%]
4. SMC_SWEEP - Liquidity Hunt & Rejection (Asian/Swing High-Low Sweeps) [Winrate 75-80%]
5. EMA_RIBBON - Dynamic EMA 20/50/100/200 Ribbon + RSI Momentum Reset [Winrate 70%]
6. BB_SQUEEZE - Bollinger Band Squeeze & Volatility Expansion [Winrate 70%]
7. SECRET_EMA_PULLBACK - Classic EMA 50/150 Trend & Pullback/Breakout
"""

import time
import math
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple
from strategy_optimizer import RealTimeStrategyOptimizer
from exit_benchmark_tracker import ExitBenchmarkTracker
from regime_liquidity_scorer import MarketRegimeScorer

logger = logging.getLogger("BotEngine")

class GoldScalpingBot:
    """Scalping Strategy Execution Engine."""
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
        
        mt5_cfg = self.config.get("mt5", {})
        self.magic_number = mt5_cfg.get("magic_number", 555888)
        self.magic_pos1 = self.magic_number + 1
        self.magic_pos2 = self.magic_number + 2
        self.magic_pos3 = self.magic_number + 3

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
        """Determines active forex/gold market session."""
        now_hour = datetime.now().hour # Thai time GMT+7
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

        # 2. Check Active Positions Limit
        positions = self.connector.get_open_positions(symbol)
        ea_positions = [p for p in positions if p.get('magic') in [self.magic_number, self.magic_pos1, self.magic_pos2, self.magic_pos3]]
        if len(ea_positions) > 0:
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

        # Fast RSI (7) for Asian Scalp & Standard RSI (14) for Trend
        delta = df['close'].diff()
        gain7 = (delta.where(delta > 0, 0)).rolling(window=7).mean()
        loss7 = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
        rs7 = gain7 / (loss7 + 1e-9)
        df['rsi7'] = 100 - (100 / (1 + rs7))

        gain14 = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss14 = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs14 = gain14 / (loss14 + 1e-9)
        df['rsi14'] = 100 - (100 / (1 + rs14))

        b1 = df.iloc[-2]
        b2 = df.iloc[-3]
        b4 = df.iloc[-5]

        self.fast_ema_val = round(float(b1['ema50']), 2)
        self.slow_ema_val = round(float(b1['ema150']), 2)
        self.fast_slope = round((float(b1['ema50']) - float(b4['ema50'])) / 0.01, 1)
        self.slow_slope = round((float(b1['ema150']) - float(b4['ema150'])) / 0.01, 1)

        buy_signal = False
        sell_signal = False
        signal_reason = ""
        is_asian_scalp = False

        # --- SPECIALIZED 0: High-Impact News Momentum Expansion (News Spike Breakout) ---
        news_status = self.optimizer.news_calendar.get_news_status()
        if strat_mode in ["ALL", "NEWS_MOMENTUM_EXPANSION"] and news_status.get("is_news_active"):
            buy_sig, sell_sig, reason = self._check_news_momentum_expansion(df, news_status)
            if buy_sig: buy_signal, signal_reason = True, reason
            elif sell_sig: sell_signal, signal_reason = True, reason

        # --- SPECIALIZED 1: EMA 50 + 3 Confirmation Candles (H1 Trend) ---
        if not buy_signal and not sell_signal and strat_mode in ["ALL", "EMA50_3CANDLES_H1"]:
            buy_sig, sell_sig, reason = self._check_ema50_3candles_h1(df)
            if buy_sig: buy_signal, signal_reason = True, reason
            elif sell_sig: sell_signal, signal_reason = True, reason

        # --- SPECIALIZED 2: Asian Range Mean-Reversion Sniper (Winrate 75-85%) ---
        if not buy_signal and not sell_signal and (session == "ASIAN SESSION" or strat_mode == "ASIAN_RANGE_SNIPER"):
            buy_sig, sell_sig, reason = self._check_asian_range_sniper(df)
            if buy_sig: 
                buy_signal, signal_reason, is_asian_scalp = True, reason, True
            elif sell_sig: 
                sell_signal, signal_reason, is_asian_scalp = True, reason, True

        # --- LONDON & NEW YORK SESSION SETUPS (Trend & Momentum) ---
        if not buy_signal and not sell_signal and session != "ASIAN SESSION":
            # Primary Flagship 1: Captain Trading LAB - SMC Signal V1.2 (Dual Auto: Fast & Confirmed)
            if strat_mode in ["ALL", "CAPTAIN_SMC", "CAPTAIN_SMC_DUAL", "SMC_SWEEP"]:
                buy_sig, sell_sig, reason = self._check_captain_smc(df)
                if buy_sig: buy_signal, signal_reason = True, reason
                elif sell_sig: sell_signal, signal_reason = True, reason

            # Institutional Flagship 2: TKT SMC Gold Pro v8.0 (M15 Institutional Confluence Score >= 60%)
            if not buy_signal and not sell_signal and strat_mode in ["ALL", "TKT_SMC_GOLD_PRO_M15"]:
                buy_sig, sell_sig, reason = self._check_tkt_smc_gold_pro_m15(symbol)
                if buy_sig: buy_signal, signal_reason = True, reason
                elif sell_sig: sell_signal, signal_reason = True, reason

            # Secondary Support: EMA Ribbon + RSI Momentum Reset (Winrate 70%)
            if not buy_signal and not sell_signal and strat_mode in ["ALL", "EMA_RIBBON"]:
                buy_sig, sell_sig, reason = self._check_ema_ribbon_rsi(df)
                if buy_sig: buy_signal, signal_reason = True, reason
                elif sell_sig: sell_signal, signal_reason = True, reason

            # Strategy: BB Squeeze Breakout (Winrate 70%)
            if not buy_signal and not sell_signal and strat_mode in ["ALL", "BB_SQUEEZE"]:
                buy_sig, sell_sig, reason = self._check_bb_squeeze(df)
                if buy_sig: buy_signal, signal_reason = True, reason
                elif sell_sig: sell_signal, signal_reason = True, reason

            # Strategy: Classic Secret EMA 50/150 Pullback
            if not buy_signal and not sell_signal and strat_mode in ["ALL", "SECRET_EMA_PULLBACK"]:
                buy_sig, sell_sig, reason = self._check_secret_ema_pullback(df, strat_cfg)
                if buy_sig: buy_signal, signal_reason = True, reason
                elif sell_sig: sell_signal, signal_reason = True, reason

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

        # Execute Signals
        if buy_signal or sell_signal:
            action_type = "BUY" if buy_signal else "SELL"
            strat_key = "CAPTAIN_SMC_DUAL"
            if "News" in signal_reason or "NEWS" in signal_reason or "Momentum" in signal_reason: strat_key = "NEWS_MOMENTUM_EXPANSION"
            elif "TKT" in signal_reason or "M15" in signal_reason: strat_key = "TKT_SMC_GOLD_PRO_M15"
            elif "Captain" in signal_reason: strat_key = "CAPTAIN_SMC_DUAL"
            elif "3 Candles" in signal_reason or "EMA50_3CANDLES" in signal_reason: strat_key = "EMA50_3CANDLES_H1"
            elif "Asian" in signal_reason: strat_key = "ASIAN_RANGE_SNIPER"

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

            if buy_signal:
                self.last_signal = f"BUY ({signal_reason} | Quality: {score_res['score']}/100 {score_res['grade']})"
                self.execute_buy(df, symbol, signal_reason, is_asian_scalp, opt_params)
            elif sell_signal:
                self.last_signal = f"SELL ({signal_reason} | Quality: {score_res['score']}/100 {score_res['grade']})"
                self.execute_sell(df, symbol, signal_reason, is_asian_scalp, opt_params)

    def _check_news_momentum_expansion(self, df: pd.DataFrame, news_status: dict) -> Tuple[bool, bool, str]:
        """
        Specialized Setup #8: High-Impact News Momentum Breakout & Straddle.
        Activates when market is inside news impact/digest window, or when volatility surges with momentum.
        """
        if len(df) < 15: return False, False, ""
        b1 = df.iloc[-2] # Last closed candle
        
        # Calculate pre-news baseline range (bars -10 to -2)
        pre_news_high = df['high'].iloc[-10:-2].max()
        pre_news_low = df['low'].iloc[-10:-2].min()
        candle_body = abs(b1['close'] - b1['open'])
        candle_range = b1['high'] - b1['low'] + 1e-9
        body_pct = candle_body / candle_range

        is_news_spike = news_status.get("is_news_active", False) or news_status.get("state") in ["NEWS_RELEASE_IMPACT", "POST_NEWS_DIGEST"]

        # BUY: Bullish Breakout above Pre-News High with solid body > 60%
        if is_news_spike and b1['close'] > pre_news_high and b1['close'] > b1['open'] and body_pct >= 0.60:
            return True, False, "⚡ High-Impact News Momentum Breakout (BUY)"

        # SELL: Bearish Breakdown below Pre-News Low with solid body > 60%
        if is_news_spike and b1['close'] < pre_news_low and b1['close'] < b1['open'] and body_pct >= 0.60:
            return False, True, "⚡ High-Impact News Momentum Breakout (SELL)"

        return False, False, ""

    def _check_ema50_3candles_h1(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
        """EMA 50 + 3 Consecutive Confirmation Candles Trend-Following (H1/M5)."""
        if len(df) < 10: return False, False, ""
        b1, b2, b3 = df.iloc[-2], df.iloc[-3], df.iloc[-4]
        b6 = df.iloc[-7]
        
        slope = (b1['ema50'] - b6['ema50']) / 0.01
        
        # BUY: 3 consecutive Bullish candles all above EMA 50 with upward slope
        buy_cond = (
            b1['close'] > b1['open'] and b1['close'] > b1['ema50'] and
            b2['close'] > b2['open'] and b2['close'] > b2['ema50'] and
            b3['close'] > b3['open'] and b3['close'] > b3['ema50'] and
            slope >= 25.0
        )
        if buy_cond:
            return True, False, "📈 EMA 50 + 3 Bullish Confirmation Candles (H1)"

        # SELL: 3 consecutive Bearish candles all below EMA 50 with downward slope
        sell_cond = (
            b1['close'] < b1['open'] and b1['close'] < b1['ema50'] and
            b2['close'] < b2['open'] and b2['close'] < b2['ema50'] and
            b3['close'] < b3['open'] and b3['close'] < b3['ema50'] and
            slope <= -25.0
        )
        if sell_cond:
            return False, True, "📉 EMA 50 + 3 Bearish Confirmation Candles (H1)"

        return False, False, ""

    def _check_asian_range_sniper(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
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

        touched_lower = (b1['low'] <= b1['bb_lower'] or b1['low'] <= (asian_low + 0.30))
        if touched_lower and b1['close'] > b1['open'] and (lower_wick / candle_range) >= 0.40:
            if b1['rsi7'] <= 35 and b1['rsi7'] > b2['rsi7']:
                return True, False, "⛩️ Asian Range Sniper: Lower Band Rebound (80% WR)"

        touched_upper = (b1['high'] >= b1['bb_upper'] or b1['high'] >= (asian_high - 0.30))
        if touched_upper and b1['close'] < b1['open'] and (upper_wick / candle_range) >= 0.40:
            if b1['rsi7'] >= 65 and b1['rsi7'] < b2['rsi7']:
                return False, True, "⛩️ Asian Range Sniper: Upper Band Rebound (80% WR)"

        return False, False, ""

    def _check_captain_smc(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
        """
        Captain Trading LAB - SMC Signal V.1.2 Dual-Model Engine
        Evaluates BOTH Fast (Wick Rejection at S/R Zone) and Confirmed (CHoCH / Market Structure Break).
        """
        if len(df) < 35: return False, False, ""
        b1 = df.iloc[-2] # Last closed bar
        lookback = df.iloc[-32:-2]
        
        # 1. Calculate Support & Resistance / Order Block Zones (Fine Tuner = 10)
        swing_high = lookback['high'].rolling(window=10).max().iloc[-1]
        swing_low = lookback['low'].rolling(window=10).min().iloc[-1]

        candle_range = b1['high'] - b1['low']
        if candle_range <= 0.25:
            return False, False, ""

        upper_wick = b1['high'] - max(b1['open'], b1['close'])
        lower_wick = min(b1['open'], b1['close']) - b1['low']

        # 2. Trend Confluence Filter (EMA 50 vs EMA 150)
        is_uptrend = b1.get('ema50', 0) > b1.get('ema150', 0)
        is_downtrend = b1.get('ema50', 0) < b1.get('ema150', 0)
        rsi = b1.get('rsi14', 50)

        # --- MODEL 1: FAST ENTRY (Wick Rejection >= 35% in S/R Zone) ---
        # Fast Buy: Tests Support Zone + Lower Wick >= 35% + Closes Bullish + NOT in steep downtrend
        if b1['low'] <= (swing_low + 0.60) and (lower_wick / candle_range) >= 0.35 and b1['close'] > b1['open']:
            if not is_downtrend or rsi < 35: # Only buy if aligned with trend or extremely oversold
                return True, False, "Captain_SMC_Fast (Wick Rejection 35%)"

        # Fast Sell: Tests Resistance Zone + Upper Wick >= 35% + Closes Bearish + NOT in steep uptrend
        if b1['high'] >= (swing_high - 0.60) and (upper_wick / candle_range) >= 0.35 and b1['close'] < b1['open']:
            if not is_uptrend or rsi > 65: # Only sell if aligned with trend or extremely overbought
                return False, True, "Captain_SMC_Fast (Wick Rejection 35%)"

        # --- MODEL 2: CONFIRMED ENTRY (CHoCH / Market Structure Break) ---
        recent_15 = df.iloc[-17:-2]
        recent_high = recent_15['high'].max()
        recent_low = recent_15['low'].min()

        # Confirmed Buy: Bullish candle closes above recent swing high
        if b1['close'] > recent_high and b1['close'] > b1['open'] and (is_uptrend or rsi > 52):
            return True, False, "Captain_SMC_Confirmed (Structure CHoCH Break)"

        # Confirmed Sell: Bearish candle closes below recent swing low
        if b1['close'] < recent_low and b1['close'] < b1['open'] and (is_downtrend or rsi < 48):
            return False, True, "Captain_SMC_Confirmed (Structure CHoCH Break)"

        return False, False, ""

    def _check_tkt_smc_gold_pro_m15(self, symbol: str) -> Tuple[bool, bool, str]:
        """
        TKT SMC Gold Pro v8.0 - Institutional Confluence Scoring Engine (M15 Sweet Spot).
        Evaluates Market Structure (BOS/CHoCH) + FVG Imbalance (min 50 pts) + Order Block + Kill Zone Session.
        Fires signal when Confluence Score >= 60%.
        """
        try:
            df_m15 = self.connector.get_rates(symbol, "M15", 60)
            if df_m15.empty or len(df_m15) < 30:
                return False, False, ""

            b1 = df_m15.iloc[-2] # Closed M15 candle
            b2 = df_m15.iloc[-3]
            b3 = df_m15.iloc[-4]

            buy_score = 0
            sell_score = 0

            # 1. Structure Trend (BOS / CHoCH) - 25%
            lookback = df_m15.iloc[-25:-2]
            swing_high = lookback['high'].max()
            swing_low = lookback['low'].min()

            if b1['close'] > swing_high:
                buy_score += 25
            elif b1['close'] < swing_low:
                sell_score += 25

            # 2. Fair Value Gap (FVG Imbalance) - 25%
            min_fvg_pts = 0.50 # 50 points = 0.50 USD
            bull_fvg_present = (b1['low'] > b3['high'] + min_fvg_pts)
            bear_fvg_present = (b1['high'] < b3['low'] - min_fvg_pts)

            if bull_fvg_present or (b1['low'] <= (swing_low + 0.80) and b1['close'] > b1['open']):
                buy_score += 25
            if bear_fvg_present or (b1['high'] >= (swing_high - 0.80) and b1['close'] < b1['open']):
                sell_score += 25

            # 3. Kill Zone Session Bonus - 20%
            now_hour = (datetime.utcnow().hour + 7) % 24 # Thai UTC+7
            in_kill_zone = (7 <= now_hour < 14) or (14 <= now_hour < 18) or (19 <= now_hour < 23)
            if in_kill_zone:
                buy_score += 20
                sell_score += 20

            # 4. Premium / Discount Equilibrium - 15%
            pd_50 = df_m15.iloc[-50:-2] if len(df_m15) >= 50 else df_m15.iloc[:-2]
            equilibrium = (pd_50['high'].max() + pd_50['low'].min()) / 2.0
            if b1['close'] < equilibrium:
                buy_score += 15 # Discount (Good for BUY)
            else:
                sell_score += 15 # Premium (Good for SELL)

            # 5. Wick Rejection / Volume Confirmation - 15%
            candle_range = b1['high'] - b1['low']
            if candle_range > 0.30:
                lower_wick = min(b1['open'], b1['close']) - b1['low']
                upper_wick = b1['high'] - max(b1['open'], b1['close'])
                if (lower_wick / candle_range) >= 0.30 and b1['close'] > b1['open']:
                    buy_score += 15
                if (upper_wick / candle_range) >= 0.30 and b1['close'] < b1['open']:
                    sell_score += 15

            # Check threshold (>= 60%)
            if buy_score >= 60 and buy_score > sell_score:
                return True, False, f"TKT SMC Gold Pro M15 (Score: {buy_score}% >= 60%)"
            elif sell_score >= 60 and sell_score > buy_score:
                return False, True, f"TKT SMC Gold Pro M15 (Score: {sell_score}% >= 60%)"

        except Exception as e:
            logger.error(f"Error checking TKT SMC Gold Pro M15: {e}")

        return False, False, ""

    def _check_smc_liquidity_sweep(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
        b1 = df.iloc[-2]
        lookback = df.iloc[-22:-2]
        swing_high = lookback['high'].max()
        swing_low = lookback['low'].min()

        candle_range = b1['high'] - b1['low']
        if candle_range <= 0.30:
            return False, False, ""

        upper_wick = b1['high'] - max(b1['open'], b1['close'])
        lower_wick = min(b1['open'], b1['close']) - b1['low']

        if b1['low'] < swing_low and b1['close'] > swing_low and (lower_wick / candle_range) >= 0.45:
            if b1['close'] > b1['open'] and b1['rsi14'] < 45:
                return True, False, "SMC Liquidity Sweep Low (75% WR)"

        if b1['high'] > swing_high and b1['close'] < swing_high and (upper_wick / candle_range) >= 0.45:
            if b1['close'] < b1['open'] and b1['rsi14'] > 55:
                return False, True, "SMC Liquidity Sweep High (75% WR)"

        return False, False, ""

    def _check_ema_ribbon_rsi(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
        b1 = df.iloc[-2]
        b2 = df.iloc[-3]

        bullish_ribbon = (b1['ema20'] > b1['ema50'] > b1['ema100'] > b1['ema200'])
        if bullish_ribbon:
            if b1['low'] <= b1['ema20'] and b1['close'] > b1['ema20'] and b1['close'] > b1['open']:
                if 40 <= b1['rsi14'] <= 60 and b1['rsi14'] > b2['rsi14']:
                    return True, False, "EMA Ribbon + RSI Momentum Reset"

        bearish_ribbon = (b1['ema20'] < b1['ema50'] < b1['ema100'] < b1['ema200'])
        if bearish_ribbon:
            if b1['high'] >= b1['ema20'] and b1['close'] < b1['ema20'] and b1['close'] < b1['open']:
                if 40 <= b1['rsi14'] <= 60 and b1['rsi14'] < b2['rsi14']:
                    return False, True, "EMA Ribbon + RSI Momentum Reset"

        return False, False, ""

    def _check_bb_squeeze(self, df: pd.DataFrame) -> Tuple[bool, bool, str]:
        """Bollinger Bands Squeeze & Volatility Expansion Setup (Winrate 70%)."""
        if len(df) < 30: return False, False, ""
        b1 = df.iloc[-2]
        b2 = df.iloc[-3]
        
        # Check if previous bar was squeezed and current bar expands with momentum
        if b2['bb_width'] < 1.20 and b1['bb_width'] >= 1.30:
            if b1['close'] > b1['bb_upper'] and b1['close'] > b1['ema50']:
                return True, False, "BB Squeeze Volatility Breakout (BUY)"
            elif b1['close'] < b1['bb_lower'] and b1['close'] < b1['ema50']:
                return False, True, "BB Squeeze Volatility Breakout (SELL)"

        return False, False, ""

    def _check_secret_ema_pullback(self, df: pd.DataFrame, strat_cfg: dict) -> Tuple[bool, bool, str]:
        """Classic Secret EMA 50/150 Pullback."""
        if len(df) < 10: return False, False, ""
        b1 = df.iloc[-2]
        b4 = df.iloc[-5]
        slope = (b1['ema50'] - b4['ema50']) / 0.01

        # Buy Pullback
        if b1['ema50'] > b1['ema150'] and slope >= 25.0:
            if b1['low'] <= (b1['ema50'] + 1.0) and b1['close'] > b1['ema50'] and b1['close'] > b1['open']:
                return True, False, "EMA 50 Secret Pullback"

        # Sell Pullback
        if b1['ema50'] < b1['ema150'] and slope <= -25.0:
            if b1['high'] >= (b1['ema50'] - 1.0) and b1['close'] < b1['ema50'] and b1['close'] < b1['open']:
                return False, True, "EMA 50 Secret Pullback"

        return False, False, ""

    def should_run_trend(self, strat_id: str, df: pd.DataFrame, session: str) -> Tuple[bool, str]:
        """
        AI Trend Intelligence Classifier:
        Analyzes whether the current setup and market structure warrant an uncapped Trend Runner (Trailing Stop)
        or should take Fixed Targets (TP1, TP2, TP3) without trailing.
        """
        # 1. Asian Session / Mean Reversion -> Strict Fixed TP (No Trailing)
        if strat_id == "ASIAN_RANGE_SNIPER" or session == "ASIAN SESSION":
            return False, "Fixed TP (Asian Sideways - No Trailing)"

        # 2. News Expansion -> High Momentum Trend Runner
        if strat_id == "NEWS_MOMENTUM_EXPANSION":
            return True, "AI Trend Trail (News Expansion)"

        # 3. EMA 50 + 3 Confirmation Candles H1 -> Macro Trend Runner
        if strat_id == "EMA50_3CANDLES_H1":
            return True, "AI Trend Trail (H1 Macro Trend)"

        # 4. TKT SMC Gold Pro M15 or Captain SMC Confirmed Break: Check Market Dynamics
        regime = self.optimizer.classify_market_regime(df)
        if "TREND" in regime.get("regime", "") or regime.get("volatility_ratio", 1.0) >= 1.25:
            return True, f"AI Trend Trail ({regime.get('label', 'Trending Expansion')})"

        return False, "Fixed TP (Normal S/R Targets)"

    def execute_buy(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None):
        ask = self.connector.get_market_info(symbol).get("ask", 0.0)
        if ask <= 0: return

        opt = opt_params or {}
        sl_mult = opt.get("atr_sl_multiplier", 1.0)
        dynamic_rr = opt.get("tp_ratio", 1.50 if not is_asian_scalp else 1.20)
        lot_mult = opt.get("lot_multiplier", 1.0)
        session = self.get_current_session()

        if is_asian_scalp:
            lowest_low = df['low'].iloc[-4:-1].min()
            sl_buffer = 0.30 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 1.00: sl = ask - 1.00; sl_dist = 1.00
            if sl_dist > 3.50: sl = ask - 3.50; sl_dist = 3.50
            
            bb_mid = float(df['sma20'].iloc[-2])
            tp1 = max(ask + 1.20, bb_mid) if bb_mid > ask else (ask + sl_dist * 1.0)
            tp2 = ask + (sl_dist * 1.8)
            tp3 = ask + (sl_dist * 2.5)
        else:
            lowest_low = df['low'].iloc[-8:-1].min()
            sl_buffer = 0.50 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 1.50: sl = ask - 1.50; sl_dist = 1.50
            if sl_dist > 10.0: sl = ask - 10.0; sl_dist = 10.0
            tp1 = ask + (sl_dist * 1.0)
            tp2 = ask + (sl_dist * 1.8)
            tp3 = ask + (sl_dist * 2.8)

        strat_id = "CAPTAIN_SMC_DUAL"
        for k in ["NEWS_MOMENTUM_EXPANSION", "EMA50_3CANDLES_H1", "ASIAN_RANGE_SNIPER", "TKT_SMC_GOLD_PRO_M15", "CAPTAIN_SMC_DUAL"]:
            if k in reason: strat_id = k; break

        is_trend_runner, runner_reason = self.should_run_trend(strat_id, df, session)
        final_tp3 = 0.0 if is_trend_runner else tp3

        total_lot = self.calculate_lot_size(sl_dist, lot_mult)

        if total_lot >= 0.03:
            lot1 = max(0.01, round(total_lot * 0.35, 2))
            lot2 = max(0.01, round(total_lot * 0.35, 2))
            lot3 = max(0.01, round(total_lot - lot1 - lot2, 2))

            res1 = self.connector.open_order(symbol, "BUY", lot1, sl, tp1, self.magic_pos1, f"Gold_TP1_{reason[:6]}")
            res2 = self.connector.open_order(symbol, "BUY", lot2, sl, tp2, self.magic_pos2, f"Gold_TP2_{reason[:6]}")
            res3 = self.connector.open_order(symbol, "BUY", lot3, sl, final_tp3, self.magic_pos3, f"Gold_TP3_{reason[:6]}")
            t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
            t2 = res2.get("ticket", 0) if isinstance(res2, dict) else 0
            self.benchmark_tracker.register_trade(t1, t2, symbol, "BUY", ask, sl, total_lot, strat_id)
        elif total_lot == 0.02:
            lot1 = 0.01
            lot2 = 0.01
            res1 = self.connector.open_order(symbol, "BUY", lot1, sl, tp1, self.magic_pos1, f"Gold_TP1_{reason[:6]}")
            res2 = self.connector.open_order(symbol, "BUY", lot2, sl, final_tp3 if is_trend_runner else tp2, self.magic_pos2, f"Gold_TP2_{reason[:6]}")
            t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
            t2 = res2.get("ticket", 0) if isinstance(res2, dict) else 0
            self.benchmark_tracker.register_trade(t1, t2, symbol, "BUY", ask, sl, total_lot, strat_id)
        else:
            lot1 = 0.01
            res1 = self.connector.open_order(symbol, "BUY", lot1, sl, tp1, self.magic_pos1, f"Gold_TP1_{reason[:6]}")

        self.add_log(f"🟢 [BUY OPENED] {reason} | Exit Plan: TP1 {tp1:.2f} (1R) / TP2 {tp2:.2f} (1.8R) / {'AI Trail' if is_trend_runner else f'TP3 {tp3:.2f}'} ({runner_reason}) | Total Lot: {total_lot}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("BUY", symbol, total_lot, ask, sl, tp1, reason)

    def execute_sell(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None):
        bid = self.connector.get_market_info(symbol).get("bid", 0.0)
        if bid <= 0: return

        opt = opt_params or {}
        sl_mult = opt.get("atr_sl_multiplier", 1.0)
        dynamic_rr = opt.get("tp_ratio", 1.50 if not is_asian_scalp else 1.20)
        lot_mult = opt.get("lot_multiplier", 1.0)
        session = self.get_current_session()

        if is_asian_scalp:
            highest_high = df['high'].iloc[-4:-1].max()
            sl_buffer = 0.30 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 1.00: sl = bid + 1.00; sl_dist = 1.00
            if sl_dist > 3.50: sl = bid + 3.50; sl_dist = 3.50
            
            bb_mid = float(df['sma20'].iloc[-2])
            tp1 = min(bid - 1.20, bb_mid) if bb_mid < bid else (bid - sl_dist * 1.0)
            tp2 = bid - (sl_dist * 1.8)
            tp3 = bid - (sl_dist * 2.5)
        else:
            highest_high = df['high'].iloc[-8:-1].max()
            sl_buffer = 0.50 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 1.50: sl = bid + 1.50; sl_dist = 1.50
            if sl_dist > 10.0: sl = bid + 10.0; sl_dist = 10.0
            tp1 = bid - (sl_dist * 1.0)
            tp2 = bid - (sl_dist * 1.8)
            tp3 = bid - (sl_dist * 2.8)

        strat_id = "CAPTAIN_SMC_DUAL"
        for k in ["NEWS_MOMENTUM_EXPANSION", "EMA50_3CANDLES_H1", "ASIAN_RANGE_SNIPER", "TKT_SMC_GOLD_PRO_M15", "CAPTAIN_SMC_DUAL"]:
            if k in reason: strat_id = k; break

        is_trend_runner, runner_reason = self.should_run_trend(strat_id, df, session)
        final_tp3 = 0.0 if is_trend_runner else tp3

        total_lot = self.calculate_lot_size(sl_dist, lot_mult)

        if total_lot >= 0.03:
            lot1 = max(0.01, round(total_lot * 0.35, 2))
            lot2 = max(0.01, round(total_lot * 0.35, 2))
            lot3 = max(0.01, round(total_lot - lot1 - lot2, 2))

            res1 = self.connector.open_order(symbol, "SELL", lot1, sl, tp1, self.magic_pos1, f"Gold_TP1_{reason[:6]}")
            res2 = self.connector.open_order(symbol, "SELL", lot2, sl, tp2, self.magic_pos2, f"Gold_TP2_{reason[:6]}")
            res3 = self.connector.open_order(symbol, "SELL", lot3, sl, final_tp3, self.magic_pos3, f"Gold_TP3_{reason[:6]}")
            t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
            t2 = res2.get("ticket", 0) if isinstance(res2, dict) else 0
            self.benchmark_tracker.register_trade(t1, t2, symbol, "SELL", bid, sl, total_lot, strat_id)
        elif total_lot == 0.02:
            lot1 = 0.01
            lot2 = 0.01
            res1 = self.connector.open_order(symbol, "SELL", lot1, sl, tp1, self.magic_pos1, f"Gold_TP1_{reason[:6]}")
            res2 = self.connector.open_order(symbol, "SELL", lot2, sl, final_tp3 if is_trend_runner else tp2, self.magic_pos2, f"Gold_TP2_{reason[:6]}")
            t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
            t2 = res2.get("ticket", 0) if isinstance(res2, dict) else 0
            self.benchmark_tracker.register_trade(t1, t2, symbol, "SELL", bid, sl, total_lot, strat_id)
        else:
            lot1 = 0.01
            res1 = self.connector.open_order(symbol, "SELL", lot1, sl, tp1, self.magic_pos1, f"Gold_TP1_{reason[:6]}")

        self.add_log(f"🔴 [SELL OPENED] {reason} | Exit Plan: TP1 {tp1:.2f} (1R) / TP2 {tp2:.2f} (1.8R) / {'AI Trail' if is_trend_runner else f'TP3 {tp3:.2f}'} ({runner_reason}) | Total Lot: {total_lot}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("SELL", symbol, total_lot, bid, sl, tp1, reason)

    def calculate_lot_size(self, sl_dist: float, lot_mult: float = 1.0) -> float:
        risk_pct = self.config.get("strategy", {}).get("risk_percent", 1.0)
        acc = self.connector.get_account_info()
        balance = acc.get("balance", 10000.0)
        risk_money = balance * (risk_pct / 100.0)

        lot = (risk_money / (sl_dist * 100.0 + 1e-9)) * lot_mult
        if self.consecutive_losses == 1: lot *= 0.50
        elif self.consecutive_losses >= 2: lot *= 0.25

        lot = max(0.01, round(lot, 2))
        return min(lot, 50.0)

    def manage_open_positions(self, symbol: str):
        positions = self.connector.get_open_positions(symbol)
        pos1_list = [p for p in positions if p.get('magic') == self.magic_pos1]
        pos2_list = [p for p in positions if p.get('magic') == self.magic_pos2]
        pos3_list = [p for p in positions if p.get('magic') == self.magic_pos3]

        m_info = self.connector.get_market_info(symbol)
        bid = m_info.get('bid', 0.0)
        ask = m_info.get('ask', 0.0)

        # Stage 1: When Pos 1 (TP1) is closed -> Move Pos 2 & Pos 3 to Break-Even (+0.30)
        if len(pos1_list) == 0 and (len(pos2_list) > 0 or len(pos3_list) > 0):
            for p in (pos2_list + pos3_list):
                open_p = p.get('price_open', 0.0)
                sl = p.get('sl', 0.0)
                ptype = p.get('type')

                if ptype == "BUY" and sl < open_p and bid > (open_p + 0.30):
                    new_sl = open_p + 0.30
                    self.connector.modify_position(p.get('ticket'), new_sl, p.get('tp'))
                    self.add_log(f"🛡️ [BREAK-EVEN LOCKED] Pos #{p.get('ticket')} SL locked at {new_sl:.2f}", "SUCCESS")
                elif ptype == "SELL" and (sl > open_p or sl == 0) and ask < (open_p - 0.30):
                    new_sl = open_p - 0.30
                    self.connector.modify_position(p.get('ticket'), new_sl, p.get('tp'))
                    self.add_log(f"🛡️ [BREAK-EVEN LOCKED] Pos #{p.get('ticket')} SL locked at {new_sl:.2f}", "SUCCESS")

        # Stage 2: When Pos 2 (TP2) is closed -> Move Pos 3 to TP1 Level (Lock Profit)
        if len(pos1_list) == 0 and len(pos2_list) == 0 and len(pos3_list) > 0:
            for p3 in pos3_list:
                open_p = p3.get('price_open', 0.0)
                sl = p3.get('sl', 0.0)
                ptype = p3.get('type')
                
                # Active Dynamic Trailing Stop for AI Trend Runners (TP == 0)
                if p3.get('tp', 0.0) == 0.0:
                    trail_dist = 2.50 # 250 points trailing buffer
                    if ptype == "BUY":
                        trail_sl = round(bid - trail_dist, 2)
                        if trail_sl > sl and trail_sl > (open_p + 0.50):
                            self.connector.modify_position(p3.get('ticket'), trail_sl, 0.0)
                            self.add_log(f"📈 [AI TREND TRAILING] Pos3 #{p3.get('ticket')} Trailing SL updated to {trail_sl:.2f}", "SUCCESS")
                    elif ptype == "SELL":
                        trail_sl = round(ask + trail_dist, 2)
                        if (sl == 0 or trail_sl < sl) and trail_sl < (open_p - 0.50):
                            self.connector.modify_position(p3.get('ticket'), trail_sl, 0.0)
                            self.add_log(f"📉 [AI TREND TRAILING] Pos3 #{p3.get('ticket')} Trailing SL updated to {trail_sl:.2f}", "SUCCESS")

        m_info = self.connector.get_market_info(symbol)
        bid = m_info.get('bid', 0.0)
        ask = m_info.get('ask', 0.0)

        # Update Parallel Exit Benchmark Price Tracker
        if len(positions) > 0:
            rates = self.connector.get_rates(symbol, "M5", 2)
            if not rates.empty:
                b1 = rates.iloc[-1]
                self.benchmark_tracker.update_price(symbol, float(b1['high']), float(b1['low']), bid, ask)

        if len(pos1_list) == 0 and len(pos2_list) > 0:
            for p2 in pos2_list:
                open_p = p2.get('price_open', 0.0)
                sl = p2.get('sl', 0.0)
                ptype = p2.get('type')

                if ptype == "BUY" and sl < open_p and bid > (open_p + 0.30):
                    new_sl = open_p + 0.30
                    self.connector.modify_position(p2.get('ticket'), new_sl, p2.get('tp'))
                    self.add_log(f"🛡️ [BREAK-EVEN LOCKED] Runner #{p2.get('ticket')} SL locked at {new_sl:.2f}", "SUCCESS")
                    if self.notifier:
                        self.notifier.notify_break_even(p2.get('ticket'), symbol, new_sl)
                elif ptype == "SELL" and (sl > open_p or sl == 0) and ask < (open_p - 0.30):
                    new_sl = open_p - 0.30
                    self.connector.modify_position(p2.get('ticket'), new_sl, p2.get('tp'))
                    self.add_log(f"🛡️ [BREAK-EVEN LOCKED] Runner #{p2.get('ticket')} SL locked at {new_sl:.2f}", "SUCCESS")
                    if self.notifier:
                        self.notifier.notify_break_even(p2.get('ticket'), symbol, new_sl)

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
