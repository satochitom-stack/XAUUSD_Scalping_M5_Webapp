import os
import unittest
from exit_benchmark_tracker import ExitBenchmarkTracker, MULTI_TP_PROFILES

class TestExitBenchmarkTracker(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_exit_bench_suite.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.tracker = ExitBenchmarkTracker(data_file_path=self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_multi_tp_profiles_count(self):
        self.assertEqual(len(MULTI_TP_PROFILES), 8)
        self.assertIn("NEWS_MOMENTUM_EXPANSION", MULTI_TP_PROFILES)
        self.assertIn("ASIAN_RANGE_SNIPER", MULTI_TP_PROFILES)
        self.assertIn("SMC_SWEEP", MULTI_TP_PROFILES)

    def test_buy_trade_progression_tp3(self):
        self.tracker.register_trade(
            primary_ticket=1001,
            runner_ticket=1002,
            symbol="XAUUSDc",
            order_type="BUY",
            open_price=2500.0,
            sl_price=2498.0,
            total_lot=0.10,
            strategy_id="SMC_SWEEP"
        )
        trade = self.tracker.active_shadow_trades["1001"]
        mtp = trade["multi_tp"]
        self.assertEqual(mtp["tp1_price"], 2503.0)
        self.assertEqual(mtp["tp2_price"], 2505.0)
        self.assertEqual(mtp["tp3_price"], 2507.0)

        # Bar 1: TP1 Hit
        self.tracker.update_price("XAUUSDc", high=2503.5, low=2499.5, bid=2503.2, ask=2503.4)
        self.assertTrue(mtp["tp1_hit"])
        self.assertEqual(mtp["virtual_sl"], 2500.0)

        # Bar 2: TP2 Hit
        self.tracker.update_price("XAUUSDc", high=2505.5, low=2501.0, bid=2505.2, ask=2505.4)
        self.assertTrue(mtp["tp2_hit"])
        self.assertEqual(mtp["virtual_sl"], 2503.0)

        # Bar 3: TP3 Hit
        self.tracker.update_price("XAUUSDc", high=2507.5, low=2504.0, bid=2507.2, ask=2507.4)
        self.assertTrue(mtp["tp3_hit"])
        self.assertTrue(mtp["closed"])
        self.assertGreater(mtp["profit"], 0.0)

    def test_sell_trade_progression_sl_hit(self):
        self.tracker.register_trade(
            primary_ticket=2001,
            runner_ticket=2002,
            symbol="XAUUSDc",
            order_type="SELL",
            open_price=2500.0,
            sl_price=2502.0,
            total_lot=0.10,
            strategy_id="ASIAN_RANGE_SNIPER"
        )
        trade = self.tracker.active_shadow_trades["2001"]
        mtp = trade["multi_tp"]
        
        # Bar 1: Hits SL at 2502.5
        self.tracker.update_price("XAUUSDc", high=2502.5, low=2499.5, bid=2502.0, ask=2502.2)
        self.assertTrue(mtp["closed"])
        self.assertEqual(mtp["closed_reason"], "SL_OR_BE_HIT")
        self.assertLess(mtp["profit"], 0.0)

    def test_benchmark_summary_and_leader(self):
        self.tracker.register_trade(3001, 3002, "XAUUSDc", "BUY", 2500.0, 2498.0, 0.10, "SMC_SWEEP")
        self.tracker.update_price("XAUUSDc", 2507.5, 2499.0, 2507.0, 2507.2)
        self.tracker.on_trade_closed(3001, 15.0, "TP1")
        self.tracker.on_trade_closed(3002, 20.0, "Trailing")

        summary = self.tracker.get_benchmark_summary()
        self.assertEqual(summary["total_benchmark_trades"], 1)
        self.assertIn("comparison", summary)
        self.assertIn("leader", summary["comparison"])
        self.assertIn("SMC_SWEEP", summary["strategy_breakdown"])

if __name__ == "__main__":
    unittest.main()
