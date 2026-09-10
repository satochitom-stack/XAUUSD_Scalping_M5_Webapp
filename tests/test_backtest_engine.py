"""
Integration test for backtest_engine.py.

Runs the actual walk-forward backtester (via CSV data, no network / no MT5 terminal
required) over a short synthetic random-walk window and checks that:
  1. It completes without raising, and produces a well-formed results dict covering
     all 5 active pillars.
  2. It never touches the LIVE production state files (strategy_learning_data.json,
     regime_scorer_stats.json, exit_benchmark_history.json) - all optimizer/scorer/
     benchmark-tracker state must be isolated to backtest_engine.py's own scratch dir.

This is a slower integration-style test (several seconds) since it drives the real
bot_engine.GoldScalpingBot end-to-end through run_iteration() for several hundred
simulated bars; kept short deliberately to stay reasonably fast.
"""

import os
import unittest
import numpy as np
import pandas as pd

import backtest_engine
from bot_engine import STRATEGY_MAGIC_MAP

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_STATE_FILES = [
    os.path.join(REPO_ROOT, "strategy_learning_data.json"),
    os.path.join(REPO_ROOT, "regime_scorer_stats.json"),
    os.path.join(REPO_ROOT, "exit_benchmark_history.json"),
]


def _make_synthetic_m5_csv(path: str, n: int = 700, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-06-01 00:00:00", periods=n, freq="5min")
    price = 2650.0
    rows = []
    for _ in range(n):
        o = price
        c = o + rng.normal(0, 0.35)
        h = max(o, c) + abs(rng.normal(0, 0.25))
        l = min(o, c) - abs(rng.normal(0, 0.25))
        rows.append((o, h, l, c, int(rng.uniform(50, 300))))
        price = c
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "tick_volume"])
    df.insert(0, "time", times)
    df.to_csv(path, index=False)


import tempfile

class TestBacktestEngine(unittest.TestCase):
    def setUp(self):
        self.csv_path = os.path.join(tempfile.gettempdir(), "test_backtest_engine_synthetic_m5.csv")
        _make_synthetic_m5_csv(self.csv_path, n=700)
        self._pre_run_mtimes = {
            p: (os.path.getmtime(p) if os.path.exists(p) else None) for p in LIVE_STATE_FILES
        }

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def test_csv_loader_normalizes_columns(self):
        df = backtest_engine.load_ohlc_csv(self.csv_path)
        for col in ["time", "open", "high", "low", "close", "tick_volume"]:
            self.assertIn(col, df.columns)
        self.assertGreater(len(df), 0)
        self.assertTrue(df["time"].is_monotonic_increasing)

    def test_resample_ohlc_produces_valid_m15(self):
        m5 = backtest_engine.load_ohlc_csv(self.csv_path)
        m15 = backtest_engine.resample_ohlc(m5, "15min")
        self.assertLess(len(m15), len(m5))
        for col in ["time", "open", "high", "low", "close"]:
            self.assertIn(col, m15.columns)

    def test_full_backtest_run_produces_well_formed_results(self):
        bt = backtest_engine.HistoricalBacktester(symbol="XAUUSDc", initial_balance=3000.0, spread_points=20.0)
        bt.load_from_csv(self.csv_path)
        results = bt.run(warmup_bars=260, progress_every=0)

        for key in ["symbol", "initial_balance", "final_balance", "net_profit_usd",
                    "total_trades", "winrate_pct", "strategy_breakdown", "assumptions"]:
            self.assertIn(key, results)

        self.assertEqual(results["initial_balance"], 3000.0)
        self.assertIsInstance(results["final_balance"], float)
        # All 5 active pillars must appear in the breakdown even with 0 trades
        for strat_id in STRATEGY_MAGIC_MAP:
            self.assertIn(strat_id, results["strategy_breakdown"])

        # Every closed trade's magic number must resolve to one of the 5 active pillars
        all_magics = set()
        for m in STRATEGY_MAGIC_MAP.values():
            all_magics.update([m["base"], m["pos1"], m["pos2"], m["pos3"]])
        for t in bt.connector.closed_trades:
            self.assertIn(t["magic"], all_magics)

    def test_backtest_never_touches_live_production_state_files(self):
        bt = backtest_engine.HistoricalBacktester(symbol="XAUUSDc", initial_balance=3000.0, spread_points=20.0)
        bt.load_from_csv(self.csv_path)
        bt.run(warmup_bars=260, progress_every=0)

        for p in LIVE_STATE_FILES:
            after = os.path.getmtime(p) if os.path.exists(p) else None
            self.assertEqual(
                self._pre_run_mtimes[p], after,
                f"Backtest run modified a LIVE production state file: {p}"
            )
        # The isolated scratch files should exist instead
        for name in ["bt_strategy_learning.json", "bt_regime_scorer_stats.json", "bt_exit_benchmark_history.json"]:
            self.assertTrue(os.path.exists(os.path.join(bt.scratch_dir, name)))


if __name__ == "__main__":
    unittest.main()
