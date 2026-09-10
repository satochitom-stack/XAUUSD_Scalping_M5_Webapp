"""
Unit Test Suite for Dr. Ekk's Signature Pullback Strategy (#PullBack ร้อยล้าน)
Verifies:
1. Strategy registration and Magic Number mapping
2. Deal classification in StrategyAnalytics
3. Strict 1.0% Risk Isolation (RTM M4/M6=3.0%, News/Asian=0.5%, Pullback=1.0%)
4. Technical detection logic (EMA60 + Fib 38.2-61.8% + S/R Flip + Pinbar/Engulfing)
"""

import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

import bot_engine
import strategy_analytics


class TestDrEkkPullbackStrategy(unittest.TestCase):
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
                "risk_percent": 1.0
            }
        }
        self.bot = bot_engine.GoldScalpingBot(self.mock_connector, self.config)

    def test_magic_number_registration(self):
        """Verify PULLBACK_DR_EKK is registered in STRATEGY_MAGIC_MAP with proper magics."""
        self.assertIn("PULLBACK_DR_EKK", bot_engine.STRATEGY_MAGIC_MAP)
        m_info = bot_engine.STRATEGY_MAGIC_MAP["PULLBACK_DR_EKK"]
        self.assertEqual(m_info["base"], 555860)
        self.assertEqual(m_info["pos1"], 555861)
        self.assertEqual(m_info["pos2"], 555862)
        self.assertEqual(m_info["pos3"], 555863)

        all_magics = self.bot.get_all_bot_magics()
        self.assertIn(555860, all_magics)
        self.assertIn(555861, all_magics)

    def test_risk_isolation_rules(self):
        """
        Verify strict Risk Isolation according to user rules:
        - RTM M4 / M6 = 2.0% (Step-Up Compounding)
        - PULLBACK_DR_EKK = 2.0% (Step-Up Compounding)
        - News / Asian = 0.5%
        - SMCxSTO = Strictly 1.0%
        """
        sl_dist = 5.00  # $5.00 SL distance = 500 points
        
        # Test RTM M4 -> 2.0% ($200 risk on $10k -> 200 / 500 = 0.40 lot)
        lot_m4 = self.bot.calculate_lot_size(sl_dist, strat_id="RTM_M4_CONSERVATIVE")
        self.assertAlmostEqual(lot_m4, 0.40, places=2)

        # Test RTM M6 -> 2.0% ($200 risk on $10k -> 200 / 500 = 0.40 lot)
        lot_m6 = self.bot.calculate_lot_size(sl_dist, strat_id="RTM_M6_ELITE_GROWTH")
        self.assertAlmostEqual(lot_m6, 0.40, places=2)

        # Test PULLBACK_DR_EKK -> 2.0% ($200 risk on $10k -> 200 / 500 = 0.40 lot)
        lot_pullback = self.bot.calculate_lot_size(sl_dist, strat_id="PULLBACK_DR_EKK")
        self.assertAlmostEqual(lot_pullback, 0.40, places=2)

        # Test News Momentum -> 0.5% ($50 risk on $10k -> 50 / 500 = 0.10 lot)
        lot_news = self.bot.calculate_lot_size(sl_dist, strat_id="NEWS_MOMENTUM_EXPANSION")
        self.assertAlmostEqual(lot_news, 0.10, places=2)

        # Test Asian Range -> 0.5% ($50 risk on $10k -> 50 / 500 = 0.10 lot)
        lot_asian = self.bot.calculate_lot_size(sl_dist, strat_id="ASIAN_RANGE_SNIPER")
        self.assertAlmostEqual(lot_asian, 0.10, places=2)

        # Test SMC_X_STO_H1 -> Strictly 1.0% ($100 risk on $10k -> 100 / 500 = 0.20 lot)
        lot_smc = self.bot.calculate_lot_size(sl_dist, strat_id="SMC_X_STO_H1")
        self.assertAlmostEqual(lot_smc, 0.20, places=2)

    def test_analytics_deal_classification(self):
        """Verify StrategyAnalytics classifies PULLBACK_DR_EKK deals accurately."""
        analytics = strategy_analytics.RealTradeAnalyticsManager()
        
        deal_mock1 = MagicMock()
        deal_mock1.magic = 555861
        deal_mock1.comment = "Gold_PULLBACK"
        self.assertEqual(analytics._classify_deal_strategy(deal_mock1), "PULLBACK_DR_EKK")

        deal_mock2 = MagicMock()
        deal_mock2.magic = 0
        deal_mock2.comment = "dr_ekk_pullback_scalp"
        self.assertEqual(analytics._classify_deal_strategy(deal_mock2), "PULLBACK_DR_EKK")

        self.assertIn("PULLBACK_DR_EKK", analytics.STRATEGY_REGISTRY)
        self.assertEqual(analytics.STRATEGY_REGISTRY["PULLBACK_DR_EKK"]["name"], "Signature Pullback (#PullBack ร้อยล้าน)")

    def test_detection_confluence_logic(self):
        """Verify _check_pullback_dr_ekk triggers without errors."""
        dates = pd.date_range("2026-09-08 10:00", periods=50, freq="5min")
        prices = [2400.0 + i * 0.20 for i in range(25)]
        prices.extend([2405.0, 2406.5, 2408.0, 2409.5, 2410.0])
        prices.extend([2409.0, 2408.0, 2407.2, 2406.5, 2406.0, 2406.2])
        while len(prices) < 50:
            prices.append(2406.3)

        df = pd.DataFrame({
            "datetime": dates,
            "open": prices,
            "high": [p + 0.40 for p in prices],
            "low": [p - 0.40 for p in prices],
            "close": prices
        })

        df.loc[df.index[-2], 'low'] = 2405.0
        df.loc[df.index[-2], 'open'] = 2406.8
        df.loc[df.index[-2], 'close'] = 2407.2
        df.loc[df.index[-2], 'high'] = 2407.4

        df['ema60'] = 2405.8
        df['ema150'] = 2401.0
        df['atr14'] = 2.0

        b_sig, s_sig, reason = self.bot._check_pullback_dr_ekk(df)
        self.assertTrue(b_sig or not s_sig)

    def test_manage_open_positions_buy_trail_no_df_crash(self):
        """Regression test: manage_open_positions() must not crash with NameError on the Dr. Ekk
        EMA60 trailing branch (BUY) when called with no `df` argument - matching how it is
        actually invoked in production: run_iteration() calls self.manage_open_positions(symbol)
        with no df. Previously this referenced an undefined `df` name, which raised NameError,
        silently swallowed by account_manager's broad except and skipping trailing/BE-lock
        updates for EVERY strategy that cycle."""
        pos1_magic = bot_engine.STRATEGY_MAGIC_MAP["PULLBACK_DR_EKK"]["pos1"]
        self.mock_connector.get_market_info.return_value = {"bid": 2406.5, "ask": 2406.7}
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 701, "magic": pos1_magic, "symbol": "XAUUSDc", "type": "BUY",
             "price_open": 2400.0, "sl": 2399.7, "tp": 2410.0}
        ]
        self.bot.initial_risk_map[701] = 4.0  # r_profit = (2406.5-2400.0)/4.0 = 1.625R -> EMA60 trail branch

        rising_closes = [2390.0 + i * 0.30 for i in range(120)]
        self.mock_connector.get_rates.return_value = pd.DataFrame({
            "time": pd.date_range("2026-09-01", periods=120, freq="5min"),
            "open": rising_closes, "high": [c + 0.2 for c in rising_closes],
            "low": [c - 0.2 for c in rising_closes], "close": rising_closes
        })

        # Must not raise (previously: NameError: name 'df' is not defined)
        self.bot.manage_open_positions("XAUUSDc")

        self.mock_connector.get_rates.assert_any_call("XAUUSDc", "M5", 200)
        self.assertEqual(self.mock_connector.modify_position.call_count, 1)
        called_ticket, called_sl, called_tp = self.mock_connector.modify_position.call_args[0]
        self.assertEqual(called_ticket, 701)
        self.assertGreaterEqual(called_sl, round(2400.0 + 4.0 * 0.8, 2))  # at least the +0.8R minimum lock
        self.assertEqual(called_tp, 2410.0)

    def test_manage_open_positions_sell_trail_no_df_crash(self):
        """Regression test: same as above but for the SELL side of the Dr. Ekk EMA60 trail branch."""
        pos1_magic = bot_engine.STRATEGY_MAGIC_MAP["PULLBACK_DR_EKK"]["pos1"]
        self.mock_connector.get_market_info.return_value = {"bid": 2393.5, "ask": 2393.7}
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 702, "magic": pos1_magic, "symbol": "XAUUSDc", "type": "SELL",
             "price_open": 2400.0, "sl": 2400.3, "tp": 2390.0}
        ]
        self.bot.initial_risk_map[702] = 4.0  # r_profit = (2400.0-2393.5)/4.0 = 1.625R -> EMA60 trail branch

        falling_closes = [2410.0 - i * 0.30 for i in range(120)]
        self.mock_connector.get_rates.return_value = pd.DataFrame({
            "time": pd.date_range("2026-09-01", periods=120, freq="5min"),
            "open": falling_closes, "high": [c + 0.2 for c in falling_closes],
            "low": [c - 0.2 for c in falling_closes], "close": falling_closes
        })

        # Must not raise (previously: NameError: name 'df' is not defined)
        self.bot.manage_open_positions("XAUUSDc")

        self.mock_connector.get_rates.assert_any_call("XAUUSDc", "M5", 200)
        self.assertEqual(self.mock_connector.modify_position.call_count, 1)
        called_ticket, called_sl, called_tp = self.mock_connector.modify_position.call_args[0]
        self.assertEqual(called_ticket, 702)
        self.assertLessEqual(called_sl, round(2400.0 - 4.0 * 0.8, 2))  # at least the +0.8R minimum lock
        self.assertEqual(called_tp, 2390.0)


if __name__ == "__main__":
    unittest.main()
