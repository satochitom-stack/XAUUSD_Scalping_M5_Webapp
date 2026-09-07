"""
Historical Multi-Strategy Backtesting Engine for XAUUSD (Gold)
Simulates exact bot logic from bot_engine.py with realistic 2-Position Multi-TP, Pina Colada, and Session Gates.
"""

import math
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BacktestEngine")


class HistoricalBacktester:
    def __init__(
        self,
        symbol: str = "XAUUSDc",
        initial_balance: float = 3000.0,
        risk_percent: float = 1.0,
        spread_usd: float = 0.25, # 25 points
        max_concurrent_setups: int = 3
    ):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.risk_percent = risk_percent
        self.spread_usd = spread_usd
        self.max_concurrent_setups = max_concurrent_setups

        self.active_setups = [
            "FLASH_MICRO_SCALPER",
            "CAPTAIN_SMC_DUAL",
            "ASIAN_RANGE_SNIPER",
            "EMA50_3CANDLES_H1",
            "NEWS_MOMENTUM_EXPANSION"
        ]

    def fetch_historical_data(self, bars_count: int = 20000) -> pd.DataFrame:
        """Fetches M5 data from MT5."""
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 python package not available.")

        if not mt5.terminal_info():
            if not mt5.initialize():
                raise RuntimeError("Failed to initialize MetaTrader 5.")

        rates_m5 = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, bars_count)
        if rates_m5 is None or len(rates_m5) == 0:
            alt_sym = "XAUUSD" if "c" in self.symbol else "XAUUSDc"
            self.symbol = alt_sym
            rates_m5 = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, bars_count)
            if rates_m5 is None or len(rates_m5) == 0:
                raise RuntimeError(f"Could not retrieve rates for {self.symbol}")

        df_m5 = pd.DataFrame(rates_m5)
        df_m5['datetime'] = pd.to_datetime(df_m5['time'], unit='s')
        return df_m5

    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates indicators identically to bot_engine.py."""
        df = df.copy()

        # EMAs
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['ema150'] = df['close'].ewm(span=150, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Bollinger Bands
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['std20'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['sma20'] + (2.0 * df['std20'])
        df['bb_lower'] = df['sma20'] - (2.0 * df['std20'])
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / (df['sma20'] + 1e-9)

        # ATR 14
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr14'] = tr.rolling(window=14).mean()

        # Pina Colada Envelopes
        df['pina_upper'] = df['ema20'] + (2.2 * df['atr14'])
        df['pina_lower'] = df['ema20'] - (2.2 * df['atr14'])

        # RSIs (4, 7, 14)
        delta = df['close'].diff()
        gain4 = (delta.where(delta > 0, 0)).rolling(window=4).mean()
        loss4 = (-delta.where(delta < 0, 0)).rolling(window=4).mean()
        df['rsi4'] = 100 - (100 / (1 + (gain4 / (loss4 + 1e-9))))

        gain7 = (delta.where(delta > 0, 0)).rolling(window=7).mean()
        loss7 = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
        df['rsi7'] = 100 - (100 / (1 + (gain7 / (loss7 + 1e-9))))

        gain14 = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss14 = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi14'] = 100 - (100 / (1 + (gain14 / (loss14 + 1e-9))))

        # Tick volume average
        df['vol_sma20'] = df['tick_volume'].rolling(window=20).mean()

        # Sessions in Thai Time (UTC+7)
        df['thai_hour'] = (df['datetime'].dt.hour + 5) % 24
        df['is_asia'] = df['thai_hour'].between(7, 13)
        df['is_london'] = df['thai_hour'].between(14, 18)
        df['is_ny'] = (df['thai_hour'] >= 19) | (df['thai_hour'] < 4)
        df['is_rollover'] = df['thai_hour'].between(4, 6)

        return df

    def run_backtest(self, bars_count: int = 20000) -> dict:
        """Executes full multi-setup backtest simulation."""
        df_m5 = self.fetch_historical_data(bars_count)
        df_m5 = self.prepare_indicators(df_m5)

        balance = self.initial_balance
        peak_balance = balance
        max_drawdown_usd = 0.0
        max_drawdown_pct = 0.0

        open_trades: List[dict] = []
        closed_trades: List[dict] = []
        equity_curve: List[dict] = []

        cooldowns = {s: 0 for s in self.active_setups}
        start_idx = 60
        total_bars = len(df_m5)

        for i in range(start_idx, total_bars):
            curr_bar = df_m5.iloc[i]
            curr_time = curr_bar['datetime']

            # -------------------------------------------------------------
            # 1. Update Existing Open Trades
            # -------------------------------------------------------------
            still_open = []
            for t in open_trades:
                pos_type = t['type']
                entry_p = t['entry_price']
                sl = t['sl']
                bar_high = curr_bar['high']
                bar_low = curr_bar['low']

                trade_closed = False

                if pos_type == "BUY":
                    # Check Pos 1 TP1 (1.0R)
                    if not t['pos1_closed']:
                        if bar_high >= t['tp1']:
                            t['pos1_closed'] = True
                            t['pos1_pnl'] = round((t['tp1'] - entry_p) * t['lot1'] * 100.0, 2)
                            balance += t['pos1_pnl']
                            t['sl'] = entry_p + 0.30 # Move Pos 2 SL to BE
                            sl = t['sl']
                            t['is_be'] = True

                    # Check SL
                    if bar_low <= sl:
                        trade_closed = True
                        t['exit_time'] = str(curr_time)
                        t['exit_reason'] = "SL" if not t['is_be'] else "BREAK_EVEN"
                        if not t['pos1_closed']:
                            t['pos1_closed'] = True
                            t['pos1_pnl'] = round((sl - entry_p) * t['lot1'] * 100.0, 2)
                            balance += t['pos1_pnl']
                        t['pos2_closed'] = True
                        t['pos2_pnl'] = round((sl - entry_p) * t['lot2'] * 100.0, 2)
                        balance += t['pos2_pnl']

                    # Check Pos 2 TP2
                    elif bar_high >= t['tp2']:
                        trade_closed = True
                        t['exit_time'] = str(curr_time)
                        t['exit_reason'] = "TP2"
                        if not t['pos1_closed']:
                            t['pos1_closed'] = True
                            t['pos1_pnl'] = round((t['tp1'] - entry_p) * t['lot1'] * 100.0, 2)
                            balance += t['pos1_pnl']
                        t['pos2_closed'] = True
                        t['pos2_pnl'] = round((t['tp2'] - entry_p) * t['lot2'] * 100.0, 2)
                        balance += t['pos2_pnl']

                elif pos_type == "SELL":
                    # Check Pos 1 TP1 (1.0R)
                    if not t['pos1_closed']:
                        if bar_low <= t['tp1']:
                            t['pos1_closed'] = True
                            t['pos1_pnl'] = round((entry_p - t['tp1']) * t['lot1'] * 100.0, 2)
                            balance += t['pos1_pnl']
                            t['sl'] = entry_p - 0.30 # Move Pos 2 SL to BE
                            sl = t['sl']
                            t['is_be'] = True

                    # Check SL
                    if bar_high >= sl:
                        trade_closed = True
                        t['exit_time'] = str(curr_time)
                        t['exit_reason'] = "SL" if not t['is_be'] else "BREAK_EVEN"
                        if not t['pos1_closed']:
                            t['pos1_closed'] = True
                            t['pos1_pnl'] = round((entry_p - sl) * t['lot1'] * 100.0, 2)
                            balance += t['pos1_pnl']
                        t['pos2_closed'] = True
                        t['pos2_pnl'] = round((entry_p - sl) * t['lot2'] * 100.0, 2)
                        balance += t['pos2_pnl']

                    # Check Pos 2 TP2
                    elif bar_low <= t['tp2']:
                        trade_closed = True
                        t['exit_time'] = str(curr_time)
                        t['exit_reason'] = "TP2"
                        if not t['pos1_closed']:
                            t['pos1_closed'] = True
                            t['pos1_pnl'] = round((entry_p - t['tp1']) * t['lot1'] * 100.0, 2)
                            balance += t['pos1_pnl']
                        t['pos2_closed'] = True
                        t['pos2_pnl'] = round((entry_p - t['tp2']) * t['lot2'] * 100.0, 2)
                        balance += t['pos2_pnl']

                if trade_closed:
                    t['total_pnl'] = round(t['pos1_pnl'] + t['pos2_pnl'], 2)
                    t['status'] = "WIN" if t['total_pnl'] > 0 else ("BE" if t['total_pnl'] == 0 else "LOSS")
                    closed_trades.append(t)
                else:
                    still_open.append(t)

            open_trades = still_open

            # Track Peak & Max Drawdown
            if balance > peak_balance:
                peak_balance = balance
            dd_usd = peak_balance - balance
            dd_pct = (dd_usd / peak_balance) * 100.0 if peak_balance > 0 else 0.0
            if dd_usd > max_drawdown_usd:
                max_drawdown_usd = dd_usd
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

            if i % 12 == 0:
                equity_curve.append({
                    "datetime": str(curr_time),
                    "balance": round(balance, 2),
                    "drawdown_pct": round(dd_pct, 2)
                })

            # -------------------------------------------------------------
            # 2. Check Signals for New Trades
            # -------------------------------------------------------------
            if curr_bar['is_rollover']:
                continue

            if len(open_trades) >= self.max_concurrent_setups:
                continue

            open_setup_ids = {t['setup_id'] for t in open_trades}
            window_m5 = df_m5.iloc[i - 45 : i + 1]
            b1 = window_m5.iloc[-2] # Last closed bar
            b2 = window_m5.iloc[-3]
            b3 = window_m5.iloc[-4]

            # Pina Colada Caution Filter (Avoid Parabolic falling knives/pumps)
            curr_atr = float(b1['atr14']) if not math.isnan(b1['atr14']) else 2.50
            is_dumping = (b1['close'] < b1['open']) and (b2['close'] < b2['open']) and (b3['close'] < b3['open'])
            wide_dump = abs(b1['close'] - b1['open']) > (1.2 * curr_atr) or abs(b2['close'] - b2['open']) > (1.2 * curr_atr)
            caution_bear = is_dumping and wide_dump and (b1['low'] < b1['pina_lower'])

            is_pumping = (b1['close'] > b1['open']) and (b2['close'] > b2['open']) and (b3['close'] > b3['open'])
            wide_pump = abs(b1['close'] - b1['open']) > (1.2 * curr_atr) or abs(b2['close'] - b2['open']) > (1.2 * curr_atr)
            caution_bull = is_pumping and wide_pump and (b1['high'] > b1['pina_upper'])
            caution_active = caution_bear or caution_bull

            # --- SETUP 1: FLASH_MICRO_SCALPER (1 Position, 1% Risk, Pure Trend Pullback) ---
            if "FLASH_MICRO_SCALPER" in self.active_setups and "FLASH_MICRO_SCALPER" not in open_setup_ids:
                if i > cooldowns["FLASH_MICRO_SCALPER"]:
                    candle_range = b1['high'] - b1['low']
                    candle_body = abs(b1['close'] - b1['open'])
                    if candle_range > 0.25 and (candle_body / candle_range) >= 0.35:
                        lower_wick = min(b1['open'], b1['close']) - b1['low']
                        upper_wick = b1['high'] - max(b1['open'], b1['close'])
                        rsi4 = b1['rsi4']
                        is_uptrend = (b1['ema9'] > b1['ema21']) and (b1['ema21'] > b1['ema50'])
                        is_downtrend = (b1['ema9'] < b1['ema21']) and (b1['ema21'] < b1['ema50'])

                        # Buy Pullback
                        if is_uptrend and b1['low'] <= (b1['ema9'] + 0.25) and b1['close'] > b1['ema9'] and b1['close'] > b1['open']:
                            if (lower_wick / candle_range) >= 0.30 and 40 <= rsi4 <= 75:
                                lowest_low = window_m5['low'].iloc[-7:-1].min()
                                ask = curr_bar['open'] + self.spread_usd
                                sl_dist = max(2.80, min(4.50, ask - (lowest_low - 0.40)))
                                sl = ask - sl_dist
                                tp = ask + (sl_dist * 1.50) # 1:1.5 RR Single Clean Trade
                                lot = self._calc_lot(balance, sl_dist)
                                open_trades.append(self._create_dual_trade("FLASH_MICRO_SCALPER", "BUY", ask, sl, tp, tp, sl_dist, lot, curr_time, is_single=True))
                                cooldowns["FLASH_MICRO_SCALPER"] = i + 3

                        # Sell Pullback
                        elif is_downtrend and b1['high'] >= (b1['ema9'] - 0.25) and b1['close'] < b1['ema9'] and b1['close'] < b1['open']:
                            if (upper_wick / candle_range) >= 0.30 and 25 <= rsi4 <= 60:
                                highest_high = window_m5['high'].iloc[-7:-1].max()
                                bid = curr_bar['open']
                                sl_dist = max(2.80, min(4.50, (highest_high + 0.40) - bid))
                                sl = bid + sl_dist
                                tp = bid - (sl_dist * 1.50)
                                lot = self._calc_lot(balance, sl_dist)
                                open_trades.append(self._create_dual_trade("FLASH_MICRO_SCALPER", "SELL", bid, sl, tp, tp, sl_dist, lot, curr_time, is_single=True))
                                cooldowns["FLASH_MICRO_SCALPER"] = i + 3

            # --- SETUP 2: CAPTAIN_SMC_DUAL (London & NY Sessions Only) ---
            if "CAPTAIN_SMC_DUAL" in self.active_setups and "CAPTAIN_SMC_DUAL" not in open_setup_ids:
                if not curr_bar['is_asia'] and i > cooldowns["CAPTAIN_SMC_DUAL"]:
                    lookback = window_m5.iloc[-32:-2]
                    swing_high = lookback['high'].rolling(window=10).max().iloc[-1]
                    swing_low = lookback['low'].rolling(window=10).min().iloc[-1]
                    candle_range = b1['high'] - b1['low']

                    if candle_range > 0.30:
                        lower_wick = min(b1['open'], b1['close']) - b1['low']
                        upper_wick = b1['high'] - max(b1['open'], b1['close'])
                        is_uptrend = b1['ema50'] > b1['ema150']
                        is_downtrend = b1['ema50'] < b1['ema150']
                        rsi = b1['rsi14']
                        is_vol_confirmed = b1['tick_volume'] >= (b1['vol_sma20'] * 0.95)

                        # MODEL 1: Fast Wick Rejection Buy (Support Zone)
                        fast_buy = (b1['low'] <= (swing_low + 0.60) and (lower_wick / candle_range) >= 0.35 and 
                                    b1['close'] > b1['open'] and is_vol_confirmed and (not is_downtrend or rsi < 35))
                        # MODEL 2: Confirmed CHoCH Breakout
                        recent_high = window_m5['high'].iloc[-17:-2].max()
                        confirmed_buy = (b1['close'] > recent_high and b1['close'] > b1['open'] and 
                                         (is_uptrend or rsi > 52) and is_vol_confirmed)

                        if fast_buy or confirmed_buy:
                            lowest_low = window_m5['low'].iloc[-15:-1].min()
                            ask = curr_bar['open'] + self.spread_usd
                            sl_dist = max(3.80, min(6.50, ask - (lowest_low - 0.60)))
                            sl = ask - sl_dist
                            tp1 = ask + (sl_dist * 1.0)
                            tp2 = ask + (sl_dist * 1.8)
                            lot = self._calc_lot(balance, sl_dist)
                            open_trades.append(self._create_dual_trade("CAPTAIN_SMC_DUAL", "BUY", ask, sl, tp1, tp2, sl_dist, lot, curr_time))
                            cooldowns["CAPTAIN_SMC_DUAL"] = i + 5

                        # MODEL 1: Fast Wick Rejection Sell (Resistance Zone)
                        fast_sell = (b1['high'] >= (swing_high - 0.60) and (upper_wick / candle_range) >= 0.35 and 
                                     b1['close'] < b1['open'] and is_vol_confirmed and (not is_uptrend or rsi > 65))
                        # MODEL 2: Confirmed CHoCH Breakdown
                        recent_low = window_m5['low'].iloc[-17:-2].min()
                        confirmed_sell = (b1['close'] < recent_low and b1['close'] < b1['open'] and 
                                          (is_downtrend or rsi < 48) and is_vol_confirmed)

                        if fast_sell or confirmed_sell:
                            highest_high = window_m5['high'].iloc[-15:-1].max()
                            bid = curr_bar['open']
                            sl_dist = max(3.80, min(6.50, (highest_high + 0.60) - bid))
                            sl = bid + sl_dist
                            tp1 = bid - (sl_dist * 1.0)
                            tp2 = bid - (sl_dist * 1.8)
                            lot = self._calc_lot(balance, sl_dist)
                            open_trades.append(self._create_dual_trade("CAPTAIN_SMC_DUAL", "SELL", bid, sl, tp1, tp2, sl_dist, lot, curr_time))
                            cooldowns["CAPTAIN_SMC_DUAL"] = i + 5

            # --- SETUP 3: ASIAN_RANGE_SNIPER (Asian Session Only with Caution Filter) ---
            if "ASIAN_RANGE_SNIPER" in self.active_setups and "ASIAN_RANGE_SNIPER" not in open_setup_ids:
                if curr_bar['is_asia'] and not caution_active and i > cooldowns["ASIAN_RANGE_SNIPER"]:
                    candle_range = b1['high'] - b1['low']
                    if candle_range > 0.20:
                        lower_wick = min(b1['open'], b1['close']) - b1['low']
                        upper_wick = b1['high'] - max(b1['open'], b1['close'])

                        # Buy Rebound: Price touched lower BB/Pina and bounced back inside
                        if (b1['low'] <= b1['bb_lower'] or b1['low'] <= b1['pina_lower']) and b1['close'] > b1['open'] and (lower_wick / candle_range) >= 0.35:
                            if b1['rsi7'] <= 35 and b1['rsi7'] > b2['rsi7']:
                                lowest_low = window_m5['low'].iloc[-7:-1].min()
                                ask = curr_bar['open'] + self.spread_usd
                                sl_dist = max(2.80, min(5.00, ask - (lowest_low - 0.40)))
                                sl = ask - sl_dist
                                tp1 = ask + (sl_dist * 1.0)
                                tp2 = ask + (sl_dist * 1.8)
                                lot = self._calc_lot(balance, sl_dist)
                                open_trades.append(self._create_dual_trade("ASIAN_RANGE_SNIPER", "BUY", ask, sl, tp1, tp2, sl_dist, lot, curr_time))
                                cooldowns["ASIAN_RANGE_SNIPER"] = i + 4

                        # Sell Rebound: Price touched upper BB/Pina and bounced back inside
                        elif (b1['high'] >= b1['bb_upper'] or b1['high'] >= b1['pina_upper']) and b1['close'] < b1['open'] and (upper_wick / candle_range) >= 0.35:
                            if b1['rsi7'] >= 65 and b1['rsi7'] < b2['rsi7']:
                                highest_high = window_m5['high'].iloc[-7:-1].max()
                                bid = curr_bar['open']
                                sl_dist = max(2.80, min(5.00, (highest_high + 0.40) - bid))
                                sl = bid + sl_dist
                                tp1 = bid - (sl_dist * 1.0)
                                tp2 = bid - (sl_dist * 1.8)
                                lot = self._calc_lot(balance, sl_dist)
                                open_trades.append(self._create_dual_trade("ASIAN_RANGE_SNIPER", "SELL", bid, sl, tp1, tp2, sl_dist, lot, curr_time))
                                cooldowns["ASIAN_RANGE_SNIPER"] = i + 4

            # --- SETUP 4: EMA50_3CANDLES_H1 (With Cooldown Lock) ---
            if "EMA50_3CANDLES_H1" in self.active_setups and "EMA50_3CANDLES_H1" not in open_setup_ids:
                if not curr_bar['is_asia'] and i > cooldowns["EMA50_3CANDLES_H1"]:
                    b6 = window_m5.iloc[-7]
                    slope = (b1['ema50'] - b6['ema50']) / 0.01

                    # Bullish 3 Candles
                    if (b1['close'] > b1['open'] and b1['close'] > b1['ema50'] and
                        b2['close'] > b2['open'] and b2['close'] > b2['ema50'] and
                        b3['close'] > b3['open'] and b3['close'] > b3['ema50'] and slope >= 30.0):
                        lowest_low = window_m5['low'].iloc[-21:-1].min()
                        ask = curr_bar['open'] + self.spread_usd
                        sl_dist = max(4.50, min(8.00, ask - (lowest_low - 0.70)))
                        sl = ask - sl_dist
                        tp1 = ask + (sl_dist * 1.0)
                        tp2 = ask + (sl_dist * 2.0)
                        lot = self._calc_lot(balance, sl_dist)
                        open_trades.append(self._create_dual_trade("EMA50_3CANDLES_H1", "BUY", ask, sl, tp1, tp2, sl_dist, lot, curr_time))
                        cooldowns["EMA50_3CANDLES_H1"] = i + 12

                    # Bearish 3 Candles
                    elif (b1['close'] < b1['open'] and b1['close'] < b1['ema50'] and
                          b2['close'] < b2['open'] and b2['close'] < b2['ema50'] and
                          b3['close'] < b3['open'] and b3['close'] < b3['ema50'] and slope <= -30.0):
                        highest_high = window_m5['high'].iloc[-21:-1].max()
                        bid = curr_bar['open']
                        sl_dist = max(4.50, min(8.00, (highest_high + 0.70) - bid))
                        sl = bid + sl_dist
                        tp1 = bid - (sl_dist * 1.0)
                        tp2 = bid - (sl_dist * 2.0)
                        lot = self._calc_lot(balance, sl_dist)
                        open_trades.append(self._create_dual_trade("EMA50_3CANDLES_H1", "SELL", bid, sl, tp1, tp2, sl_dist, lot, curr_time))
                        cooldowns["EMA50_3CANDLES_H1"] = i + 12

            # --- SETUP 5: NEWS_MOMENTUM_EXPANSION (Breakout Engine) ---
            if "NEWS_MOMENTUM_EXPANSION" in self.active_setups and "NEWS_MOMENTUM_EXPANSION" not in open_setup_ids:
                if i > cooldowns["NEWS_MOMENTUM_EXPANSION"]:
                    pre_swing_high = window_m5['high'].iloc[-16:-2].max()
                    pre_swing_low = window_m5['low'].iloc[-16:-2].min()
                    candle_body = abs(b1['close'] - b1['open'])
                    candle_range = b1['high'] - b1['low'] + 1e-9
                    body_pct = candle_body / candle_range

                    is_solid_expansion = (body_pct >= 0.60) and (candle_range >= 1.20)

                    # Breakout High
                    if is_solid_expansion and b1['close'] > pre_swing_high and b1['close'] > b1['open'] and b1['rsi14'] >= 55:
                        lowest_low = window_m5['low'].iloc[-11:-1].min()
                        ask = curr_bar['open'] + self.spread_usd
                        sl_dist = max(3.50, min(7.00, ask - (lowest_low - 0.50)))
                        sl = ask - sl_dist
                        tp1 = ask + (sl_dist * 1.0)
                        tp2 = ask + (sl_dist * 1.8)
                        lot = self._calc_lot(balance, sl_dist)
                        open_trades.append(self._create_dual_trade("NEWS_MOMENTUM_EXPANSION", "BUY", ask, sl, tp1, tp2, sl_dist, lot, curr_time))
                        cooldowns["NEWS_MOMENTUM_EXPANSION"] = i + 8

                    # Breakdown Low
                    elif is_solid_expansion and b1['close'] < pre_swing_low and b1['close'] < b1['open'] and b1['rsi14'] <= 45:
                        highest_high = window_m5['high'].iloc[-11:-1].max()
                        bid = curr_bar['open']
                        sl_dist = max(3.50, min(7.00, (highest_high + 0.50) - bid))
                        sl = bid + sl_dist
                        tp1 = bid - (sl_dist * 1.0)
                        tp2 = bid - (sl_dist * 1.8)
                        lot = self._calc_lot(balance, sl_dist)
                        open_trades.append(self._create_dual_trade("NEWS_MOMENTUM_EXPANSION", "SELL", bid, sl, tp1, tp2, sl_dist, lot, curr_time))
                        cooldowns["NEWS_MOMENTUM_EXPANSION"] = i + 8

        return self._generate_report(closed_trades, equity_curve, balance, peak_balance, max_drawdown_usd, max_drawdown_pct, df_m5)

    def _calc_lot(self, balance: float, sl_dist: float) -> float:
        risk_usd = balance * (self.risk_percent / 100.0)
        lot = risk_usd / (sl_dist * 100.0 + 1e-9)
        return max(0.01, min(10.0, round(lot, 2)))

    def _create_dual_trade(self, setup_id: str, pos_type: str, entry_p: float, sl: float, tp1: float, tp2: float, sl_dist: float, total_lot: float, entry_time, is_single: bool = False) -> dict:
        if is_single or total_lot <= 0.01:
            lot1 = total_lot
            lot2 = 0.0
        else:
            lot1 = max(0.01, round(total_lot * 0.50, 2))
            lot2 = max(0.01, round(total_lot - lot1, 2))

        return {
            "setup_id": setup_id,
            "type": pos_type,
            "entry_price": round(entry_p, 3),
            "sl": round(sl, 3),
            "tp1": round(tp1, 3),
            "tp2": round(tp2, 3),
            "sl_dist": round(sl_dist, 3),
            "lot1": lot1,
            "lot2": lot2,
            "total_lot": total_lot,
            "pos1_closed": False,
            "pos2_closed": False,
            "pos1_pnl": 0.0,
            "pos2_pnl": 0.0,
            "entry_time": str(entry_time),
            "is_be": False
        }

    def _generate_report(self, trades: List[dict], equity_curve: List[dict], final_balance: float, peak_balance: float, max_dd_usd: float, max_dd_pct: float, df_m5: pd.DataFrame) -> dict:
        total_trades = len(trades)
        wins = [t for t in trades if t['total_pnl'] > 0]
        losses = [t for t in trades if t['total_pnl'] < 0]
        be_trades = [t for t in trades if t['total_pnl'] == 0]

        win_count = len(wins)
        loss_count = len(losses)
        be_count = len(be_trades)

        winrate = round((win_count / total_trades) * 100.0, 1) if total_trades > 0 else 0.0

        gross_profit = round(sum(t['total_pnl'] for t in wins), 2)
        gross_loss = round(abs(sum(t['total_pnl'] for t in losses)), 2)
        net_profit = round(final_balance - self.initial_balance, 2)
        net_profit_pct = round((net_profit / self.initial_balance) * 100.0, 2)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

        strategy_stats = {}
        for s_id in self.active_setups:
            s_trades = [t for t in trades if t['setup_id'] == s_id]
            s_total = len(s_trades)
            s_wins = [t for t in s_trades if t['total_pnl'] > 0]
            s_losses = [t for t in s_trades if t['total_pnl'] < 0]
            s_gp = sum(t['total_pnl'] for t in s_wins)
            s_gl = abs(sum(t['total_pnl'] for t in s_losses))
            s_net = round(sum(t['total_pnl'] for t in s_trades), 2)
            s_wr = round((len(s_wins) / s_total) * 100.0, 1) if s_total > 0 else 0.0
            s_pf = round(s_gp / s_gl, 2) if s_gl > 0 else s_gp

            strategy_stats[s_id] = {
                "total_trades": s_total,
                "wins": len(s_wins),
                "losses": len(s_losses),
                "winrate_pct": s_wr,
                "net_profit_usd": s_net,
                "gross_profit_usd": round(s_gp, 2),
                "gross_loss_usd": round(s_gl, 2),
                "profit_factor": s_pf
            }

        report = {
            "symbol": self.symbol,
            "period_start": str(df_m5['datetime'].iloc[0]),
            "period_end": str(df_m5['datetime'].iloc[-1]),
            "total_bars_tested": len(df_m5),
            "initial_balance": self.initial_balance,
            "final_balance": round(final_balance, 2),
            "net_profit_usd": net_profit,
            "net_profit_pct": net_profit_pct,
            "profit_factor": profit_factor,
            "total_trades": total_trades,
            "win_trades": win_count,
            "loss_trades": loss_count,
            "break_even_trades": be_count,
            "winrate_pct": winrate,
            "max_drawdown_usd": round(max_dd_usd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "strategy_breakdown": strategy_stats,
            "equity_curve": equity_curve[-50:],
            "recent_trades": trades[-20:]
        }

        return report


if __name__ == "__main__":
    tester = HistoricalBacktester(initial_balance=3000.0, risk_percent=1.0)
    # Test on recent 30-day window (~6000 bars) and full window (20000 bars)
    for bars in [6000, 20000]:
        res = tester.run_backtest(bars_count=bars)
        period_label = "RECENT 30 DAYS (AUG - SEP 2026)" if bars == 6000 else "FULL 3.5 MONTHS (MAY - SEP 2026)"
        print("\n" + "=" * 68)
        print(f"[REPORT] XAUUSD BACKTEST: {period_label}")
        print("=" * 68)
        print(f"Symbol: {res['symbol']} | Bars: {res['total_bars_tested']} M5 | {res['period_start'][:10]} to {res['period_end'][:10]}")
        print(f"Initial Balance: ${res['initial_balance']:.2f} -> Final Balance: ${res['final_balance']:.2f}")
        print(f"Net Profit: {'+' if res['net_profit_usd']>=0 else ''}${res['net_profit_usd']:.2f} ({res['net_profit_pct']:+.2f}%) | Profit Factor: {res['profit_factor']:.2f}")
        print(f"Winrate: {res['winrate_pct']}% ({res['win_trades']}W / {res['loss_trades']}L / {res['break_even_trades']}BE) | Max DD: ${res['max_drawdown_usd']:.2f} ({res['max_drawdown_pct']:.2f}%)")
        print("-" * 68)
        print(f"{'Strategy':<26} | {'Trades':<6} | {'Winrate':<7} | {'Net Profit':<11} | {'PF':<5}")
        print("-" * 68)
        for s_id, s in res['strategy_breakdown'].items():
            print(f"{s_id:<26} | {s['total_trades']:<6} | {s['winrate_pct']:>5.1f}% | ${s['net_profit_usd']:>9.2f} | {s['profit_factor']:>4.2f}")
        print("=" * 68)

        if bars == 6000:
            with open("backtest_results_30d.json", "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)
        else:
            with open("backtest_results.json", "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)
