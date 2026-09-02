import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime

from bot_engine import BotEngine
from strategy_optimizer import RealTimeStrategyOptimizer, SETUP_PROFILES
from strategy_analytics import StrategyAnalyticsManager


class TestM1SniperConfirmation(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.config = {
            "symbol": "XAUUSDc",
            "strategy": {
                "risk_percent": 1.0,
                "daily_target_percent": 5.0,
                "daily_max_loss_percent": 3.0,
                "mode": "ALL"
            }
        }
        self.bot = BotEngine(self.mock_connector, self.config)

    def _create_mock_m5_df(self, base_price=2650.0):
        times = pd.date_range(end=datetime.now(), periods=40, freq='5min')
        df = pd.DataFrame({
            'time': times,
            'open': [base_price + i*0.1 for i in range(40)],
            'high': [base_price + i*0.1 + 0.5 for i in range(40)],
            'low': [base_price + i*0.1 - 0.5 for i in range(40)],
            'close': [base_price + i*0.1 + 0.2 for i in range(40)],
            'tick_volume': [100 + i*5 for i in range(40)]
        })
        df['sma20'] = df['close'].rolling(20).mean()
        df['bb_upper'] = df['sma20'] + 3.0
        df['bb_lower'] = df['sma20'] - 3.0
        return df

    def test_m1_sniper_profile_exists(self):
        self.assertIn("M1_SNIPER_CONFIRMATION", SETUP_PROFILES)
        profile = SETUP_PROFILES["M1_SNIPER_CONFIRMATION"]
        self.assertEqual(profile["icon"], "🎯")
        self.assertGreaterEqual(profile["base_rr"], 2.0)
        self.assertEqual(profile["max_rr"], 5.0)

    def test_analytics_registry_contains_m1(self):
        manager = StrategyAnalyticsManager()
        self.assertIn("M1_SNIPER_CONFIRMATION", manager.STRATEGY_REGISTRY)
        setup = manager.STRATEGY_REGISTRY["M1_SNIPER_CONFIRMATION"]
        self.assertEqual(setup["category"], "SCALPING")

    def test_should_run_trend_for_m1_sniper(self):
        df_m5 = self._create_mock_m5_df()
        is_runner, reason = self.bot.should_run_trend("M1_SNIPER_CONFIRMATION", df_m5, "NEW YORK SESSION")
        self.assertTrue(is_runner)
        self.assertIn("M1", reason)

    def test_m1_sniper_bullish_bos_detection(self):
        df_m5 = self._create_mock_m5_df(2650.0)
        df_m5.loc[df_m5.index[-2], 'close'] = df_m5['low'].iloc[-12:-2].min() + 0.50
        df_m5.loc[df_m5.index[-2], 'low'] = df_m5['low'].iloc[-12:-2].min()

        m1_times = pd.date_range(end=datetime.now(), periods=20, freq='1min')
        rates_m1 = pd.DataFrame({
            'time': m1_times,
            'open': [2650.0] * 20,
            'high': [2650.5] * 20,
            'low': [2649.5] * 20,
            'close': [2650.0] * 20,
            'tick_volume': [50] * 20
        })
        rates_m1.loc[rates_m1.index[-2], 'high'] = 2652.0
        rates_m1.loc[rates_m1.index[-2], 'open'] = 2650.2
        rates_m1.loc[rates_m1.index[-2], 'close'] = 2651.8
        self.mock_connector.get_rates.return_value = rates_m1

        buy_sig, sell_sig, reason = self.bot._check_m1_sniper_confirmation("XAUUSDc", df_m5, strat_mode="M1_SNIPER_CONFIRMATION")
        self.assertTrue(buy_sig)
        self.assertFalse(sell_sig)
        self.assertIn("M1 Sniper Confirmation", reason)

    def test_m1_sniper_bearish_bos_detection(self):
        df_m5 = self._create_mock_m5_df(2650.0)
        df_m5.loc[df_m5.index[-2], 'close'] = df_m5['high'].iloc[-12:-2].max() - 0.50
        df_m5.loc[df_m5.index[-2], 'high'] = df_m5['high'].iloc[-12:-2].max()

        m1_times = pd.date_range(end=datetime.now(), periods=20, freq='1min')
        rates_m1 = pd.DataFrame({
            'time': m1_times,
            'open': [2650.0] * 20,
            'high': [2650.5] * 20,
            'low': [2649.5] * 20,
            'close': [2650.0] * 20,
            'tick_volume': [50] * 20
        })
        rates_m1.loc[rates_m1.index[-2], 'low'] = 2648.0
        rates_m1.loc[rates_m1.index[-2], 'open'] = 2649.8
        rates_m1.loc[rates_m1.index[-2], 'close'] = 2648.2
        self.mock_connector.get_rates.return_value = rates_m1

        buy_sig, sell_sig, reason = self.bot._check_m1_sniper_confirmation("XAUUSDc", df_m5, strat_mode="M1_SNIPER_CONFIRMATION")
        self.assertFalse(buy_sig)
        self.assertTrue(sell_sig)
        self.assertIn("M1 Sniper Confirmation", reason)


if __name__ == '__main__':
    unittest.main()
