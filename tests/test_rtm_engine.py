import time
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
        """Test active RTM models have registered magic numbers."""
        rtm_keys = [
            "RTM_M4_CONSERVATIVE",
            "RTM_M6_ELITE_GROWTH"
        ]
        for key in rtm_keys:
            self.assertIn(key, STRATEGY_MAGIC_MAP)
            magic_info = STRATEGY_MAGIC_MAP[key]
            self.assertIn("base", magic_info)
            self.assertIn("pos1", magic_info)
            self.assertTrue(magic_info["base"] >= 777000)

    def test_analytics_registry_contains_rtm_models(self):
        """Test StrategyAnalyticsManager has active RTM models and retired setups registered."""
        analytics = StrategyAnalyticsManager()
        for key in ["RTM_M4_CONSERVATIVE", "RTM_M6_ELITE_GROWTH"]:
            self.assertIn(key, analytics.STRATEGY_REGISTRY)
            entry = analytics.STRATEGY_REGISTRY[key]
            self.assertEqual(entry["category"], "RTM_PRO")
            self.assertEqual(entry["timeframe"], "M15 (H1 Filter)")
        self.assertIn("RETIRED_SETUPS", analytics.STRATEGY_REGISTRY)
        self.assertEqual(analytics.STRATEGY_REGISTRY["RETIRED_SETUPS"]["name"], "เซตอัพที่เลิกใช้")

    def test_deal_classification_for_rtm(self):
        """Test that closed deals with RTM magics or comments are accurately classified into active or retired."""
        analytics = StrategyAnalyticsManager()
        
        deal_m4 = MagicMock()
        deal_m4.magic = 777014
        deal_m4.comment = "Gold_RTM_M4_C"
        self.assertEqual(analytics._classify_deal_strategy(deal_m4), "RTM_M4_CONSERVATIVE")

        deal_m5 = MagicMock()
        deal_m5.magic = 777015
        deal_m5.comment = "Gold_RTM_M5_A"
        self.assertEqual(analytics._classify_deal_strategy(deal_m5), "RETIRED_SETUPS")

        deal_m6 = MagicMock()
        deal_m6.magic = 777016
        deal_m6.comment = "Gold_RTM_M6_E"
        self.assertEqual(analytics._classify_deal_strategy(deal_m6), "RTM_M6_ELITE_GROWTH")

        deal_m7 = MagicMock()
        deal_m7.magic = 777017
        deal_m7.comment = "Gold_RTM_M7_A"
        self.assertEqual(analytics._classify_deal_strategy(deal_m7), "RETIRED_SETUPS")

    def test_rtm_confluence_execution_router(self):
        """Test _process_rtm_confluence_engine queues M4/M6 for staggered pullback without breakout chasing."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.get_open_positions.return_value = []
        self.mock_connector.open_order.return_value = {"ticket": 99999}

        mock_signal = {
            "action": "BUY",
            "score": 88.0,
            "grade": "A+",
            "sl": 2690.0,
            "m15_time": datetime.now(),
            "reason": "RTM Quasimodo Bullish QML [A+] (88 pts)",
            "qml_price": 2695.0,
            "head_extreme": 2688.0,
            "break_level": 2702.0,
            "signal_close": 2700.0,
            "curr_atr": 4.0
        }
        self.bot._check_rtm_confluence_m15 = MagicMock(return_value=mock_signal)

        dummy_df = pd.DataFrame({'close': [2700.0]*20, 'low': [2695.0]*20, 'high': [2705.0]*20})
        
        # Test in PULLBACK_DUO mode: M4 and M6 queued, no immediate breakout chase order
        self.bot._process_rtm_confluence_engine(dummy_df, "XAUUSDc", 20.0, rtm_mode="PULLBACK_DUO")
        self.assertEqual(self.mock_connector.open_order.call_count, 0)
        self.assertIsNotNone(self.bot.active_rtm_setup)
        self.assertFalse(self.bot.active_rtm_setup["m4_filled"])
        self.assertFalse(self.bot.active_rtm_setup["m6_filled"])

    def test_rtm_anti_clustering_guard(self):
        """Test Anti-Clustering blocks positions within 1.50 USD of existing RTM entry."""
        m6_magic = STRATEGY_MAGIC_MAP["RTM_M6_ELITE_GROWTH"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 123, "magic": m6_magic, "price_open": 2700.00, "symbol": "XAUUSDc"}
        ]
        # Price 2700.80 is only 0.80 away -> Must be blocked (False)
        self.assertFalse(self.bot._check_rtm_clustering("XAUUSDc", 2700.80, min_gap=1.50))
        # Price 2697.50 is 2.50 away -> Must be allowed (True)
        self.assertTrue(self.bot._check_rtm_clustering("XAUUSDc", 2697.50, min_gap=1.50))
        # Price 2700.80 is only 0.80 away -> Must be blocked (False)
        self.assertFalse(self.bot._check_rtm_clustering("XAUUSDc", 2700.80, min_gap=1.50))
        # Price 2697.50 is 2.50 away -> Must be allowed (True)
        self.assertTrue(self.bot._check_rtm_clustering("XAUUSDc", 2697.50, min_gap=1.50))

    def test_rtm_pullback_m4_execution(self):
        """Test M4 executes when price pulls back to QML / discount zone."""
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.open_order.return_value = {"ticket": 99998}
        
        # Setup pending BUY signal
        self.bot.active_rtm_setup = {
            "action": "BUY",
            "grade": "A+",
            "score": 85.0,
            "sl": 2690.0,
            "reason": "Bullish QML",
            "qml_price": 2695.0,
            "head_extreme": 2688.0,
            "signal_close": 2700.0,
            "curr_atr": 4.0,
            "created_time": time.time(),
            "expiry_time": time.time() + 1800,
            "rtm_mode": "PULLBACK_DUO",
            "m4_filled": False,
            "m6_filled": False
        }
        # Price pulls back to 2696.0 (saved 4.0 USD vs 2700 breakout)
        self.mock_connector.get_market_info.return_value = {"ask": 2696.0, "bid": 2695.8, "spread": 20.0}
        self.mock_connector.get_open_positions.return_value = [] # No clustering

        rates_m5 = pd.DataFrame({
            'time': [datetime.now()]*5,
            'open': [2696.5]*5,
            'high': [2697.0]*5,
            'low': [2695.5]*5,
            'close': [2696.0]*5
        })
        self.bot._check_and_execute_pending_rtm_pullbacks("XAUUSDc", rates=rates_m5)
        self.assertTrue(self.bot.active_rtm_setup["m4_filled"])
        self.assertEqual(self.mock_connector.open_order.call_count, 1)

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
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M6_ELITE_GROWTH"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "PULLBACK_DR_EKK"))
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
        """Test that max_concurrent_setups defaults to 6 and permits concurrent positions."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0, "margin_level": 500.0}
        
        # Simulate 3 active setups already running
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 1, "magic": STRATEGY_MAGIC_MAP["ASIAN_RANGE_SNIPER"]["pos1"], "symbol": "XAUUSDc", "type": "BUY"},
            {"ticket": 2, "magic": STRATEGY_MAGIC_MAP["SMC_X_STO_H1"]["pos1"], "symbol": "XAUUSDc", "type": "BUY"},
            {"ticket": 3, "magic": STRATEGY_MAGIC_MAP["RTM_M4_CONSERVATIVE"]["pos1"], "symbol": "XAUUSDc", "type": "BUY"}
        ]
        
        # Verify other setups are NOT blocked by has_open_positions_for_setup
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "RTM_M6_ELITE_GROWTH"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "PULLBACK_DR_EKK"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "NEWS_MOMENTUM_EXPANSION"))

    def test_rtm_trailing_stop_dual_style(self):
        """Test trailing stop: M4/M6 locks +0.8R at 1.5R."""
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

    def test_news_momentum_trailing_lock_1_4r(self):
        """Test News Momentum locks +0.8R profit when reaching >= 1.4R."""
        self.mock_connector.get_market_info.return_value = {"bid": 2714.5, "ask": 2714.7}
        news_magic = STRATEGY_MAGIC_MAP["NEWS_MOMENTUM_EXPANSION"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 801, "magic": news_magic, "symbol": "XAUUSDc", "type": "BUY", "price_open": 2700.0, "sl": 2700.3, "tp": 2718.0}
        ]
        self.bot.initial_risk_map[801] = 10.0
        self.bot.manage_open_positions("XAUUSDc")
        # Target SL should be open + 0.8 * 10 = 2708.0
        self.mock_connector.modify_position.assert_called_with(801, 2708.0, 2718.0)

    def test_asian_sniper_breakeven_breathing_room(self):
        """Test Asian Range Sniper locks Break-Even at 1.0R and maintains breathing room without 1.4R choke."""
        self.mock_connector.get_market_info.return_value = {"bid": 2710.5, "ask": 2710.7}
        asian_magic = STRATEGY_MAGIC_MAP["ASIAN_RANGE_SNIPER"]["pos1"]
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 802, "magic": asian_magic, "symbol": "XAUUSDc", "type": "BUY", "price_open": 2700.0, "sl": 2695.0, "tp": 2718.0}
        ]
        self.bot.initial_risk_map[802] = 5.0
        self.bot.manage_open_positions("XAUUSDc")
        # Target SL should be open + 0.30 = 2700.30
        self.mock_connector.modify_position.assert_called_with(802, 2700.30, 2718.0)

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

    def test_rtm_pullback_duo_mode_bypasses_m5(self):
        """Test that in PULLBACK_DUO mode, M5 breakout scout is bypassed and only M4 & M6 are queued."""
        mock_signal = {
            "action": "BUY",
            "score": 85.0,
            "grade": "A+",
            "sl": 2690.0,
            "m15_time": datetime.now(),
            "reason": "Bullish QML",
            "qml_price": 2695.0,
            "head_extreme": 2688.0,
            "break_level": 2702.0,
            "signal_close": 2700.0,
            "curr_atr": 4.0
        }
        self.bot._check_rtm_confluence_m15 = MagicMock(return_value=mock_signal)
        dummy_df = pd.DataFrame({'close': [2700.0]*20, 'low': [2695.0]*20, 'high': [2705.0]*20})

        # Test PULLBACK_DUO: M5 is decommissioned, only M4 and M6 are tracked
        self.bot._process_rtm_confluence_engine(dummy_df, "XAUUSDc", 20.0, rtm_mode="PULLBACK_DUO")
        self.assertEqual(self.mock_connector.open_order.call_count, 0)
        self.assertIsNotNone(self.bot.active_rtm_setup)
        self.assertNotIn("m5_filled", self.bot.active_rtm_setup)
        self.assertFalse(self.bot.active_rtm_setup["m4_filled"])
        self.assertFalse(self.bot.active_rtm_setup["m6_filled"])

    def test_step_up_compounding_lot_calculation(self):
        """Test Step-Up Compounding calculates 2% risk on tiered milestones."""
        self.bot.config["strategy"]["risk_percent"] = 2.0
        self.bot.config["strategy"]["enable_step_up_compounding"] = True

        # Tier 1 ($10,000 base) -> 2% = $200 risk. With SL dist 3.00 USD (300 pts) -> 200 / (3.0 * 100) = 0.67 Lot
        self.mock_connector.get_account_info.return_value = {"balance": 11300.0, "equity": 11350.0}
        lot_t1 = self.bot.calculate_lot_size(3.00)
        self.assertEqual(lot_t1, 0.67)

        # Tier 2 ($15,000 base) -> 2% = $300 risk. With SL dist 3.00 USD -> 300 / 300 = 1.00 Lot
        self.mock_connector.get_account_info.return_value = {"balance": 16500.0, "equity": 16500.0}
        lot_t2 = self.bot.calculate_lot_size(3.00)
        self.assertEqual(lot_t2, 1.00)

        # Tier 3 ($20,000 base) -> 2% = $400 risk. With SL dist 3.00 USD -> 400 / 300 = 1.33 Lot
        self.mock_connector.get_account_info.return_value = {"balance": 22000.0, "equity": 22000.0}
        lot_t3 = self.bot.calculate_lot_size(3.00)
        self.assertEqual(lot_t3, 1.33)

    def test_earthetc_structural_sl_no_choke(self):
        """Test that wide structural SL (e.g. 11.50 USD) is preserved without 8.50 clamp."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.open_order.return_value = {"ticket": 5555}
        dummy_df = pd.DataFrame({'close': [2700.0]*20, 'low': [2685.0]*20, 'high': [2705.0]*20})

        # Provide custom SL at 2688.50 (SL dist = 11.50 USD, > 8.50)
        opt = {"custom_sl": 2688.50, "tp_ratio": 2.0, "lot_multiplier": 1.0}
        self.bot.execute_buy(dummy_df, "XAUUSDc", "Test Structural SL", opt_params=opt, strat_id="RTM_M4_CONSERVATIVE")
        
        # Verify open_order was called with sl = 2688.50 (NOT clamped to 2691.50)
        call_args = self.mock_connector.open_order.call_args[0]
        sl_placed = call_args[3]
        self.assertEqual(sl_placed, 2688.50)

    def test_news_momentum_earthetc_structural_sl_no_choke(self):
        """Test that News Momentum Expansion uses EarthETC Structural SL without arbitrary 7.00 choke."""
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.open_order.return_value = {"ticket": 9999}
        
        # Create df where lowest low in last 10 candles is 2690.0 (10.0 USD away)
        lows = [2695.0]*10 + [2690.0] + [2698.0]*9
        highs = [2702.0]*20
        closes = [2700.0]*20
        df = pd.DataFrame({'close': closes, 'low': lows, 'high': highs})
        
        self.bot.execute_buy(df, "XAUUSDc", "News Spike Breakout", strat_id="NEWS_MOMENTUM_EXPANSION")
        
        # Verify open_order was called with wide structural SL (NOT choked at 2700 - 7.00 = 2693.0)
        call_args = self.mock_connector.open_order.call_args[0]
        sl_placed = call_args[3]
        self.assertLess(sl_placed, 2692.0)  # Must be below the 7.00 choke line
        self.assertGreaterEqual(sl_placed, 2682.0)  # Must be above the 18.00 max ceiling

if __name__ == "__main__":
    unittest.main()

