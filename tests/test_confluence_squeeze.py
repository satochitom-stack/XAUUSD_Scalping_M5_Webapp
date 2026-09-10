"""
Automated Unit Tests for the 6th Elite Pillar: CONFLUENCE_SQUEEZE_M15
(AI Confluence Squeeze Breakout - self-designed setup combining Volatility Squeeze/Clustering,
Expansion Breakout, Market Structure, Volume, and Session/H1-Trend confluence filters)
"""

import random
import unittest
from unittest.mock import MagicMock
import pandas as pd
from datetime import datetime, timedelta

from bot_engine import BotEngine, STRATEGY_MAGIC_MAP
from strategy_analytics import StrategyAnalyticsManager
from strategy_optimizer import SETUP_PROFILES, DEFAULT_STRATEGIES


def _make_squeeze_df(direction="BUY", total_baseline=45, tight_bars=28, baseline_price=2700.0,
                      low_volume_breakout=False, no_squeeze=False, seed=42):
    """
    Build a synthetic M15 rates DataFrame that simulates a genuine volatility-squeeze breakout:
      - `total_baseline` moderately volatile bars (sets a wide BB-width/ATR baseline history)
      - `tight_bars` very tight, low-range bars right after (the "coil" - BB width & ATR
        compress into their own recent low, satisfying the squeeze condition)
      - one strong expansion breakout candle (wide body, closes beyond the coil range and the
        20-bar swing high/low) in `direction`
      - one unused still-forming bar, so the last CLOSED candle is always iloc[-2]
    `low_volume_breakout=True` gives the breakout candle below-average tick_volume (to test the
    volume-confirmation filter). `no_squeeze=True` skips the tight-coil phase entirely (keeps
    baseline volatility all the way to the breakout, so no squeeze condition is met).
    """
    t0 = datetime(2026, 9, 10, 8, 0, 0)
    rows = []
    price = baseline_price
    rng = random.Random(seed)
    idx = 0
    for _ in range(total_baseline):
        o = price
        c = price + rng.uniform(-0.5, 0.5)
        h = max(o, c) + rng.uniform(0.1, 0.3)
        l = min(o, c) - rng.uniform(0.1, 0.3)
        rows.append({"time": t0 + timedelta(minutes=15 * idx), "open": o, "high": h, "low": l,
                      "close": c, "tick_volume": 150})
        price = c
        idx += 1

    coil_center = price
    if not no_squeeze:
        for _ in range(tight_bars):
            o = coil_center
            c = coil_center + rng.uniform(-0.03, 0.03)
            h = max(o, c) + 0.03
            l = min(o, c) - 0.03
            rows.append({"time": t0 + timedelta(minutes=15 * idx), "open": o, "high": h, "low": l,
                          "close": c, "tick_volume": 100})
            idx += 1

    if direction == "BUY":
        o = coil_center
        c = coil_center + 4.0
        h = c + 0.20
        l = o - 0.10
    else:
        o = coil_center
        c = coil_center - 4.0
        h = o + 0.10
        l = c - 0.20

    breakout_vol = 60 if low_volume_breakout else 400
    rows.append({"time": t0 + timedelta(minutes=15 * idx), "open": o, "high": h, "low": l,
                 "close": c, "tick_volume": breakout_vol})
    idx += 1
    # Unused still-forming bar
    rows.append({"time": t0 + timedelta(minutes=15 * idx), "open": c, "high": c + 0.05,
                 "low": c - 0.05, "close": c, "tick_volume": 50})
    return pd.DataFrame(rows)


def _make_h1_df(trend="flat", step=0.05):
    """Build a synthetic H1 DataFrame with a steady EMA50 slope in the given direction."""
    rows = []
    t0 = datetime(2026, 9, 10, 0, 0, 0)
    price = 2695.0
    for i in range(60):
        if trend == "up":
            price += step
        elif trend == "down":
            price -= step
        rows.append({"time": t0 + timedelta(hours=i), "open": price - 0.05, "high": price + 0.1,
                     "low": price - 0.1, "close": price})
    return pd.DataFrame(rows)


