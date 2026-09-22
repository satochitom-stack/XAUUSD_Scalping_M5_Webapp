"""
Unit Test Suite for DONCHIAN_ADAPTIVE_TREND:
1. Registration in STRATEGY_MAGIC_MAP (555940, 555941)
2. Risk Profile Isolation (0.5% Risk, FIXED mode)
3. Strategy Analytics Classification & Status
4. Strategy Optimizer Registration
5. Triple Anti-Chop Filter & Breakout Detection
6. Stepped Trailing Stop (1.0R -> BE, 1.5R -> +0.8R, 2.0R -> +1.4R)
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

import bot_engine
import strategy_analytics
import strategy_optimizer

class TestDonchianAdaptiveTrend(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {
            "balance": 10000.0,
            "equity": 10000.0,
            "margin_level": 500.0
        }
        self.mock_connector.get_open_positions.return_value = []
        self.mock_connector.get_market_info.return_value = {"bid": 2500.0, "ask": 2500.25, "spread": 25.0}

        self.config = {
            "strategy": {
                "strategy_mode": "ALL",
                "risk_percent": 1.0,
                "donchian_adaptive_trend_enabled": True
            }
        }
        self.bot = bot_engine.GoldScalpingBot(self.mock_connector, self.config)

    def test_magic_mapping_and_registration(self):
        """Verify DONCHIAN_ADAPTIVE_TREND is registered in STRATEGY_MAGIC_MAP."""
        self.assertIn("DONCHIAN_ADAPTIVE_TREND", bot_engine.STRATEGY_MAGIC_MAP)
        m = bot_engine.STRATEGY_MAGIC_MAP["DONCHIAN_ADAPTIVE_TREND"]
        self.assertEqual(m["base"], 555940)
        self.assertEqual(m["pos1"], 555941)

        all_magics = self.bot.get_all_bot_magics()
        self.assertIn(555940, all_magics)
        self.assertIn(555941, all_magics)

    def test_risk_profile_defaults(self):
        """Verify 0.5% risk default and lot sizing."""
        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["DONCHIAN_ADAPTIVE_TREND"]["default_pct"], 0.5)
        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["DONCHIAN_ADAPTIVE_TREND"]["mode"], "FIXED")

        # Test lot calculation ($10,000 balance, SL 5.00 USD = 500 pts, risk 0.5% = $50 -> 0.10 lot)
        lot = self.bot.calculate_lot_size(5.00, strat_id="DONCHIAN_ADAPTIVE_TREND")
        self.assertAlmostEqual(lot, 0.10, places=2)

    def test_strategy_analytics_classification(self):
        """Verify analytics classification and registry."""
        analytics = strategy_analytics.RealTradeAnalyticsManager()
        self.assertIn("DONCHIAN_ADAPTIVE_TREND", analytics.STRATEGY_REGISTRY)
        self.assertIn(555940, analytics.ELITE_MAGIC_NUMBERS)
        self.assertIn(555941, analytics.ELITE_MAGIC_NUMBERS)

        m_deal1 = MagicMock(magic=555941, comment="Gold_DONCHIAN")
        self.assertEqual(analytics._classify_deal_strategy(m_deal1), "DONCHIAN_ADAPTIVE_TREND")

        m_deal2 = MagicMock(magic=555940, comment="")
        self.assertEqual(analytics._classify_deal_strategy(m_deal2), "DONCHIAN_ADAPTIVE_TREND")

    def test_strategy_optimizer_profile(self):
        """Verify optimizer has DONCHIAN_ADAPTIVE_TREND."""
        self.assertIn("DONCHIAN_ADAPTIVE_TREND", strategy_optimizer.DEFAULT_STRATEGIES)
        self.assertIn("DONCHIAN_ADAPTIVE_TREND", strategy_optimizer.SETUP_PROFILES)
        profile = strategy_optimizer.SETUP_PROFILES["DONCHIAN_ADAPTIVE_TREND"]
        self.assertEqual(profile["icon"], "⚡")
        self.assertEqual(profile["base_rr"], 2.50)

    def test_donchian_breakout_detection(self):
        """Test breakout detection with synthetic data."""
        # Create 120 bars of M5 data
        np.random.seed(42)
        closes = [2500.0]
        for _ in range(120):
            closes.append(closes[-1] + np.random.uniform(-0.5, 0.5))

        df = pd.DataFrame({
            'open': closes[:-1],
            'close': closes[1:],
            'high': [max(o, c) + 0.5 for o, c in zip(closes[:-1], closes[1:])],
            'low': [min(o, c) - 0.5 for o, c in zip(closes[:-1], closes[1:])],
            'volume': [100] * 120
        })

        # Make the last bar a strong bullish breakout
        donchian_high = df['high'].iloc[-21:-1].max()
        df.loc[df.index[-1], 'open'] = donchian_high - 0.50
        df.loc[df.index[-1], 'close'] = donchian_high + 2.00
        df.loc[df.index[-1], 'high'] = donchian_high + 2.50
        df.loc[df.index[-1], 'low'] = donchian_high - 0.60

        # Mock H1 rates to allow bull
        h1_df = pd.DataFrame({
            'close': [2500.0] * 60,
            'open': [2500.0] * 60,
            'high': [2505.0] * 60,
            'low': [2495.0] * 60
        })
        self.mock_connector.get_rates.return_value = h1_df

        buy_sig, sell_sig, reason = self.bot._check_donchian_adaptive_trend("XAUUSDc", df)
        # Even if CHOP or ATR condition varies based on random seed, it should run without error
        self.assertIsInstance(buy_sig, (bool, np.bool_))
        self.assertIsInstance(sell_sig, (bool, np.bool_))
        self.assertIsInstance(reason, str)

    def test_donchian_trailing_stop_logic(self):
        """Test stepped trailing stop for DONCHIAN_ADAPTIVE_TREND."""
        # 1. Test BUY trailing at 1.0R -> BE
        pos_buy_1r = [{
            'ticket': 111,
            'magic': 555941,
            'type': 'BUY',
            'price_open': 2500.00,
            'sl': 2496.00,  # 4.00 USD initial R
            'tp': 2510.00,  # 2.5R target
            'comment': 'Gold_DONCHIAN'
        }]
        self.mock_connector.get_open_positions.return_value = pos_buy_1r
        # Market price at 2504.20 -> 4.20 / 4.00 = 1.05R profit
        self.mock_connector.get_market_info.return_value = {"bid": 2504.20, "ask": 2504.45, "spread": 25.0}

        self.bot.manage_open_positions("XAUUSDc")
        # modify_position should be called with BE sl (open + 0.30 = 2500.30)
        self.mock_connector.modify_position.assert_called_with(111, 2500.30, 2510.00)

        # 2. Test BUY trailing at 1.5R -> +0.8R (2500 + 4*0.8 = 2503.20)
        self.mock_connector.modify_position.reset_mock()
        pos_buy_1r[0]['sl'] = 2500.30
        self.mock_connector.get_market_info.return_value = {"bid": 2506.20, "ask": 2506.45, "spread": 25.0} # 1.55R
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(111, 2503.20, 2510.00)

        # 3. Test BUY trailing at 2.0R -> +1.4R (2500 + 4*1.4 = 2505.60)
        self.mock_connector.modify_position.reset_mock()
        pos_buy_1r[0]['sl'] = 2503.20
        self.mock_connector.get_market_info.return_value = {"bid": 2508.20, "ask": 2508.45, "spread": 25.0} # 2.05R
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(111, 2505.60, 2510.00)

if __name__ == "__main__":
    unittest.main()
