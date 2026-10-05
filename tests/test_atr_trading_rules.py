import os
import sys
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_engine import GoldScalpingBot

class TestATRTradingRules(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {"balance": 1000.0, "equity": 1000.0}
        self.mock_connector.get_market_info.return_value = {"bid": 2650.0, "ask": 2650.30, "spread": 30.0}
        self.mock_connector.open_order.return_value = {"ticket": 888123, "status": True}
        
        self.config = {
            "mt5": {"symbol": "XAUUSDc", "magic_number": 555888},
            "strategy": {
                "risk_percent": 1.0,
                "enable_step_up_compounding": False
            }
        }
        self.bot = GoldScalpingBot(self.mock_connector, self.config)
        self.bot.get_h1_macro_trend = MagicMock(return_value=1) # Bullish

    def test_atr_overextension_guard_blocks_buying_top_tick(self):
        """MTRADERS Rule 2 & 6: Block BUY if price is > 2.0x ATR above EMA50."""
        # ATR ~ 3.0 USD. EMA50 at 2640.0. Current ask = 2650.30 (dist = 10.30 > 2.0 * 3.0 = 6.0)
        closes = [2640.0] * 20
        highs = [c + 3.0 for c in closes]
        lows = [c - 0.5 for c in closes]
        df = pd.DataFrame({
            "high": highs,
            "low": lows,
            "close": closes,
            "ema50": [2640.0] * 20,
            "ema60": [2639.0] * 20
        })
        
        self.bot.execute_buy(df, "XAUUSDc", "Test Overextension", strat_id="PULLBACK_DR_EKK")
        self.assertEqual(self.mock_connector.open_order.call_count, 0)
        self.assertIn("ATR OVEREXTENDED", self.bot.logs[-1]["message"])

    def test_atr_tp_feasibility_clamp(self):
        """MTRADERS Rule 5: Clamp TP distance if it exceeds 2.5x ATR."""
        # Ask = 2650.30. EMA50 at 2648.0 (not overextended). Low = 2645.0. SL dist = 5.30.
        # Target RR = 3.0 -> Raw TP = ask + 15.90. But ATR = 3.0 -> 2.5 * ATR = 7.50 max feasible TP.
        closes = [2648.0] * 20
        highs = [c + 3.0 for c in closes]
        lows = [c - 0.5 for c in closes]
        df = pd.DataFrame({
            "high": highs,
            "low": lows,
            "close": closes,
            "ema50": [2648.0] * 20,
            "ema60": [2647.0] * 20
        })
        
        opt = {"tp_ratio": 3.0}
        self.bot.execute_buy(df, "XAUUSDc", "Test Feasible TP", opt_params=opt, strat_id="PULLBACK_DR_EKK")
        self.assertEqual(self.mock_connector.open_order.call_count, 1)
        placed_tp = self.mock_connector.open_order.call_args[0][4]
        # TP distance should be clamped from 15.90 down to 2.5 * ATR (2.5 * 3.5 = 8.75 USD)
        self.assertAlmostEqual(placed_tp - 2650.30, 8.75, places=1)

    def test_dynamic_atr_buffer_scales_with_volatility(self):
        """MTRADERS Rule 4: Dynamic ATR buffer expands under high volatility."""
        # High volatility ATR ~ 5.0 USD
        closes = [2645.0] * 20
        highs = [c + 5.0 for c in closes]
        lows = [c - 0.5 for c in closes]
        df = pd.DataFrame({
            "high": highs,
            "low": lows,
            "close": closes,
            "ema50": [2645.0] * 20,
            "ema60": [2644.0] * 20
        })
        
        self.bot.execute_buy(df, "XAUUSDc", "Test High Volatility Buffer", strat_id="EW_WAVE3_BREAKER")
        self.assertEqual(self.mock_connector.open_order.call_count, 1)
        placed_sl = self.mock_connector.open_order.call_args[0][3]
        # Under ATR ~ 5.0, buffer is at least 1.00 USD (0.25 * 5.0 = 1.25)
        lowest_low = df['low'].iloc[-8:-1].min()
        self.assertLessEqual(placed_sl, lowest_low - 1.00)

if __name__ == '__main__':
    unittest.main()
