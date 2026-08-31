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
        if self.current_day != today:
            self.current_day = today
            self.day_starting_equity = self.connector.get_account_info().get("equity", 10000.0)
            self.daily_target_reached = False
            self.daily_max_loss_reached = False
            self.pause_until_time = 0
            self.add_log(f"📅 New trading day initialized. Base Equity: ${self.day_starting_equity:.2f}", "INFO")

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
        ea_positions = [p for p in positions if p.get('magic') in [self.magic_number, self.magic_pos1, self.magic_pos2]]
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
            # Strategy: SMC Liquidity Sweep (Winrate 75-80%)
            if strat_mode in ["ALL", "SMC_SWEEP"]:
                buy_sig, sell_sig, reason = self._check_smc_liquidity_sweep(df)
                if buy_sig: buy_signal, signal_reason = True, reason
                elif sell_sig: sell_signal, signal_reason = True, reason

            # Strategy: EMA Ribbon + RSI Momentum Reset (Winrate 70%)
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
            strat_key = "SECRET_EMA_PULLBACK"
            if "News" in signal_reason or "NEWS" in signal_reason or "Momentum" in signal_reason: strat_key = "NEWS_MOMENTUM_EXPANSION"
            elif "3 Candles" in signal_reason or "EMA50_3CANDLES" in signal_reason: strat_key = "EMA50_3CANDLES_H1"
            elif "Asian" in signal_reason: strat_key = "ASIAN_RANGE_SNIPER"
            elif "SMC" in signal_reason: strat_key = "SMC_SWEEP"
            elif "Ribbon" in signal_reason: strat_key = "EMA_RIBBON"
            elif "BB" in signal_reason or "Squeeze" in signal_reason: strat_key = "BB_SQUEEZE"
            elif "Pullback" in signal_reason: strat_key = "SECRET_EMA_PULLBACK"
            elif strat_mode == "ALL": strat_key = "ALL_CONFLUENCE"

            # 1. Evaluate Market Regime & Liquidity Filter Score (0 - 100)
            score_res = self.scorer.evaluate_market_confluence(df, current_spread, strat_key)
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

    def execute_buy(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None):
        ask = self.connector.get_market_info(symbol).get("ask", 0.0)
        if ask <= 0: return

        opt = opt_params or {}
        sl_mult = opt.get("atr_sl_multiplier", 1.0)
        dynamic_rr = opt.get("tp_ratio", 1.60 if not is_asian_scalp else 1.25)
        lot_mult = opt.get("lot_multiplier", 1.0)

        if is_asian_scalp:
            lowest_low = df['low'].iloc[-4:-1].min()
            sl_buffer = 0.30 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 1.00: sl = ask - 1.00; sl_dist = 1.00
            if sl_dist > 3.50: sl = ask - 3.50; sl_dist = 3.50
            
            bb_mid = float(df['sma20'].iloc[-2])
            tp1 = max(ask + 1.50, bb_mid) if bb_mid > ask else (ask + sl_dist * dynamic_rr)
        else:
            lowest_low = df['low'].iloc[-8:-1].min()
            sl_buffer = 0.50 * sl_mult
            sl = lowest_low - sl_buffer
            sl_dist = ask - sl
            if sl_dist < 1.50: sl = ask - 1.50; sl_dist = 1.50
            if sl_dist > 10.0: sl = ask - 10.0; sl_dist = 10.0
            tp1 = ask + (sl_dist * dynamic_rr)

        total_lot = self.calculate_lot_size(sl_dist, lot_mult)
        lot1 = max(0.01, round(total_lot * 0.50, 2))
        lot2 = max(0.01, round(total_lot * 0.50, 2))

        res1 = self.connector.open_order(symbol, "BUY", lot1, sl, tp1, self.magic_pos1, f"Gold_P1_{reason[:8]}")
        res2 = self.connector.open_order(symbol, "BUY", lot2, sl, 0.0, self.magic_pos2, f"Gold_P2_{reason[:8]}")

        t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
        t2 = res2.get("ticket", 0) if isinstance(res2, dict) else 0
        strat_id = "SECRET_EMA_PULLBACK"
        for k in ["NEWS_MOMENTUM_EXPANSION", "EMA50_3CANDLES_H1", "ASIAN_RANGE_SNIPER", "SMC_SWEEP", "EMA_RIBBON", "BB_SQUEEZE", "SECRET_EMA_PULLBACK", "ALL_CONFLUENCE"]:
            if k in reason: strat_id = k; break
        self.benchmark_tracker.register_trade(t1, t2, symbol, "BUY", ask, sl, total_lot, strat_id)

        self.add_log(f"🟢 [AI BUY OPENED] {reason} | Dynamic RR: {dynamic_rr}R | Total Lot: {total_lot} (x{lot_mult:.2f}) | Price: {ask:.2f} | SL: {sl:.2f} | TP1: {tp1:.2f}", "SUCCESS")
        if self.notifier:
            self.notifier.notify_order_opened("BUY", symbol, total_lot, ask, sl, tp1, reason)

    def execute_sell(self, df: pd.DataFrame, symbol: str, reason: str, is_asian_scalp: bool = False, opt_params: Optional[dict] = None):
        bid = self.connector.get_market_info(symbol).get("bid", 0.0)
        if bid <= 0: return

        opt = opt_params or {}
        sl_mult = opt.get("atr_sl_multiplier", 1.0)
        dynamic_rr = opt.get("tp_ratio", 1.60 if not is_asian_scalp else 1.25)
        lot_mult = opt.get("lot_multiplier", 1.0)

        if is_asian_scalp:
            highest_high = df['high'].iloc[-4:-1].max()
            sl_buffer = 0.30 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 1.00: sl = bid + 1.00; sl_dist = 1.00
            if sl_dist > 3.50: sl = bid + 3.50; sl_dist = 3.50
            
            bb_mid = float(df['sma20'].iloc[-2])
            tp1 = min(bid - 1.50, bb_mid) if bb_mid < bid else (bid - sl_dist * dynamic_rr)
        else:
            highest_high = df['high'].iloc[-8:-1].max()
            sl_buffer = 0.50 * sl_mult
            sl = highest_high + sl_buffer
            sl_dist = sl - bid
            if sl_dist < 1.50: sl = bid + 1.50; sl_dist = 1.50
            if sl_dist > 10.0: sl = bid + 10.0; sl_dist = 10.0
            tp1 = bid - (sl_dist * dynamic_rr)

        total_lot = self.calculate_lot_size(sl_dist, lot_mult)
        lot1 = max(0.01, round(total_lot * 0.50, 2))
        lot2 = max(0.01, round(total_lot * 0.50, 2))

        res1 = self.connector.open_order(symbol, "SELL", lot1, sl, tp1, self.magic_pos1, f"Gold_P1_{reason[:8]}")
        res2 = self.connector.open_order(symbol, "SELL", lot2, sl, 0.0, self.magic_pos2, f"Gold_P2_{reason[:8]}")

        t1 = res1.get("ticket", 0) if isinstance(res1, dict) else 0
        t2 = res2.get("ticket", 0) if isinstance(res2, dict) else 0
        strat_id = "SECRET_EMA_PULLBACK"
        for k in ["NEWS_MOMENTUM_EXPANSION", "EMA50_3CANDLES_H1", "ASIAN_RANGE_SNIPER", "SMC_SWEEP", "EMA_RIBBON", "BB_SQUEEZE", "SECRET_EMA_PULLBACK", "ALL_CONFLUENCE"]:
            if k in reason: strat_id = k; break
        self.benchmark_tracker.register_trade(t1, t2, symbol, "SELL", bid, sl, total_lot, strat_id)

        self.add_log(f"🔴 [AI SELL OPENED] {reason} | Dynamic RR: {dynamic_rr}R | Total Lot: {total_lot} (x{lot_mult:.2f}) | Price: {bid:.2f} | SL: {sl:.2f} | TP1: {tp1:.2f}", "SUCCESS")
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

# Alias for backwards compatibility
BotEngine = GoldScalpingBot
