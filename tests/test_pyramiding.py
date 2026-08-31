import os, sys, unittest, pandas as pd, numpy as np
from datetime import datetime
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_engine import GoldScalpingBot

class TestTrendPyramiding(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {'balance': 1000.0, 'equity': 1000.0}
        self.mock_connector.get_market_info.return_value = {'bid': 4610.00, 'ask': 4610.25, 'spread': 25.0}
        self.mock_connector.open_order.return_value = {'status': True, 'ticket': 999991, 'price': 4610.00}
        
        self.config = {
            'mt5': {'symbol': 'XAUUSDc', 'magic_number': 555888},
            'strategy': {
                'enable_trend_pyramiding': True,
                'max_pyramid_layers': 2,
                'pyramid_step_points': 350.0,
                'pyramid_lot_ratio': 0.60,
                'risk_percent': 2.0
            }
        }
        self.bot = GoldScalpingBot(self.mock_connector, self.config)

    def test_pyramiding_blocked_in_sideway_regime(self):
        dummy_df = pd.DataFrame([{'time': datetime.now(), 'open': 4608.0, 'high': 4610.5, 'low': 4607.5, 'close': 4609.5, 'ema20': 4608.0} for _ in range(50)])
        regime_info = {'regime': 'RANGING_SIDEWAY', 'label': 'Sideway', 'is_choppy': True}
        ea_positions = [{'ticket': 101, 'magic': 555890, 'type': 'BUY', 'volume': 0.02, 'price_open': 4600.0, 'sl': 4601.0}]
        self.bot.check_and_execute_pyramiding(dummy_df, 'XAUUSDc', ea_positions, regime_info)
        self.mock_connector.open_order.assert_not_called()

    def test_pyramiding_blocked_if_sl_not_locked_at_breakeven(self):
        dummy_df = pd.DataFrame([{'time': datetime.now(), 'open': 4608.0, 'high': 4610.5, 'low': 4607.5, 'close': 4609.5, 'ema20': 4608.0} for _ in range(50)])
        regime_info = {'regime': 'STRONG_BULLISH_TREND', 'label': 'Strong Trend', 'is_choppy': False}
        ea_positions = [{'ticket': 101, 'magic': 555890, 'type': 'BUY', 'volume': 0.02, 'price_open': 4600.0, 'sl': 4595.0}]
        self.bot.check_and_execute_pyramiding(dummy_df, 'XAUUSDc', ea_positions, regime_info)
        self.mock_connector.open_order.assert_not_called()

    def test_pyramiding_executes_layer1_when_breakeven_and_trending(self):
        dummy_df = pd.DataFrame([{'time': datetime.now(), 'open': 4608.0, 'high': 4610.5, 'low': 4607.5, 'close': 4609.5, 'ema20': 4608.0} for _ in range(50)])
        regime_info = {'regime': 'STRONG_BULLISH_TREND', 'label': 'Strong Trend', 'is_choppy': False}
        ea_positions = [{'ticket': 101, 'magic': 555890, 'type': 'BUY', 'volume': 0.02, 'price_open': 4600.0, 'sl': 4600.50}]
        self.bot.check_and_execute_pyramiding(dummy_df, 'XAUUSDc', ea_positions, regime_info)
        self.mock_connector.open_order.assert_called_once()
        args = self.mock_connector.open_order.call_args[0]
        self.assertEqual(args[0], 'XAUUSDc')
        self.assertEqual(args[1], 'BUY')
        self.assertEqual(args[5], 555891)

if __name__ == '__main__':
    unittest.main()