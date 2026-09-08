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

    def test_concurrent_setups_isolation(self):
        """Test that having an open position in Setup A does not block Setup B, C, or D."""
        asian_pos1_magic = STRATEGY_MAGIC_MAP["ASIAN_RANGE_SNIPER"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 111, "magic": asian_pos1_magic, "symbol": "XAUUSDc", "type": "BUY"}
        ]
        
        # ASIAN_RANGE_SNIPER has open position
        self.assertTrue(self.bot.has_open_positions_for_setup("XAUUSDc", "ASIAN_RANGE_SNIPER"))
        
        # All other setups must NOT be blocked and report False
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "SMC_X_STO_H1"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M4_CONSERVATIVE"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M5_ALL_WEATHER"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M6_ELITE_GROWTH"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M7_MAX_ALPHA"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "NEWS_MOMENTUM_EXPANSION"))

    def test_execute_sell_single_order(self):
        """Test that execute_sell places exactly 1 order per call, avoiding duplicate orders."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.open_order.return_value = {"ticket": 88888}
        dummy_df = pd.DataFrame({'close': [2700.0]*20, 'low': [2695.0]*20, 'high': [2705.0]*20})

        self.bot.execute_sell(dummy_df, "XAUUSDc", "Test Sell Signal", strat_id="SMC_X_STO_H1")
        self.assertEqual(self.mock_connector.open_order.call_count, 1)

    def test_max_concurrent_setups_allows_all_models(self):
        """Test that max_concurrent_setups defaults to len(STRATEGY_MAGIC_MAP) (7) and permits concurrent positions."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0, "margin_level": 500.0}
        
        # Simulate 3 active setups already running
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 1, "magic": STRATEGY_MAGIC_MAP["ASIAN_RANGE_SNIPER"]["pos1"], "symbol": "XAUUSDc", "type": "BUY"},
            {"ticket": 2, "magic": STRATEGY_MAGIC_MAP["SMC_X_STO_H1"]["pos1"], "symbol": "XAUUSDc", "type": "BUY"},
            {"ticket": 3, "magic": STRATEGY_MAGIC_MAP["RTM_M4_CONSERVATIVE"]["pos1"], "symbol": "XAUUSDc", "type": "BUY"}
        ]
        
        # Verify 4th setup is NOT blocked by has_open_positions_for_setup
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M5_ALL_WEATHER"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "NEWS_MOMENTUM_EXPANSION"))

    def test_rtm_trailing_stop_dual_style(self):
        """Test dual-style trailing stop: M4/M5/M6 locks +0.8R at 1.5R; M7 locks +1.0R at 2.0R, +1.8R at 2.6R, +2.4R at 3.0R."""
        # Setup market info: BUY opened at 2700.0, SL at 2690.0 (initial_r = 10.0)
        # Price reaches 2715.5 (+1.55R)
        self.mock_connector.get_market_info.return_value = {"bid": 2715.5, "ask": 2715.7}
        
        # Test M4 (Quick Harvest 2.0R) at 1.55R -> Expect SL locked to 2700 + 0.8 * 10 = 2708.0
        m4_magic = STRATEGY_MAGIC_MAP["RTM_M4_CONSERVATIVE"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 401, "magic": m4_magic, "symbol": "XAUUSDc", "type": "BUY", "price_open": 2700.0, "sl": 2700.3, "tp": 2720.0}
        ]
        self.bot.initial_risk_map[401] = 10.0
        self.bot.manage_open_positions("XAUUSDc")
        
        # modify_position should be called with target_sl = 2708.0
        self.mock_connector.modify_position.assert_called_with(401, 2708.0, 2720.0)

        # Test M7 (Trend Runner 3.5R) at 2.65R (bid = 2726.5) -> Expect SL locked to 2700 + 1.8 * 10 = 2718.0
        self.mock_connector.get_market_info.return_value = {"bid": 2726.5, "ask": 2726.7}
        m7_magic = STRATEGY_MAGIC_MAP["RTM_M7_MAX_ALPHA"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 701, "magic": m7_magic, "symbol": "XAUUSDc", "type": "BUY", "price_open": 2700.0, "sl": 2710.0, "tp": 2735.0}
        ]
        self.bot.initial_risk_map[701] = 10.0
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(701, 2718.0, 2735.0)

    def test_asian_and_news_trailing_lock_1_4r(self):
        """Test Asian Range Sniper and News Momentum lock +0.8R profit when reaching >= 1.4R."""
        # Price at +1.45R (open: 2700.0, initial_r: 10.0, bid: 2714.5)
        self.mock_connector.get_market_info.return_value = {"bid": 2714.5, "ask": 2714.7}
        asian_magic = STRATEGY_MAGIC_MAP["ASIAN_RANGE_SNIPER"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 801, "magic": asian_magic, "symbol": "XAUUSDc", "type": "BUY", "price_open": 2700.0, "sl": 2700.3, "tp": 2718.0}
        ]
        self.bot.initial_risk_map[801] = 10.0
        self.bot.manage_open_positions("XAUUSDc")
        # Target SL should be open + 0.8 * 10 = 2708.0
        self.mock_connector.modify_position.assert_called_with(801, 2708.0, 2718.0)

    def test_smc_devil_trailing_lock(self):
        """Test SMC x STO Devil locks +0.8R at 1.4R and +1.2R at 1.8R."""
        smc_magic = STRATEGY_MAGIC_MAP["SMC_X_STO_H1"]["pos1"]
        
        # Test 1: At 1.45R -> Lock +0.8R
        self.mock_connector.get_market_info.return_value = {"bid": 2714.5, "ask": 2714.7}
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 901, "magic": smc_magic, "symbol": "XAUUSDc", "type": "BUY", "price_open": 2700.0, "sl": 2700.3, "tp": 2722.0}
        ]
        self.bot.initial_risk_map[901] = 10.0
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(901, 2708.0, 2722.0)

        # Test 2: At 1.85R -> Lock +1.2R
        self.mock_connector.get_market_info.return_value = {"bid": 2718.5, "ask": 2718.7}
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(901, 2712.0, 2722.0)

    def test_news_momentum_volume_filter(self):
        """Test News Momentum Expansion requires volume spike when not in high-impact news."""
        # Create dummy df where last candle breaks out above swing high
        closes = [2700.0]*20 + [2705.0, 2700.0]
        highs = [2702.0]*20 + [2706.0, 2701.0]
        lows = [2698.0]*20 + [2699.5, 2699.0]
        opens = [2699.0]*20 + [2700.0, 2700.0]
        
        # Case A: Low volume (100 vs MA 500) -> Should NOT trigger
        vols_low = [500]*20 + [100, 100]
        df_low = pd.DataFrame({'close': closes, 'high': highs, 'low': lows, 'open': opens, 'tick_volume': vols_low, 'rsi14': [60.0]*22})
        b_sig, s_sig, _ = self.bot._check_news_momentum_expansion(df_low, {"is_news_active": False})
        self.assertFalse(b_sig)

        # Case B: High volume (800 vs MA 500 = 1.6x) -> Should trigger
        vols_high = [500]*20 + [800, 100]
        df_high = pd.DataFrame({'close': closes, 'high': highs, 'low': lows, 'open': opens, 'tick_volume': vols_high, 'rsi14': [60.0]*22})
        b_sig, s_sig, _ = self.bot._check_news_momentum_expansion(df_high, {"is_news_active": False})
        self.assertTrue(b_sig)

if __name__ == "__main__":
    unittest.main()
