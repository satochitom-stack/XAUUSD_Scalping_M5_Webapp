"""
Unit Test Suite for KC Forex Trading (Liquidity Sweep + Candle Dominance) - Pillar #5
Verifies:
1. Strategy registration and Magic Number mapping (555880 - 555883)
2. Deal classification in StrategyAnalytics
3. Strategy Optimizer integration and Setup Profile
4. 1.5% Step-Up Compounding Risk Isolation
5. Detection of Bullish/Bearish Liquidity Sweeps with Candle Dominance
6. Position Isolation & Guard
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, time as dtime, timezone, timedelta
import pandas as pd
import numpy as np

import bot_engine
import strategy_analytics
import strategy_optimizer


class TestKCLiquidityDominanceStrategy(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {
            "balance": 10000.0,
            "equity": 10000.0,
            "margin_level": 500.0
        }
        self.mock_connector.get_open_positions.return_value = []
        self.mock_connector.get_market_info.return_value = {"bid": 2400.0, "ask": 2400.25, "spread": 25.0}

        self.config = {
            "strategy": {
                "enable_step_up_compounding": True,
                "strategy_mode": "ALL",
                "risk_percent": 1.0,
                "kc_liquidity_dominance_enabled": True
            }
        }
        self.bot = bot_engine.GoldScalpingBot(self.mock_connector, self.config)

    def test_magic_number_registration(self):
        """Verify KC_LIQUIDITY_DOMINANCE is registered in STRATEGY_MAGIC_MAP with proper magics."""
        self.assertIn("KC_LIQUIDITY_DOMINANCE", bot_engine.STRATEGY_MAGIC_MAP)
        m_info = bot_engine.STRATEGY_MAGIC_MAP["KC_LIQUIDITY_DOMINANCE"]
        self.assertEqual(m_info["base"], 555880)
        self.assertEqual(m_info["pos1"], 555881)
        self.assertEqual(m_info["pos2"], 555882)
        self.assertEqual(m_info["pos3"], 555883)

        all_magics = self.bot.get_all_bot_magics()
        self.assertIn(555880, all_magics)
        self.assertIn(555881, all_magics)

    def test_strategy_analytics_registration(self):
        """Verify KC_LIQUIDITY_DOMINANCE is registered in STRATEGY_REGISTRY and deal classification."""
        analytics = strategy_analytics.RealTradeAnalyticsManager()
        self.assertIn("KC_LIQUIDITY_DOMINANCE", analytics.STRATEGY_REGISTRY)
        reg_item = analytics.STRATEGY_REGISTRY["KC_LIQUIDITY_DOMINANCE"]
        self.assertEqual(reg_item["avg_rr"], "1:2.0")
        self.assertIn(555880, reg_item["magic_numbers"])

        # Test deal classification
        deal_mock = MagicMock()
        deal_mock.magic = 555881
        deal_mock.comment = "Gold_KC_LIQU"
        self.assertEqual(analytics._classify_deal_strategy(deal_mock), "KC_LIQUIDITY_DOMINANCE")

    def test_strategy_optimizer_registration(self):
        """Verify KC_LIQUIDITY_DOMINANCE is in DEFAULT_STRATEGIES and SETUP_PROFILES."""
        self.assertIn("KC_LIQUIDITY_DOMINANCE", strategy_optimizer.DEFAULT_STRATEGIES)
        self.assertIn("KC_LIQUIDITY_DOMINANCE", strategy_optimizer.SETUP_PROFILES)
        prof = strategy_optimizer.SETUP_PROFILES["KC_LIQUIDITY_DOMINANCE"]
        self.assertEqual(prof["base_rr"], 2.00)

    def test_risk_isolation_rules(self):
        """
        Verify 1.5% Step-Up Compounding Risk for KC_LIQUIDITY_DOMINANCE:
        - $10,000 balance * 1.5% = $150 risk
        - $5.00 SL distance = 500 points
        - Lot = $150 / 500 = 0.30 lot
        """
        sl_dist = 5.00
        lot_kc = self.bot.calculate_lot_size(sl_dist, strat_id="KC_LIQUIDITY_DOMINANCE")
        self.assertAlmostEqual(lot_kc, 0.30, places=2)

    def test_has_open_positions_isolation(self):
        """Verify position isolation protects KC_LIQUIDITY_DOMINANCE correctly."""
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 9991, "magic": 555881, "symbol": "XAUUSDc", "type": "BUY"}
        ]
        self.assertTrue(self.bot.has_open_positions_for_setup("XAUUSDc", "KC_LIQUIDITY_DOMINANCE"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "PULLBACK_DR_EKK"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "SMC_X_STO_H1"))

    @patch('bot_engine.datetime')
    def test_bullish_liquidity_sweep_detection(self, mock_datetime):
        """
        Verify detection of Bullish Liquidity Sweep + Candle Dominance during London/NY session:
        - Prior range with swing low at 2400.00
        - Bar i-1 or trigger bar sweeps below 2400.00 to 2398.50
        - Trigger bar closes strongly at 2403.00 with solid body (Candle Dominance)
        """
        # Mock Thai time to 16:30 (London session)
        th_tz = timezone(timedelta(hours=7))
        mock_now = datetime(2026, 9, 10, 16, 30, tzinfo=th_tz)
        mock_datetime.now.return_value = mock_now

        # Create DataFrame with 35 bars
        rows = []
        # First 30 bars: trading in 2400.0 to 2410.0 range
        for j in range(30):
            rows.append({
                "open": 2402.0 + (j % 3),
                "high": 2408.0,
                "low": 2400.5, # Swing low will be around 2400.5
                "close": 2404.0,
                "ema50": 2405.0,
                "ema150": 2405.0
            })

        # Bar 31 (prev2): Bearish bar
        rows.append({"open": 2403.0, "high": 2404.0, "low": 2401.0, "close": 2401.5, "ema50": 2405.0, "ema150": 2405.0})
        # Bar 32 (prev1): Bearish bar sweeping prior low 2400.5 down to 2398.5
        rows.append({"open": 2401.5, "high": 2402.0, "low": 2398.5, "close": 2399.0, "ema50": 2405.0, "ema150": 2405.0})
        # Bar 33 (trigger bar b1): Massive Bullish Dominance closing at 2403.0 (engulfing prev open 2401.5)
        rows.append({"open": 2399.5, "high": 2403.5, "low": 2399.0, "close": 2403.0, "ema50": 2405.0, "ema150": 2405.0})
        # Bar 34 (current incomplete bar):
        rows.append({"open": 2403.0, "high": 2403.5, "low": 2402.8, "close": 2403.2, "ema50": 2405.0, "ema150": 2405.0})

        df = pd.DataFrame(rows)
        b_sig, s_sig, reason = self.bot._check_kc_liquidity_dominance(df, "XAUUSDc")
        self.assertTrue(b_sig)
        self.assertFalse(s_sig)
        self.assertIn("Bullish Liquidity Sweep", reason)
        self.assertIn("Swept", reason)

    @patch('bot_engine.datetime')
    def test_bearish_liquidity_sweep_detection(self, mock_datetime):
        """
        Verify detection of Bearish Liquidity Sweep + Candle Dominance during London/NY session:
        - Prior range with swing high at 2420.00
        - Prev/Trigger bar sweeps above 2420.00 to 2422.50
        - Trigger bar closes strongly down at 2417.00 with solid body (Candle Dominance)
        """
        th_tz = timezone(timedelta(hours=7))
        mock_now = datetime(2026, 9, 10, 20, 0, tzinfo=th_tz)
        mock_datetime.now.return_value = mock_now

        rows = []
        for j in range(30):
            rows.append({
                "open": 2415.0 + (j % 3),
                "high": 2419.5, # Swing high is 2419.5
                "low": 2412.0,
                "close": 2416.0,
                "ema50": 2415.0,
                "ema150": 2415.0
            })

        # Bar 31 (prev2)
        rows.append({"open": 2416.0, "high": 2418.0, "low": 2415.0, "close": 2417.5, "ema50": 2415.0, "ema150": 2415.0})
        # Bar 32 (prev1): Sweeps above 2419.5 to 2422.0
        rows.append({"open": 2417.5, "high": 2422.0, "low": 2417.0, "close": 2420.5, "ema50": 2415.0, "ema150": 2415.0})
        # Bar 33 (trigger bar b1): Massive Bearish Dominance closing at 2416.0 (engulfing prev open 2417.5)
        rows.append({"open": 2420.0, "high": 2420.5, "low": 2415.5, "close": 2416.0, "ema50": 2415.0, "ema150": 2415.0})
        # Bar 34 (current incomplete bar)
        rows.append({"open": 2416.0, "high": 2416.5, "low": 2415.8, "close": 2416.0, "ema50": 2415.0, "ema150": 2415.0})

        df = pd.DataFrame(rows)
        b_sig, s_sig, reason = self.bot._check_kc_liquidity_dominance(df, "XAUUSDc")
        self.assertFalse(b_sig)
        self.assertTrue(s_sig)
        self.assertIn("Bearish Liquidity Sweep", reason)
        self.assertIn("Swept", reason)


if __name__ == '__main__':
    unittest.main()
