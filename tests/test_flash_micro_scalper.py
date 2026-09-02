import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
from datetime import datetime

from bot_engine import BotEngine
from strategy_optimizer import RealTimeStrategyOptimizer, SETUP_PROFILES
from strategy_analytics import StrategyAnalyticsManager


class TestFlashMicroScalper(unittest.TestCase):
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
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['rsi4'] = 50.0
        return df

    def test_flash_scalper_profile_exists(self):
        self.assertIn("FLASH_MICRO_SCALPER", SETUP_PROFILES)
        profile = SETUP_PROFILES["FLASH_MICRO_SCALPER"]
        self.assertEqual(profile["icon"], "⚡")
        self.assertEqual(profile["base_rr"], 1.10)

    def test_analytics_registry_contains_flash(self):
        manager = StrategyAnalyticsManager()
        self.assertIn("FLASH_MICRO_SCALPER", manager.STRATEGY_REGISTRY)
        setup = manager.STRATEGY_REGISTRY["FLASH_MICRO_SCALPER"]
        self.assertEqual(setup["category"], "SCALPING")

    def test_should_not_run_trend_for_flash_scalper(self):
        df_m5 = self._create_mock_m5_df()
        is_runner, reason = self.bot.should_run_trend("FLASH_MICRO_SCALPER", df_m5, "LONDON SESSION")
        self.assertFalse(is_runner)
        self.assertIn("Flash", reason)

    def test_flash_scalper_trend_pullback_buy(self):
        df = self._create_mock_m5_df(2650.0)
        # Set uptrend: ema9 > ema21
        df['ema9'] = 2652.0
        df['ema21'] = 2650.0
        df.loc[df.index[-2], 'low'] = 2651.8 # dipped to/near ema9
        df.loc[df.index[-2], 'open'] = 2652.1
        df.loc[df.index[-2], 'close'] = 2652.8 # closed green above ema9
        df.loc[df.index[-2], 'high'] = 2653.0
        df.loc[df.index[-2], 'rsi4'] = 55.0

        buy_sig, sell_sig, reason = self.bot._check_flash_micro_scalper(df)
        self.assertTrue(buy_sig)
        self.assertFalse(sell_sig)
        self.assertIn("Flash Scalper", reason)

    def test_flash_scalper_trend_pullback_sell(self):
        df = self._create_mock_m5_df(2650.0)
        # Set downtrend: ema9 < ema21
        df['ema9'] = 2648.0
        df['ema21'] = 2650.0
        df.loc[df.index[-2], 'high'] = 2648.2 # poked to/near ema9
        df.loc[df.index[-2], 'open'] = 2647.9
        df.loc[df.index[-2], 'close'] = 2647.2 # closed red below ema9
        df.loc[df.index[-2], 'low'] = 2647.0
        df.loc[df.index[-2], 'rsi4'] = 45.0

        buy_sig, sell_sig, reason = self.bot._check_flash_micro_scalper(df)
        self.assertFalse(buy_sig)
        self.assertTrue(sell_sig)
        self.assertIn("Flash Scalper", reason)

    def test_flash_scalper_sideways_exhaustion_buy(self):
        df = self._create_mock_m5_df(2650.0)
        df['ema9'] = 2650.0
        df['ema21'] = 2650.0
        # Price stretched 1.50 below ema9 + oversold rsi4
        df.loc[df.index[-2], 'low'] = 2648.2
        df.loc[df.index[-2], 'open'] = 2648.3
        df.loc[df.index[-2], 'close'] = 2648.9 # green close
        df.loc[df.index[-2], 'high'] = 2649.0
        df.loc[df.index[-2], 'rsi4'] = 15.0

        buy_sig, sell_sig, reason = self.bot._check_flash_micro_scalper(df)
        self.assertTrue(buy_sig)
        self.assertFalse(sell_sig)
        self.assertIn("Sideways Exhaustion", reason)


if __name__ == '__main__':
    unittest.main()
