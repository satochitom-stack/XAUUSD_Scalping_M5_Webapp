import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
from datetime import datetime

from bot_engine import GoldScalpingBot
from strategy_optimizer import SETUP_PROFILES
from strategy_analytics import RealTradeAnalyticsManager

class TestAsianRangeSniper(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.config = {
            'symbol': 'XAUUSDc',
            'strategy': {
                'risk_percent': 1.0,
                'daily_target_percent': 5.0,
                'daily_max_loss_percent': 3.0,
                'strategy_mode': 'ALL'
            }
        }
        self.bot = GoldScalpingBot(self.mock_connector, self.config)

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
        df['std20'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['sma20'] + (2.0 * df['std20'])
        df['bb_lower'] = df['sma20'] - (2.0 * df['std20'])
        df['rsi7'] = 50.0
        return df

    def test_asian_sniper_profile_exists(self):
        self.assertIn('ASIAN_RANGE_SNIPER', SETUP_PROFILES)
        profile = SETUP_PROFILES['ASIAN_RANGE_SNIPER']
        self.assertEqual(profile['base_rr'], 1.40)

    def test_analytics_registry_contains_asian(self):
        manager = RealTradeAnalyticsManager()
        self.assertIn('ASIAN_RANGE_SNIPER', manager.STRATEGY_REGISTRY)
        setup = manager.STRATEGY_REGISTRY['ASIAN_RANGE_SNIPER']
        self.assertEqual(setup['category'], 'MEAN_REVERSION')

    def test_should_not_run_trend_for_asian_sniper(self):
        df_m5 = self._create_mock_m5_df()
        is_runner, reason = self.bot.should_run_trend('ASIAN_RANGE_SNIPER', df_m5, 'ASIAN SESSION')
        self.assertFalse(is_runner)
        self.assertIn('Asian', reason)

    def test_pina_colada_bands_and_caution_guard(self):
        df = self._create_mock_m5_df(2650.0)
        df.loc[df.index[-4], 'open'] = 2650.0; df.loc[df.index[-4], 'close'] = 2640.0; df.loc[df.index[-4], 'low'] = 2638.0
        df.loc[df.index[-3], 'open'] = 2640.0; df.loc[df.index[-3], 'close'] = 2630.0; df.loc[df.index[-3], 'low'] = 2628.0
        df.loc[df.index[-2], 'open'] = 2630.0; df.loc[df.index[-2], 'close'] = 2620.0; df.loc[df.index[-2], 'low'] = 2615.0

        pina = self.bot._calculate_pina_colada(df)
        self.assertTrue(pina['caution'])
        self.assertFalse(pina['coming_back_bull'])

    def test_pina_colada_coming_back_trigger(self):
        df = self._create_mock_m5_df(2650.0)
        pina_pre = self.bot._calculate_pina_colada(df)
        lb = pina_pre['lower_band']

        df.loc[df.index[-3], 'low'] = lb - 2.0
        df.loc[df.index[-3], 'close'] = lb - 1.0

        df.loc[df.index[-2], 'open'] = lb - 0.5
        df.loc[df.index[-2], 'close'] = lb + 1.5
        df.loc[df.index[-2], 'high'] = lb + 1.8
        df.loc[df.index[-2], 'low'] = lb - 0.6

        pina_post = self.bot._calculate_pina_colada(df)
        self.assertTrue(pina_post['coming_back_bull'])

if __name__ == '__main__':
    unittest.main()