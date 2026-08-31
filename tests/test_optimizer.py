"""
Automated Unit & Integration Test for Real-Time Strategy Learning Optimizer
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Add root dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_optimizer import RealTimeStrategyOptimizer

def generate_sample_candles(count=50, trend="BULLISH"):
    base_price = 2650.0
    records = []
    for i in range(count):
        if trend == "BULLISH":
            base_price += np.random.uniform(0.1, 0.8)
        elif trend == "BEARISH":
            base_price -= np.random.uniform(0.1, 0.8)
        else: # SIDEWAY
            base_price += np.random.uniform(-0.3, 0.3)

        high = base_price + np.random.uniform(0.2, 0.6)
        low = base_price - np.random.uniform(0.2, 0.6)
        open_p = low + np.random.uniform(0.1, 0.3)
        close_p = high - np.random.uniform(0.1, 0.3)

        records.append({
            "time": datetime.now(),
            "open": open_p,
            "high": high,
            "low": low,
            "close": close_p,
            "tick_volume": 100
        })
    return pd.DataFrame(records)

def test_market_regime_classification():
    print("Testing Market Regime Classification...")
    test_db = os.path.join(os.path.dirname(__file__), "test_temp_data.json")
    opt = RealTimeStrategyOptimizer(data_file_path=test_db)
    
    # Test Bullish Data
    bull_df = generate_sample_candles(60, "BULLISH")
    regime = opt.classify_market_regime(bull_df)
    print("Bullish Regime Output:", regime["label"], "| ATR:", regime["atr"])
    assert "regime" in regime
    assert regime["atr"] > 0

    # Test Sideway Data
    side_df = generate_sample_candles(60, "SIDEWAY")
    regime_side = opt.classify_market_regime(side_df)
    print("Sideway Regime Output:", regime_side["label"])
    assert "regime" in regime_side
    print("✅ Market Regime Classification passed.")

def test_dynamic_execution_and_learning():
    print("\nTesting Dynamic Execution & Learning Scorecard...")
    test_db = os.path.join(os.path.dirname(__file__), "test_temp_data.json")
    opt = RealTimeStrategyOptimizer(data_file_path=test_db)
    opt.reset_learning()

    # Initial state
    stats = opt.get_dashboard_summary()
    assert stats["enabled"] == True

    # Record consecutive wins for SMC_SWEEP
    opt.record_trade_outcome("SMC_SWEEP", 45.0, 15.0, "SMC Liquidity Sweep Low")
    opt.record_trade_outcome("SMC_SWEEP", 50.0, 16.0, "SMC Liquidity Sweep Low")
    opt.record_trade_outcome("SMC_SWEEP", 60.0, 20.0, "SMC Liquidity Sweep Low")

    smc_stat = opt.strategy_stats["SMC_SWEEP"]
    print(f"SMC Stats after 3 wins: Winrate = {smc_stat['winrate']}% | Streak = {smc_stat['streak']} | Weight = {smc_stat['weight']}x")
    assert smc_stat["wins"] == 3
    assert smc_stat["streak"] == 3
    assert smc_stat["weight"] >= 1.20

    # Calculate execution in Strong Bullish Trend
    dummy_regime = {
        "regime": "STRONG_BULLISH_TREND",
        "label": "🟢 Strong Bullish Trend",
        "atr": 3.0,
        "volatility_ratio": 1.1,
        "is_choppy": False,
        "recommended_strategies": ["EMA_RIBBON", "ALL_CONFLUENCE"]
    }
    # Calculate execution for SMC_SWEEP (Should have higher dynamic R:R due to base 1.60R + streak)
    smc_plan = opt.calculate_optimized_execution("SMC_SWEEP", 1.0, 150.0, dummy_regime)
    print("AI Optimized Execution Plan for SMC_SWEEP:", smc_plan)
    assert smc_plan["should_execute"] == True
    assert smc_plan["tp_ratio"] >= 1.60
    assert smc_plan["trailing_type"] == "TIGHT_LOCK"

    # Calculate execution for BB_SQUEEZE in High Volatility
    vol_regime = {
        "regime": "HIGH_VOLATILITY",
        "label": "⚡ High Volatility Breakout",
        "atr": 4.5,
        "volatility_ratio": 1.4,
        "is_choppy": False,
        "recommended_strategies": ["BB_SQUEEZE", "ALL_CONFLUENCE"]
    }
    bb_plan = opt.calculate_optimized_execution("BB_SQUEEZE", 1.0, 150.0, vol_regime)
    print("AI Optimized Execution Plan for BB_SQUEEZE in High Volatility:", bb_plan)
    assert bb_plan["tp_ratio"] >= 1.80
    assert bb_plan["trailing_type"] == "WIDE_ATR"

    print("✅ Dynamic Execution & Learning tests passed successfully!")

if __name__ == "__main__":
    test_market_regime_classification()
    test_dynamic_execution_and_learning()