class TestConfluenceSqueezeM15(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.config = {
            "mt5": {"symbol": "XAUUSDc", "magic_number": 555888},
            "strategy": {
                "risk_percent": 1.0,
                "strategy_mode": "ALL",
            }
        }
        self.bot = BotEngine(self.mock_connector, self.config)
        self.bot.get_current_session = MagicMock(return_value="LONDON SESSION")

    def _wire_rates(self, m15_df, h1_df=None):
        h1_df = h1_df if h1_df is not None else _make_h1_df("flat")

        def _side_effect(symbol, tf, n):
            if tf == "H1":
                return h1_df
            return m15_df
        self.mock_connector.get_rates.side_effect = _side_effect

    # ---------------------------------------------------------------
    # Registration
    # ---------------------------------------------------------------
    def test_confluence_squeeze_magic_registered(self):
        """Test CONFLUENCE_SQUEEZE_M15 has isolated, non-colliding magic numbers registered."""
        self.assertIn("CONFLUENCE_SQUEEZE_M15", STRATEGY_MAGIC_MAP)
        magic_info = STRATEGY_MAGIC_MAP["CONFLUENCE_SQUEEZE_M15"]
        for key in ["base", "pos1", "pos2", "pos3"]:
            self.assertIn(key, magic_info)
        self.assertEqual(magic_info["base"], 555950)
        all_magics = set()
        for k, m in STRATEGY_MAGIC_MAP.items():
            if k == "CONFLUENCE_SQUEEZE_M15":
                continue
            all_magics.update([m["base"], m["pos1"], m["pos2"], m["pos3"]])
        for v in magic_info.values():
            self.assertNotIn(v, all_magics)
        self.assertEqual(len(STRATEGY_MAGIC_MAP), 6)

    def test_confluence_squeeze_registered_in_optimizer(self):
        """Test CONFLUENCE_SQUEEZE_M15 has a SETUP_PROFILES entry and is part of DEFAULT_STRATEGIES."""
        self.assertIn("CONFLUENCE_SQUEEZE_M15", SETUP_PROFILES)
        self.assertIn("CONFLUENCE_SQUEEZE_M15", DEFAULT_STRATEGIES)
        profile = SETUP_PROFILES["CONFLUENCE_SQUEEZE_M15"]
        self.assertGreaterEqual(profile["base_rr"], 1.5)

    def test_confluence_squeeze_registered_in_analytics(self):
        """Test StrategyAnalyticsManager has CONFLUENCE_SQUEEZE_M15 registered with its magic block."""
        analytics = StrategyAnalyticsManager()
        self.assertIn("CONFLUENCE_SQUEEZE_M15", analytics.STRATEGY_REGISTRY)
        entry = analytics.STRATEGY_REGISTRY["CONFLUENCE_SQUEEZE_M15"]
        self.assertEqual(entry["magic_numbers"], [555950, 555951, 555952, 555953])
        for m in entry["magic_numbers"]:
            self.assertIn(m, analytics.ELITE_MAGIC_NUMBERS)

    # ---------------------------------------------------------------
    # Confluence Detection
    # ---------------------------------------------------------------
    def test_squeeze_breakout_buy_signal(self):
        """Test a genuine squeeze -> expansion breakout produces a BUY signal."""
        df = _make_squeeze_df("BUY")
        self._wire_rates(df, _make_h1_df("flat"))
        b_sig, s_sig, reason = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertTrue(b_sig)
        self.assertFalse(s_sig)
        self.assertIn("Confluence Squeeze Breakout (BUY)", reason)

    def test_squeeze_breakout_sell_signal(self):
        """Test a genuine squeeze -> expansion breakdown produces a SELL signal."""
        df = _make_squeeze_df("SELL")
        self._wire_rates(df, _make_h1_df("flat"))
        b_sig, s_sig, reason = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig)
        self.assertTrue(s_sig)
        self.assertIn("Confluence Squeeze Breakout (SELL)", reason)

    def test_no_squeeze_blocks_signal(self):
        """Test a breakout candle with NO preceding volatility compression produces no signal."""
        df = _make_squeeze_df("BUY", no_squeeze=True)
        self._wire_rates(df, _make_h1_df("flat"))
        b_sig, s_sig, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig)
        self.assertFalse(s_sig)

    def test_low_volume_breakout_blocks_signal(self):
        """Test a squeeze breakout candle with below-average volume is filtered out."""
        df = _make_squeeze_df("BUY", low_volume_breakout=True)
        self._wire_rates(df, _make_h1_df("flat"))
        b_sig, s_sig, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig)
        self.assertFalse(s_sig)

    def test_asian_session_blocks_signal(self):
        """Test the setup does not fire outside London/NY sessions."""
        self.bot.get_current_session = MagicMock(return_value="ASIAN SESSION")
        df = _make_squeeze_df("BUY")
        self._wire_rates(df, _make_h1_df("flat"))
        b_sig, s_sig, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig)
        self.assertFalse(s_sig)

    def test_h1_strong_downtrend_blocks_buy_breakout(self):
        """Test a BUY breakout is blocked when the H1 trend is strongly bearish."""
        df = _make_squeeze_df("BUY")
        self._wire_rates(df, _make_h1_df("down", step=0.6))
        b_sig, s_sig, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig)
        self.assertFalse(s_sig)

    def test_h1_strong_uptrend_blocks_sell_breakout(self):
        """Test a SELL breakdown is blocked when the H1 trend is strongly bullish."""
        df = _make_squeeze_df("SELL")
        self._wire_rates(df, _make_h1_df("up", step=0.6))
        b_sig, s_sig, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig)
        self.assertFalse(s_sig)

    def test_bar_lock_prevents_re_fire_on_same_closed_bar(self):
        """Test the M15 bar-lock prevents re-evaluating the same closed breakout candle twice."""
        df = _make_squeeze_df("BUY")
        self._wire_rates(df, _make_h1_df("flat"))
        b_sig1, _, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertTrue(b_sig1)
        b_sig2, s_sig2, _ = self.bot._check_confluence_squeeze_m15("XAUUSDc")
        self.assertFalse(b_sig2)
        self.assertFalse(s_sig2)

    # ---------------------------------------------------------------
    # Risk Sizing (0.5% Fixed)
    # ---------------------------------------------------------------
    def test_confluence_squeeze_uses_fixed_half_percent_lot_sizing(self):
        """Test calculate_lot_size applies a dedicated Fixed 0.5% risk branch for CONFLUENCE_SQUEEZE_M15."""
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        lot = self.bot.calculate_lot_size(2.00, strat_id="CONFLUENCE_SQUEEZE_M15")
        # 10000 * 0.5% = 50 risk USD; 50 / (2.00 * 100) = 0.25 lot
        self.assertAlmostEqual(lot, 0.25, places=2)

    # ---------------------------------------------------------------
    # Full AI Gating (MarketRegimeScorer quality filter + RealTimeStrategyOptimizer throttle)
    # ---------------------------------------------------------------
    def test_confluence_squeeze_blocked_by_quality_filter(self):
        """Test CONFLUENCE_SQUEEZE_M15 is blocked by the MarketRegimeScorer quality filter (Full AI Gating)."""
        dummy_df = pd.DataFrame({'close': [2700.0] * 20, 'low': [2695.0] * 20, 'high': [2705.0] * 20})
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.bot.scorer.evaluate_market_confluence = MagicMock(return_value={
            "is_allowed": False, "score": 38, "grade": "D",
            "pillars": {"volume": {"desc": "Low Volume Filter"}}
        })
        self.bot._process_single_setup_signal(dummy_df, "XAUUSDc", 20.0, "CONFLUENCE_SQUEEZE_M15", "BUY", "Test Squeeze Signal")
        self.assertEqual(self.mock_connector.open_order.call_count, 0)

    def test_confluence_squeeze_blocked_by_ai_loss_streak_cooldown(self):
        """Test CONFLUENCE_SQUEEZE_M15 is blocked when RealTimeStrategyOptimizer signals should_execute=False (Full AI Gating)."""
        dummy_df = pd.DataFrame({'close': [2700.0] * 20, 'low': [2695.0] * 20, 'high': [2705.0] * 20})
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.bot.scorer.evaluate_market_confluence = MagicMock(return_value={
            "is_allowed": True, "score": 81, "grade": "A", "lot_recommendation": 1.0,
            "pillars": {"volume": {"desc": "OK"}}
        })
        self.bot.optimizer.get_dynamic_rr_and_parameters = MagicMock(return_value={
            "should_execute": False, "reason": "AI Loss Cooldown (CONFLUENCE_SQUEEZE_M15): -3 Consecutive Losses"
        })
        self.bot._process_single_setup_signal(dummy_df, "XAUUSDc", 20.0, "CONFLUENCE_SQUEEZE_M15", "BUY", "Test Squeeze Signal")
        self.assertEqual(self.mock_connector.open_order.call_count, 0)

    def test_confluence_squeeze_executes_when_ai_gate_allows(self):
        """Test CONFLUENCE_SQUEEZE_M15 places exactly 1 order under its own magic when both AI gates pass."""
        dummy_df = pd.DataFrame({
            'close': [2700.0] * 20, 'low': [2695.0] * 20, 'high': [2705.0] * 20, 'open': [2699.5] * 20
        })
        self.mock_connector.get_market_info.return_value = {"ask": 2700.0, "bid": 2699.8, "spread": 20.0}
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.mock_connector.get_rates.side_effect = None
        self.mock_connector.get_rates.return_value = pd.DataFrame({
            'time': [datetime.now()] * 10,
            'open': [2698.0] * 10, 'high': [2699.0] * 10, 'low': [2697.0] * 10, 'close': [2698.5] * 10
        })
        self.mock_connector.open_order.return_value = {"ticket": 55951}
        self.bot.scorer.evaluate_market_confluence = MagicMock(return_value={
            "is_allowed": True, "score": 79, "grade": "A", "lot_recommendation": 1.0,
            "pillars": {"volume": {"desc": "OK"}}
        })
        self.bot.optimizer.get_dynamic_rr_and_parameters = MagicMock(return_value={
            "should_execute": True, "lot_multiplier": 1.0, "atr_sl_multiplier": 1.0, "tp_ratio": 2.0
        })
        self.bot._process_single_setup_signal(dummy_df, "XAUUSDc", 20.0, "CONFLUENCE_SQUEEZE_M15", "BUY", "Test Squeeze Signal")

        self.assertEqual(self.mock_connector.open_order.call_count, 1)
        args, _ = self.mock_connector.open_order.call_args
        self.assertEqual(args[0], "XAUUSDc")
        self.assertEqual(args[1], "BUY")
        self.assertEqual(args[5], STRATEGY_MAGIC_MAP["CONFLUENCE_SQUEEZE_M15"]["pos1"])

    # ---------------------------------------------------------------
    # Exit Behavior
    # ---------------------------------------------------------------
    def test_confluence_squeeze_uses_trend_trail_runner(self):
        """Test should_run_trend classifies CONFLUENCE_SQUEEZE_M15 as a trailing trend-runner (not Fixed TP)."""
        dummy_df = pd.DataFrame({'close': [2700.0] * 20})
        should_trail, label = self.bot.should_run_trend("CONFLUENCE_SQUEEZE_M15", dummy_df, "LONDON SESSION")
        self.assertTrue(should_trail)
        self.assertIn("Confluence Squeeze", label)

    def test_confluence_squeeze_break_even_lock_at_one_r(self):
        """Test manage_open_positions locks SL to Break-Even once CONFLUENCE_SQUEEZE_M15 reaches 1.0R profit."""
        magic = STRATEGY_MAGIC_MAP["CONFLUENCE_SQUEEZE_M15"]["pos1"]
        self.mock_connector.get_market_info.return_value = {"bid": 2702.0, "ask": 2702.2}
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 601, "magic": magic, "symbol": "XAUUSDc", "type": "BUY",
             "price_open": 2700.0, "sl": 0.0, "tp": 2704.0}
        ]
        self.bot.initial_risk_map[601] = 2.0  # 1.0R profit at bid = 2702.0
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(601, 2700.30, 2704.0)

    def test_confluence_squeeze_profit_lock_at_1_6r(self):
        """Test manage_open_positions locks +0.9R profit once CONFLUENCE_SQUEEZE_M15 reaches 1.6R."""
        magic = STRATEGY_MAGIC_MAP["CONFLUENCE_SQUEEZE_M15"]["pos1"]
        self.mock_connector.get_market_info.return_value = {"bid": 2703.30, "ask": 2703.50}
        self.mock_connector.get_open_positions.return_value = [
            {"ticket": 602, "magic": magic, "symbol": "XAUUSDc", "type": "BUY",
             "price_open": 2700.0, "sl": 2700.30, "tp": 2704.0}
        ]
        self.bot.initial_risk_map[602] = 2.0  # 1.65R profit at bid = 2703.30 (safely clears the 1.6R threshold)
        self.bot.manage_open_positions("XAUUSDc")
        self.mock_connector.modify_position.assert_called_with(602, 2701.80, 2704.0)

    # ---------------------------------------------------------------
    # Analytics Classification
    # ---------------------------------------------------------------
    def test_deal_classification_for_confluence_squeeze(self):
        """Test closed deals with CONFLUENCE_SQUEEZE_M15 magics/comments classify correctly, others fall to RETIRED_SETUPS."""
        analytics = StrategyAnalyticsManager()

        deal = MagicMock()
        deal.magic = 555951
        deal.comment = "Gold_CONFLUEN"
        self.assertEqual(analytics._classify_deal_strategy(deal), "CONFLUENCE_SQUEEZE_M15")

        unrelated_deal = MagicMock()
        unrelated_deal.magic = 999999
        unrelated_deal.comment = "Manual Trade"
        self.assertEqual(analytics._classify_deal_strategy(unrelated_deal), "RETIRED_SETUPS")


if __name__ == "__main__":
    unittest.main()