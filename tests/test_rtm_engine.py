import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
from datetime import datetime

from bot_engine import BotEngine, STRATEGY_MAGIC_MAP
from strategy_analytics import StrategyAnalyticsManager

class TestRTMEngine(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.config = {
            "mt5": {"symbol": "XAUUSDc", "magic_number": 555888},
            "strategy": {
                "risk_percent": 1.0,
                "strategy_mode": "ALL",
                "rtm_mode": "ALL"
            }
        }
        self.bot = BotEngine(self.mock_connector, self.config)

    def test_rtm_magics_exist(self):
        """Test all 4 RTM models have registered magic numbers."""
        rtm_keys = [
            "RTM_M4_CONSERVATIVE",
            "RTM_M5_ALL_WEATHER",
            "RTM_M6_ELITE_GROWTH",
            "RTM_M7_MAX_ALPHA"
        ]
        for key in rtm_keys:
            self.assertIn(key, STRATEGY_MAGIC_MAP)
            magic_info = STRATEGY_MAGIC_MAP[key]
            self.assertIn("base", magic_info)
            self.assertIn("pos1", magic_info)
            self.assertTrue(magic_info["base"] >= 777000)

    def test_analytics_registry_contains_rtm_models(self):
        """Test StrategyAnalyticsManager has all 4 RTM models registered."""
        analytics = StrategyAnalyticsManager()
        for key in ["RTM_M4_CONSERVATIVE", "RTM_M5_ALL_WEATHER", "RTM_M6_ELITE_GROWTH", "RTM_M7_MAX_ALPHA"]:
            self.assertIn(key, analytics.STRATEGY_REGISTRY)
            entry = analytics.STRATEGY_REGISTRY[key]
            self.assertEqual(entry["category"], "RTM_PRO")
            self.assertEqual(entry["timeframe"], "M15 (H1 Filter)")

    def test_deal_classification_for_rtm(self):
        """Test that closed deals with RTM magics or comments are accurately classified."""
        analytics = StrategyAnalyticsManager()
        
        deal_m4 = MagicMock()
        deal_m4.magic = 777014
        deal_m4.comment = "Gold_RTM_M4_C"
        self.assertEqual(analytics._classify_deal_strategy(deal_m4), "RTM_M4_CONSERVATIVE")

        deal_m5 = MagicMock()
        deal_m5.magic = 777015
        deal_m5.comment = "Gold_RTM_M5_A"
        self.assertEqual(analytics._classify_deal_strategy(deal_m5), "RTM_M5_ALL_WEATHER")

        deal_m6 = MagicMock()
        deal_m6.magic = 777016
        deal_m6.comment = "Gold_RTM_M6_E"
        self.assertEqual(analytics._classify_deal_strategy(deal_m6), "RTM_M6_ELITE_GROWTH")

        deal_m7 = MagicMock()
        deal_m7.magic = 777017
        deal_m7.comment = "Gold_RTM_M7_A"
        self.assertEqual(analytics._classify_deal_strategy(deal_m7), "RTM_M7_MAX_ALPHA")

    def test_rtm_confluence_execution_router(self):
        """Test _process_rtm_confluence_engine dispatches to eligible models according to Grade."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.get_open_positions.return_value = []
        self.mock_connector.open_order.return_value = {"ticket": 99999}

        mock_signal = {
            "action": "BUY",
            "score": 88.0,
            "grade": "A+",
            "sl": 2694.0,
            "m15_time": datetime.now(),
            "reason": "RTM Quasimodo Bullish QML [A+] (88 pts)"
        }
        self.bot._check_rtm_confluence_m15 = MagicMock(return_value=mock_signal)

        dummy_df = pd.DataFrame({'close': [2700.0]*20, 'low': [2695.0]*20, 'high': [2705.0]*20})
        
        # Test in ALL mode: Grade A+ should trigger all 4 models
        self.bot._process_rtm_confluence_engine(dummy_df, "XAUUSDc", 20.0, rtm_mode="ALL")
        self.assertEqual(self.mock_connector.open_order.call_count, 4)

if __name__ == "__main__":
    unittest.main()
