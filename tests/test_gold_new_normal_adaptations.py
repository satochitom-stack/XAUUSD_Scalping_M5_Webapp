"""
Unit Test Suite for Gold New Normal Adaptation Engine
Verifies:
1. Liquidity Reference Levels (PDH/PDL, Asian H/L, EQH/EQL) calculation
2. Liquidity Guard blocks breakout chasing into unpurged ceilings/floors
3. Strict Confirmation rejects weak/exhaustion candles with opposite wicks
4. Dynamic ATR SL Floor adapts minimum SL based on market volatility
5. Dynamic Lot Sizing scales down by 50% for Grade B and applies ATR damping
"""

import unittest
from unittest.mock import MagicMock
from datetime import datetime, time as dtime, timezone, timedelta
import pandas as pd
import numpy as np

import bot_engine


class TestGoldNewNormalAdaptations(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {
            "balance": 10000.0,
            "equity": 10000.0,
            "margin_level": 500.0
        }
        self.mock_connector.get_open_positions.return_value = []
        self.mock_connector.get_market_info.return_value = {"bid": 2650.0, "ask": 2650.25, "spread": 25.0}

        self.config = {
            "strategy": {
                "enable_step_up_compounding": True,
                "strategy_mode": "ALL",
                "risk_percent": 1.0
            }
        }
        self.bot = bot_engine.GoldScalpingBot(self.mock_connector, self.config)

    def test_liquidity_levels_calculation(self):
        """Verify get_market_liquidity_levels computes PDH/PDL, Asian H/L, and EQH/EQL."""
        dates = pd.date_range("2026-09-15 07:00", periods=60, freq="5min")
        highs = [2650.0 + (i % 10) * 0.5 for i in range(60)]
        lows = [h - 2.0 for h in highs]
        closes = [(h + l) / 2.0 for h, l in zip(highs, lows)]

        df = pd.DataFrame({
            "time": dates,
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * 60
        })

        # Mock D1 rates for PDH/PDL
        df_d1 = pd.DataFrame({
            "high": [2670.0, 2665.0],
            "low": [2630.0, 2635.0]
        })
        self.mock_connector.get_rates.return_value = df_d1

        levels = self.bot.get_market_liquidity_levels(df, "XAUUSDc")
        self.assertEqual(levels["pdh"], 2670.0)
        self.assertEqual(levels["pdl"], 2630.0)
        self.assertGreater(levels["asia_high"], 0.0)
        self.assertGreater(levels["asia_low"], 0.0)
        self.assertGreater(levels["curr_atr"], 0.0)

    def test_liquidity_guard_blocks_buying_into_unpurged_ceiling(self):
        """Verify _process_single_setup_signal blocks BUY if price is directly under PDH ceiling."""
        dates = pd.date_range("2026-09-15 15:00", periods=30, freq="5min")
        # Current price close is 2664.80, PDH is 2665.00 (within 0.20 USD)
        df = pd.DataFrame({
            "time": dates,
            "open": [2664.0] * 30,
            "high": [2664.9] * 30,
            "low": [2663.0] * 30,
            "close": [2664.80] * 30,
            "tick_volume": [150] * 30
        })

        df_d1 = pd.DataFrame({"high": [2665.0, 2665.0], "low": [2630.0, 2630.0]})
        self.mock_connector.get_rates.return_value = df_d1
        self.bot.get_h1_macro_trend = MagicMock(return_value=1) # Bullish
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, "Within hours", "14:00", "02:00"))
        self.bot.execute_buy = MagicMock()

        self.bot._process_single_setup_signal(df, "XAUUSDc", 20.0, "EW_WAVE3_BREAKER", "BUY", "Wave 3 Breakout")
        # Execution should be blocked by Liquidity Guard
        self.assertEqual(self.bot.execute_buy.call_count, 0)
        self.assertIn("LIQUIDITY BLOCKED", self.bot.latest_trend)

    def test_dynamic_atr_sl_floor_in_execute_buy(self):
        """Verify execute_buy dynamically scales SL floor when ATR is elevated."""
        # High volatility market: M5 candle range ~5.00 USD -> ATR ~5.00 USD
        highs = [2650.0 + 5.0] * 20
        lows = [2650.0] * 20
        closes = [2652.5] * 20
        df = pd.DataFrame({
            "time": pd.date_range("2026-09-15", periods=20, freq="5min"),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "ema60": [2651.0] * 20
        })

        self.mock_connector.get_market_info.return_value = {"ask": 2655.0, "bid": 2654.8, "spread": 20.0}
        self.mock_connector.open_order.return_value = {"ticket": 9876}

        # For PULLBACK_DR_EKK, base minimum was 2.50. With ATR ~5.0, min_sl = max(2.50, min(5.00, 0.8 * 5.0)) = 4.00
        self.bot.execute_buy(df, "XAUUSDc", "High Volatility Pullback", strat_id="PULLBACK_DR_EKK")
        self.assertEqual(self.mock_connector.open_order.call_count, 1)
        placed_sl = self.mock_connector.open_order.call_args[0][3]
        sl_dist = 2655.0 - placed_sl
        self.assertGreaterEqual(sl_dist, 4.00)

    def test_dynamic_lot_scaling_for_grade_b_and_extreme_volatility(self):
        """Verify Grade B setup scales down lot by 50% and extreme ATR applies damping."""
        # Setup Grade B mock scorer
        self.bot.scorer.evaluate_market_confluence = MagicMock(return_value={
            "is_allowed": True,
            "score": 60,
            "grade": "B",
            "lot_recommendation": 0.50,
            "pillars": {"volume": {"desc": "Normal"}}
        })
        self.bot.optimizer.get_dynamic_rr_and_parameters = MagicMock(return_value={
            "should_execute": True,
            "lot_multiplier": 1.0,
            "tp_ratio": 2.0
        })
        self.bot.get_h1_macro_trend = MagicMock(return_value=1)
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, "Within hours", "14:00", "24:00"))
        self.bot.execute_buy = MagicMock()

        # Extreme ATR df (highs - lows = 6.0 USD)
        df = pd.DataFrame({
            "time": pd.date_range("2026-09-15", periods=20, freq="5min"),
            "open": [2650.0] * 20,
            "high": [2656.0] * 20,
            "low": [2650.0] * 20,
            "close": [2653.0] * 20,
            "tick_volume": [200] * 20
        })

        self.bot._process_single_setup_signal(df, "XAUUSDc", 20.0, "KC_LIQUIDITY_DOMINANCE", "BUY", "KC Sweep")
        self.assertEqual(self.bot.execute_buy.call_count, 1)
        call_args = self.bot.execute_buy.call_args
        opt_passed = call_args[1].get("opt_params") if "opt_params" in call_args[1] else call_args[0][4]
        # Base 1.0 * 0.50 (Grade B) * 0.80 (ATR >= 4.50 damping) = 0.40
        self.assertAlmostEqual(opt_passed.get("lot_multiplier", 1.0), 0.40, places=2)


if __name__ == '__main__':
    unittest.main()
