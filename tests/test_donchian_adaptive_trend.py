"""
Unit Test Suite for DONCHIAN_ADAPTIVE_TREND (Break-and-Retest v2):
1. Registration in STRATEGY_MAGIC_MAP (555940, 555941)
2. Risk Profile Isolation (0.5% Risk, FIXED mode)
3. Strategy Analytics Classification & Status
4. Strategy Optimizer Registration
5. Phase 1 (ALERT): Bullish breakout sets alert, no immediate order
6. Phase 2 (ENTRY): Retest bar fires BUY order
7. Phase 1 (ALERT): Bearish breakout sets SELL alert
8. Timeout: Alert cleared after >3 bars without retest
9. Stepped Trailing Stop (1.0R -> BE, 1.5R -> +0.8R, 2.0R -> +1.4R)
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
        self.assertEqual(profile["base_rr"], 1.00)

    def _make_synthetic_df(self, seed=42, n=120, base=2500.0):
        """Helper: create n bars of random-walk M5 OHLC data (may have high CHOP)."""
        np.random.seed(seed)
        closes = [base]
        for _ in range(n):
            closes.append(closes[-1] + np.random.uniform(-0.5, 0.5))
        df = pd.DataFrame({
            'open':   closes[:-1],
            'close':  closes[1:],
            'high':   [max(o, c) + 0.5 for o, c in zip(closes[:-1], closes[1:])],
            'low':    [min(o, c) - 0.5 for o, c in zip(closes[:-1], closes[1:])],
            'volume': [100] * n
        })
        return df

    def _make_trending_df(self, n=120, base=2500.0, step=0.30, noise=0.05):
        """
        Helper: create n bars of TRENDING M5 OHLC data with low CHOP (< 58).
        Uses steady directional drift with small noise so the market regime
        filters (CHOP < 58, ATR Pct >= 35%) are likely to pass.
        """
        np.random.seed(7)
        closes = [base]
        for _ in range(n):
            closes.append(closes[-1] + step + np.random.uniform(-noise, noise))
        df = pd.DataFrame({
            'open':   closes[:-1],
            'close':  closes[1:],
            'high':   [max(o, c) + 0.40 for o, c in zip(closes[:-1], closes[1:])],
            'low':    [min(o, c) - 0.40 for o, c in zip(closes[:-1], closes[1:])],
            'volume': [100] * n
        })
        return df

    def _mock_h1_bullish(self):
        """Return H1 df where H1 is in uptrend (ema50 above ema200)."""
        closes = [2500.0 + i * 0.5 for i in range(210)]
        return pd.DataFrame({
            'close': closes,
            'open':  closes,
            'high':  [c + 0.5 for c in closes],
            'low':   [c - 0.5 for c in closes],
        })

    def _mock_h1_bearish(self):
        """Return H1 df where H1 is in downtrend (ema50 below ema200)."""
        closes = [2600.0 - i * 0.5 for i in range(210)]
        return pd.DataFrame({
            'close': closes,
            'open':  closes,
            'high':  [c + 0.5 for c in closes],
            'low':   [c - 0.5 for c in closes],
        })

    def test_phase1_alert_set_no_immediate_entry(self):
        """
        Phase 1: On breakout bar, function should return (False, False)
        and set _donchian_alert state. No order fired immediately.
        Uses trending data so CHOP < 58 and ATR Pct >= 35% pass.
        """
        df = self._make_trending_df(n=120)
        self.mock_connector.get_rates.return_value = self._mock_h1_bullish()
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, None, None, None))

        # Force last closed bar (b1 = df.iloc[-2]) to be a strong bullish breakout
        donchian_high = float(df['high'].iloc[-22:-2].max())
        df.iloc[-2, df.columns.get_loc('open')]  = donchian_high - 0.30
        df.iloc[-2, df.columns.get_loc('close')] = donchian_high + 2.50  # breakout
        df.iloc[-2, df.columns.get_loc('high')]  = donchian_high + 3.00
        df.iloc[-2, df.columns.get_loc('low')]   = donchian_high - 0.40
        # Ensure b2 was close to (not breaking) donchian_high
        df.iloc[-3, df.columns.get_loc('close')] = donchian_high - 0.10

        buy_sig, sell_sig, reason = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")

        # Phase 1: must NOT fire order
        self.assertFalse(buy_sig, "Phase 1 should NOT return buy_sig=True immediately")
        self.assertFalse(sell_sig)
        self.assertEqual(reason, "")
        # But alert must be set
        self.assertIsNotNone(self.bot._donchian_alert)
        self.assertEqual(self.bot._donchian_alert["direction"], "BUY")
        self.assertAlmostEqual(self.bot._donchian_alert["level"], donchian_high, places=1)

    def test_phase2_retest_fires_buy_entry(self):
        """
        Phase 2: After Phase 1 ALERT is set, a pullback bar that retests
        the broken level and closes above it should fire BUY.
        The CHOP/ATR filters still run but use _alert values from Phase 1,
        so pre-set a valid alert and use trending data for the retest bar.
        """
        df = self._make_trending_df(n=120)
        self.mock_connector.get_rates.return_value = self._mock_h1_bullish()
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, None, None, None))

        donchian_high = float(df['high'].iloc[-22:-2].max())

        # Pre-set Phase 1 ALERT manually (simulates previous breakout bar)
        self.bot._donchian_alert = {
            "direction":    "BUY",
            "level":        donchian_high,
            "donchian_mid": donchian_high - 3.0,
            "curr_atr":     2.0,
            "chop_val":     50.0,
            "atr_pct":      60.0,
            "bars_waited":  0,
        }

        # Simulate a retest bar: wicks into level, body is bullish and strong
        # open = at level, close = 1.50 above level, high = 1.80 above, low = -0.50 below
        # => body = 1.50, range = 2.30, bull_body = 0.65 >= 0.35 ✓
        # => c_low (donchian_high - 0.50) <= level + 0.80 → pulled_back=True ✓
        # => c_close (donchian_high + 1.50) > level → closed_above=True ✓
        df.iloc[-2, df.columns.get_loc('open')]  = donchian_high - 0.00  # at level
        df.iloc[-2, df.columns.get_loc('close')] = donchian_high + 1.50  # well above
        df.iloc[-2, df.columns.get_loc('high')]  = donchian_high + 1.80  # small upper wick
        df.iloc[-2, df.columns.get_loc('low')]   = donchian_high - 0.50  # wick into level

        buy_sig, sell_sig, reason = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")

        self.assertTrue(buy_sig, "Phase 2 retest should fire BUY")
        self.assertFalse(sell_sig)
        self.assertIn("Retest BUY", reason)
        # Alert should be cleared after entry
        self.assertIsNone(self.bot._donchian_alert)

    def test_phase1_sell_alert_set(self):
        """
        Phase 1 Bearish: breakout below Donchian Low should set SELL alert,
        not fire order immediately. Uses trending (bearish) data for CHOP pass.
        """
        df = self._make_trending_df(n=120, step=-0.30)  # downtrend
        self.mock_connector.get_rates.return_value = self._mock_h1_bearish()
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, None, None, None))

        donchian_low = float(df['low'].iloc[-22:-2].min())
        df.iloc[-2, df.columns.get_loc('open')]  = donchian_low + 0.30
        df.iloc[-2, df.columns.get_loc('close')] = donchian_low - 2.50  # breakdown
        df.iloc[-2, df.columns.get_loc('high')]  = donchian_low + 0.40
        df.iloc[-2, df.columns.get_loc('low')]   = donchian_low - 3.00
        # Ensure b2 was just above donchian_low
        df.iloc[-3, df.columns.get_loc('close')] = donchian_low + 0.10

        buy_sig, sell_sig, reason = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")

        self.assertFalse(buy_sig)
        self.assertFalse(sell_sig, "Phase 1 SELL should NOT fire immediately")
        self.assertIsNotNone(self.bot._donchian_alert)
        self.assertEqual(self.bot._donchian_alert["direction"], "SELL")

    def test_alert_timeout_clears_after_3_bars(self):
        """
        If no valid retest occurs within 3 bars, alert is cleared (timeout).
        """
        df = self._make_synthetic_df(n=120)
        self.mock_connector.get_rates.return_value = self._mock_h1_bullish()
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, None, None, None))

        donchian_high = float(df['high'].iloc[-22:-2].max())

        # Pre-set alert at bars_waited=3 (about to expire)
        self.bot._donchian_alert = {
            "direction":    "BUY",
            "level":        donchian_high,
            "donchian_mid": donchian_high - 3.0,
            "curr_atr":     2.0,
            "chop_val":     50.0,
            "atr_pct":      60.0,
            "bars_waited":  3,
        }

        # Current bar does NOT retest (far from level)
        df.iloc[-2, df.columns.get_loc('open')]  = donchian_high + 5.0
        df.iloc[-2, df.columns.get_loc('close')] = donchian_high + 6.0
        df.iloc[-2, df.columns.get_loc('high')]  = donchian_high + 6.5
        df.iloc[-2, df.columns.get_loc('low')]   = donchian_high + 4.5

        buy_sig, sell_sig, reason = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")

        self.assertFalse(buy_sig)
        self.assertFalse(sell_sig)
        # Alert should be None (timed out)
        self.assertIsNone(self.bot._donchian_alert, "Alert should be cleared after timeout")

    def test_donchian_trailing_stop_logic(self):
        """Test stepped trailing stop for DONCHIAN_ADAPTIVE_TREND (RR 1:1 Scalp)."""
        # 1. Test BUY trailing at 0.6R -> BE (+0.20 USD)
        pos_buy_06r = [{
            'ticket': 111,
            'magic': 555941,
            'type': 'BUY',
            'price_open': 2500.00,
            'sl': 2496.00,  # 4.00 USD initial R
            'tp': 2504.00,  # 1.0R target (RR 1:1)
            'comment': 'Gold_DONCHIAN'
        }]
        self.mock_connector.get_open_positions.return_value = pos_buy_06r
        # Market price at 2502.50 -> 2.50 / 4.00 = 0.625R profit
        self.mock_connector.get_market_info.return_value = {"bid": 2502.50, "ask": 2502.75, "spread": 25.0}

        self.bot.manage_open_positions("XAUUSDc")
        # modify_position should be called with BE sl (open + 0.20 = 2500.20)
        self.mock_connector.modify_position.assert_called_with(111, 2500.20, 2504.00)

        # 2. Test BUY trailing at 0.8R -> +0.4R (2500 + 4*0.4 = 2501.60)
        self.mock_connector.modify_position.reset_mock()
        pos_buy_06r[0]['sl'] = 2500.20
        self.mock_connector.get_market_info.return_value = {"bid": 2503.40, "ask": 2503.65, "spread": 25.0} # 0.85R
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(111, 2501.60, 2504.00)

    def test_breakout_bar_cannot_trigger_retest_same_bar(self):
        """
        Verify that Phase 1 breakout bar NEVER triggers Phase 2 retest
        on subsequent iteration calls while still on the SAME closed bar.
        Retest must wait for a subsequent bar.
        """
        df = self._make_trending_df(n=120)
        self.mock_connector.get_rates.return_value = self._mock_h1_bullish()
        self.bot.is_setup_in_trading_hours = MagicMock(return_value=(True, None, None, None))

        donchian_high = float(df['high'].iloc[-22:-2].max())
        # Breakout candle on df.iloc[-2]
        df.iloc[-2, df.columns.get_loc('open')]  = donchian_high - 0.30
        df.iloc[-2, df.columns.get_loc('close')] = donchian_high + 2.50
        df.iloc[-2, df.columns.get_loc('high')]  = donchian_high + 3.00
        df.iloc[-2, df.columns.get_loc('low')]   = donchian_high - 0.40
        df.iloc[-3, df.columns.get_loc('close')] = donchian_high - 0.10

        # 1. First call (breakout detected) -> sets alert, returns False
        b_sig1, s_sig1, _ = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")
        self.assertFalse(b_sig1)
        self.assertIsNotNone(self.bot._donchian_alert)
        self.assertEqual(self.bot._donchian_alert["bars_waited"], 0)

        # 2. Second call on the EXACT SAME closed bar (1 second later tick) -> MUST NOT FIRE!
        b_sig2, s_sig2, _ = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")
        self.assertFalse(b_sig2, "Must NOT fire retest on the same breakout bar!")
        self.assertFalse(s_sig2)
        self.assertEqual(self.bot._donchian_alert["bars_waited"], 0, "bars_waited must not increment on same bar tick")

        # 3. Third call on the EXACT SAME bar -> STILL MUST NOT FIRE!
        b_sig3, s_sig3, _ = self.bot._check_donchian_adaptive_trend(df, "XAUUSDc")
        self.assertFalse(b_sig3)
        self.assertEqual(self.bot._donchian_alert["bars_waited"], 0)

if __name__ == "__main__":
    unittest.main()

