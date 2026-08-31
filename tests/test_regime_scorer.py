import os
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from regime_liquidity_scorer import MarketRegimeScorer

class TestMarketRegimeScorer(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_regime_scorer_suite.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.scorer = MarketRegimeScorer(data_file_path=self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def _create_mock_df(self, count=30, vol_mult=1.0, atr=2.5):
        data = []
        base_price = 2500.0
        for i in range(count):
            vol = 1000 * (vol_mult if i == count - 1 else 1.0)
            data.append({
                "time": f"2026-08-31 10:{i:02d}:00",
                "open": base_price + i * 0.1,
                "high": base_price + i * 0.1 + atr,
                "low": base_price + i * 0.1 - atr,
                "close": base_price + i * 0.1 + 0.05,
                "tick_volume": vol
            })
        return pd.DataFrame(data)

    def test_prime_confluence_generates_grade_a_plus(self):
        # 14:30 London session, 1.8x volume surge, healthy ATR 3.0, tight spread 12 pts
        df = self._create_mock_df(count=30, vol_mult=1.8, atr=3.0)
        eval_time = datetime(2026, 8, 31, 10, 30) # London Session (08:00 - 13:00 Server Time)
        res = self.scorer.evaluate_market_confluence(df, current_spread=12.0, setup_id="SMC_SWEEP", server_time=eval_time)
        
        self.assertGreaterEqual(res["score"], 85)
        self.assertEqual(res["grade"], "A+")
        self.assertTrue(res["is_allowed"])
        self.assertEqual(res["pillars"]["session"]["score"], 25)
        self.assertEqual(res["pillars"]["volume"]["score"], 25)
        self.assertEqual(res["pillars"]["spread"]["score"], 25)

    def test_rollover_illiquid_generates_grade_c_and_blocks(self):
        # 22:30 Rollover Deadzone, 0.4x thin volume, low ATR, widened spread 48 pts
        df = self._create_mock_df(count=30, vol_mult=0.4, atr=0.5)
        eval_time = datetime(2026, 8, 31, 22, 30) # Rollover Deadzone
        res = self.scorer.evaluate_market_confluence(df, current_spread=48.0, setup_id="EMA50_3CANDLES_H1", server_time=eval_time)
        
        self.assertLess(res["score"], 55)
        self.assertEqual(res["grade"], "C")
        self.assertFalse(res["is_allowed"])

    def test_asian_range_sniper_rewards_asian_session(self):
        # 04:00 Asian Session, normal volume, calm ATR 1.5
        df = self._create_mock_df(count=30, vol_mult=1.1, atr=1.5)
        eval_time = datetime(2026, 8, 31, 4, 0)
        res = self.scorer.evaluate_market_confluence(df, current_spread=14.0, setup_id="ASIAN_RANGE_SNIPER", server_time=eval_time)
        
        self.assertEqual(res["pillars"]["session"]["score"], 25)
        self.assertEqual(res["pillars"]["trend"]["score"], 25) # Asian sniper rewards tight ATR
        self.assertGreaterEqual(res["score"], 70)
        self.assertTrue(res["is_allowed"])

    def test_record_filtered_trade_saves_counter(self):
        self.assertEqual(self.scorer.saved_junk_trades, 0)
        mock_res = {"score": 42, "grade": "C", "pillars": {"volume": {"desc": "Low volume"}}}
        self.scorer.record_filtered_trade("SMC_SWEEP", mock_res)
        
        self.assertEqual(self.scorer.saved_junk_trades, 1)
        self.assertEqual(len(self.scorer.recent_evaluations), 1)

if __name__ == "__main__":
    unittest.main()
