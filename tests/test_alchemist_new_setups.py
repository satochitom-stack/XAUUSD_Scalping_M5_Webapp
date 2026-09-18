"""
Unit Test Suite for Alchemist Trading Notes Setups:
1. ICT_JUDAS_RTM_QM (0.5% Risk, London Killzone)
2. ICT_SILVER_BULLET_FVG (0.5% Risk, NY AM Killzone)
3. EW_WAVE3_BREAKER (1.0% Risk, Trend Session)
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, time as dtime, timezone, timedelta
import pandas as pd
import numpy as np

import bot_engine
import strategy_analytics
import strategy_optimizer

class TestAlchemistNewSetups(unittest.TestCase):
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
                "strategy_mode": "ALL",
                "risk_percent": 1.0,
                "ict_judas_rtm_qm_enabled": True,
                "ict_silver_bullet_fvg_enabled": True,
                "ew_wave3_breaker_enabled": True
            }
        }
        self.bot = bot_engine.GoldScalpingBot(self.mock_connector, self.config)

    def test_magic_mapping_and_registration(self):
        """Verify all 3 new setups are registered in STRATEGY_MAGIC_MAP."""
        new_setups = ["ICT_JUDAS_RTM_QM", "ICT_SILVER_BULLET_FVG", "EW_WAVE3_BREAKER"]
        for s in new_setups:
            self.assertIn(s, bot_engine.STRATEGY_MAGIC_MAP)
            m = bot_engine.STRATEGY_MAGIC_MAP[s]
            self.assertTrue(m["base"] > 0)
            self.assertTrue(m["pos1"] > 0)

        all_magics = self.bot.get_all_bot_magics()
        self.assertIn(555910, all_magics)
        self.assertIn(555920, all_magics)
        self.assertIn(555930, all_magics)

    def test_risk_profile_defaults(self):
        """Verify specific risk isolation: 0.5% for Judas & Silver Bullet, 1.0% for EW Wave 3."""
        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["ICT_JUDAS_RTM_QM"]["default_pct"], 0.5)
        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["ICT_JUDAS_RTM_QM"]["mode"], "FIXED")

        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["ICT_SILVER_BULLET_FVG"]["default_pct"], 0.5)
        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["ICT_SILVER_BULLET_FVG"]["mode"], "FIXED")

        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["EW_WAVE3_BREAKER"]["default_pct"], 1.0)
        self.assertEqual(bot_engine.RISK_PROFILE_DEFAULTS["EW_WAVE3_BREAKER"]["mode"], "FIXED")

        # Test calculate_lot_size math ($10,000 balance, SL dist = 5.00 USD = 500 pts)
        # 0.5% risk = $50 / 500 = 0.10 lot
        # 1.0% risk = $100 / 500 = 0.20 lot
        sl_dist = 5.00
        lot_judas = self.bot.calculate_lot_size(sl_dist, strat_id="ICT_JUDAS_RTM_QM")
        self.assertAlmostEqual(lot_judas, 0.10, places=2)

        lot_sb = self.bot.calculate_lot_size(sl_dist, strat_id="ICT_SILVER_BULLET_FVG")
        self.assertAlmostEqual(lot_sb, 0.10, places=2)

        lot_ew = self.bot.calculate_lot_size(sl_dist, strat_id="EW_WAVE3_BREAKER")
        self.assertAlmostEqual(lot_ew, 0.20, places=2)

    def test_strategy_analytics_classification(self):
        """Verify deals with new comments/magics are classified properly in analytics."""
        analytics = strategy_analytics.RealTradeAnalyticsManager()
        self.assertIn("ICT_JUDAS_RTM_QM", analytics.STRATEGY_REGISTRY)
        self.assertIn("ICT_SILVER_BULLET_FVG", analytics.STRATEGY_REGISTRY)
        self.assertIn("EW_WAVE3_BREAKER", analytics.STRATEGY_REGISTRY)

        m_deal1 = MagicMock(magic=555911, comment="Gold_ICT_JUDA")
        self.assertEqual(analytics._classify_deal_strategy(m_deal1), "ICT_JUDAS_RTM_QM")

        m_deal2 = MagicMock(magic=555921, comment="Gold_ICT_SILV")
        self.assertEqual(analytics._classify_deal_strategy(m_deal2), "ICT_SILVER_BULLET_FVG")

        m_deal3 = MagicMock(magic=555931, comment="Gold_EW_WAVE")
        self.assertEqual(analytics._classify_deal_strategy(m_deal3), "EW_WAVE3_BREAKER")

    def test_strategy_optimizer_profiles(self):
        """Verify SETUP_PROFILES and DEFAULT_STRATEGIES contain all 3 new setups."""
        for s in ["ICT_JUDAS_RTM_QM", "ICT_SILVER_BULLET_FVG", "EW_WAVE3_BREAKER"]:
            self.assertIn(s, strategy_optimizer.DEFAULT_STRATEGIES)
            self.assertIn(s, strategy_optimizer.SETUP_PROFILES)

    def test_position_isolation_guards(self):
        """Verify each new strategy isolates its own open positions."""
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 1001, "magic": 555911, "symbol": "XAUUSDc", "type": "BUY"}
        ]
        self.assertTrue(self.bot.has_open_positions_for_setup("XAUUSDc", "ICT_JUDAS_RTM_QM"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "ICT_SILVER_BULLET_FVG"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "EW_WAVE3_BREAKER"))
        self.assertFalse(self.bot.has_open_positions_for_setup("XAUUSDc", "KC_LIQUIDITY_DOMINANCE"))

    @patch('bot_engine.datetime')
    def test_ict_judas_rtm_qm_signal_detection(self, mock_dt):
        """Verify ICT Judas Swing & RTM Quasimodo detects Bearish QM during London session."""
        mock_now = datetime(2026, 9, 15, 15, 0, tzinfo=timezone(timedelta(hours=7)))
        mock_dt.now.return_value = mock_now
        self.mock_connector.current_time = None

        # Build synthetic 40 bars
        data = []
        for i in range(25):
            data.append({"open": 2405.0, "high": 2408.0, "low": 2402.0, "close": 2405.0, "volume": 100})

        # London open (bars 25-39):
        data.append({"open": 2405.0, "high": 2412.0, "low": 2404.0, "close": 2410.0, "volume": 120})
        data.append({"open": 2410.0, "high": 2410.0, "low": 2406.0, "close": 2407.0, "volume": 110})
        data.append({"open": 2407.0, "high": 2414.0, "low": 2407.0, "close": 2413.0, "volume": 250})
        data.append({"open": 2413.0, "high": 2413.0, "low": 2400.0, "close": 2401.0, "volume": 280})
        for _ in range(7):
            data.append({"open": 2404.0, "high": 2406.0, "low": 2403.0, "close": 2405.0, "volume": 100})
        data.append({"open": 2405.0, "high": 2411.8, "low": 2405.0, "close": 2411.0, "volume": 150})
        data.append({"open": 2411.5, "high": 2412.0, "low": 2408.0, "close": 2408.5, "volume": 180})
        data.append({"open": 2408.5, "high": 2409.0, "low": 2408.0, "close": 2408.5, "volume": 50})

        df = pd.DataFrame(data)
        b_sig, s_sig, reason = self.bot._check_ict_judas_rtm_qm(df, "XAUUSDc")
        self.assertTrue(s_sig)
        self.assertFalse(b_sig)
        self.assertIn("Bearish QM", reason)

    @patch('bot_engine.datetime')
    def test_ict_silver_bullet_fvg_detection(self, mock_dt):
        """Verify ICT NY Silver Bullet detects Bullish FVG after SSL sweep."""
        mock_now = datetime(2026, 9, 15, 21, 15, tzinfo=timezone(timedelta(hours=7)))
        mock_dt.now.return_value = mock_now
        self.mock_connector.current_time = None

        data = []
        for i in range(25):
            data.append({"open": 2405.0, "high": 2408.0, "low": 2402.0, "close": 2405.0, "volume": 100})

        data.append({"open": 2404.0, "high": 2404.0, "low": 2399.0, "close": 2400.0, "volume": 200})
        data.append({"open": 2400.0, "high": 2402.0, "low": 2399.5, "close": 2401.5, "volume": 150})
        data.append({"open": 2401.5, "high": 2407.0, "low": 2401.0, "close": 2406.8, "volume": 350})
        data.append({"open": 2406.8, "high": 2407.0, "low": 2404.2, "close": 2405.5, "volume": 180})
        data.append({"open": 2405.5, "high": 2406.0, "low": 2405.0, "close": 2405.8, "volume": 50})

        df = pd.DataFrame(data)
        b_sig, s_sig, reason = self.bot._check_ict_silver_bullet_fvg(df, "XAUUSDc")
        self.assertTrue(b_sig)
        self.assertFalse(s_sig)
        self.assertIn("Bullish FVG", reason)

        # Test at 19:10 Thai time (inside new 19:00 - 23:00 window)
        mock_dt.now.return_value = datetime(2026, 9, 15, 19, 10, tzinfo=timezone(timedelta(hours=7)))
        b_sig, _, _ = self.bot._check_ict_silver_bullet_fvg(df, "XAUUSDc")
        self.assertTrue(b_sig)

        # Test outside window: 18:55
        mock_dt.now.return_value = datetime(2026, 9, 15, 18, 55, tzinfo=timezone(timedelta(hours=7)))
        b_sig, _, _ = self.bot._check_ict_silver_bullet_fvg(df, "XAUUSDc")
        self.assertFalse(b_sig)

        # Test outside window: 23:05
        mock_dt.now.return_value = datetime(2026, 9, 15, 23, 5, tzinfo=timezone(timedelta(hours=7)))
        b_sig, _, _ = self.bot._check_ict_silver_bullet_fvg(df, "XAUUSDc")
        self.assertFalse(b_sig)

    @patch('bot_engine.datetime')
    def test_ew_wave3_breaker_detection(self, mock_dt):
        """Verify Elliott Wave 3 detects Wave 3 breakout above Wave 1 top."""
        mock_now = datetime(2026, 9, 15, 16, 30, tzinfo=timezone(timedelta(hours=7)))
        mock_dt.now.return_value = mock_now
        self.mock_connector.current_time = None

        data = []
        for i in range(15):
            data.append({"open": 2400.0, "high": 2402.0, "low": 2399.0, "close": 2400.0, "volume": 100})

        data.append({"open": 2400.0, "high": 2402.0, "low": 2398.0, "close": 2401.0, "volume": 120})
        for p in [2404.0, 2407.0, 2410.0]:
            data.append({"open": p-2, "high": p, "low": p-2.5, "close": p-0.2, "volume": 150})

        for p in [2408.0, 2405.5, 2404.0]:
            data.append({"open": p+1, "high": p+1.5, "low": p, "close": p+0.2, "volume": 100})

        data.append({"open": 2404.5, "high": 2409.0, "low": 2404.0, "close": 2408.5, "volume": 200})
        data.append({"open": 2408.5, "high": 2412.0, "low": 2408.0, "close": 2411.5, "volume": 350})
        data.append({"open": 2411.5, "high": 2412.0, "low": 2411.0, "close": 2411.8, "volume": 50})

        df = pd.DataFrame(data)
        b_sig, s_sig, reason = self.bot._check_ew_wave3_breaker(df, "XAUUSDc")
        self.assertTrue(b_sig)
        self.assertFalse(s_sig)
        self.assertIn("Breaker Bullish", reason)

    @patch('bot_engine.datetime')
    def test_ew_wave3_breaker_h1_bear_blocks_buy(self, mock_dt):
        """Verify Elliott Wave 3 blocks BUY if H1 trend is bearish (Close < EMA50)."""
        mock_now = datetime(2026, 9, 15, 16, 30, tzinfo=timezone(timedelta(hours=7)))
        mock_dt.now.return_value = mock_now
        self.mock_connector.current_time = None

        # Mock H1 dataframe where close is well below EMA50
        df_h1 = pd.DataFrame({
            "time": pd.date_range("2026-09-15 00:00", periods=40, freq="1h"),
            "open": [2450.0 - i * 1.0 for i in range(40)],
            "high": [2451.0 - i * 1.0 for i in range(40)],
            "low": [2449.0 - i * 1.0 for i in range(40)],
            "close": [2450.0 - i * 1.0 for i in range(40)],
        })
        self.mock_connector.get_rates.return_value = df_h1

        data = []
        for i in range(15):
            data.append({"open": 2400.0, "high": 2402.0, "low": 2399.0, "close": 2400.0, "volume": 100})
        data.append({"open": 2400.0, "high": 2402.0, "low": 2398.0, "close": 2401.0, "volume": 120})
        for p in [2404.0, 2407.0, 2410.0]:
            data.append({"open": p-2, "high": p, "low": p-2.5, "close": p-0.2, "volume": 150})
        for p in [2408.0, 2405.5, 2404.0]:
            data.append({"open": p+1, "high": p+1.5, "low": p, "close": p+0.2, "volume": 100})
        data.append({"open": 2404.5, "high": 2409.0, "low": 2404.0, "close": 2408.5, "volume": 200})
        data.append({"open": 2408.5, "high": 2412.0, "low": 2408.0, "close": 2411.5, "volume": 350})
        data.append({"open": 2411.5, "high": 2412.0, "low": 2411.0, "close": 2411.8, "volume": 50})
        df = pd.DataFrame(data)

        b_sig, s_sig, _ = self.bot._check_ew_wave3_breaker(df, "XAUUSDc")
        self.assertFalse(b_sig, "Must NOT buy when H1 trend is bearish")

if __name__ == '__main__':
    unittest.main()
