"""
Hourly Winrate & Session Heatmap Intelligence Engine for XAUUSD Scalping
Tracks hourly trade distribution and adapts confidence weights across 24-hour UTC+7 trading sessions.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Tuple

logger = logging.getLogger("HourlyHeatEngine")

class HourlyHeatEngine:
    """
    Tracks and learns the winrate and profit distribution across each 24-hour UTC+7 window.
    Provides dynamic confidence weights (e.g. 1.15x for Peak Session Kill Zones, 0.85x for Slow Roll Hours).
    """
    def __init__(self, data_file: str = "hourly_learning_data.json"):
        # Put data file in same directory or persistent path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_file = os.path.join(base_dir, data_file)
        self.hourly_stats = self.load_stats()

    def load_stats(self) -> Dict[str, dict]:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading hourly learning data: {e}")
        return self._get_default_stats()

    def _get_default_stats(self) -> Dict[str, dict]:
        stats = {}
        for h in range(24):
            h_str = f"{h:02d}"
            # Asian: 07-13, London: 14-18, NY: 19-23, Rollover/Dead: 04-06 (UTC+7)
            if 14 <= h <= 17 or 19 <= h <= 22:
                base_w = 1.15
                desc = "🔥 Peak Institutional Volume (Kill Zone)"
            elif 4 <= h <= 6:
                base_w = 0.85
                desc = "💤 Low Liquidity Rollover"
            elif 7 <= h <= 13:
                base_w = 1.05
                desc = "⛩️ Asian Range Session"
            else:
                base_w = 1.00
                desc = "⚖️ Normal Trading Session"
            stats[h_str] = {
                "hour": h,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0.0,
                "winrate": 75.0,
                "weight_multiplier": base_w,
                "desc": desc
            }
        return stats

    def record_outcome(self, trade_time: datetime, profit: float):
        """Record completed trade outcome for the specific hour."""
        try:
            h_str = f"{trade_time.hour:02d}"
            if h_str not in self.hourly_stats:
                self.hourly_stats[h_str] = {
                    "hour": trade_time.hour,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "profit": 0.0,
                    "winrate": 75.0,
                    "weight_multiplier": 1.0,
                    "desc": "Active Hour"
                }
            stat = self.hourly_stats[h_str]
            stat["trades"] += 1
            stat["profit"] = round(stat["profit"] + profit, 2)
            if profit > 0:
                stat["wins"] += 1
            else:
                stat["losses"] += 1
            stat["winrate"] = round((stat["wins"] / stat["trades"]) * 100.0, 1)

            # Dynamic weight adjustment based on actual sample size
            if stat["trades"] >= 3:
                if stat["winrate"] >= 75.0:
                    stat["weight_multiplier"] = 1.20
                    stat["desc"] = f"🔥 High-Winrate Hot Zone ({stat['winrate']}%)"
                elif stat["winrate"] >= 60.0:
                    stat["weight_multiplier"] = 1.05
                    stat["desc"] = f"🟢 Solid Trading Zone ({stat['winrate']}%)"
                elif stat["winrate"] < 50.0:
                    stat["weight_multiplier"] = 0.80
                    stat["desc"] = f"⚠️ Low-Efficiency Zone ({stat['winrate']}%)"
                else:
                    stat["weight_multiplier"] = 1.00

            self.save_stats()
        except Exception as e:
            logger.error(f"Error in record_outcome for hourly heatmap: {e}")

    def get_hour_multiplier(self, hour: int) -> Tuple[float, str]:
        """Return confidence multiplier and descriptor for the current hour."""
        h_str = f"{hour:02d}"
        stat = self.hourly_stats.get(h_str, {"weight_multiplier": 1.0, "desc": "Normal Trading Session"})
        return stat.get("weight_multiplier", 1.0), stat.get("desc", "Normal Trading Session")

    def get_all_heatmap_data(self) -> list:
        """Return list of 24 hourly stats for Web Dashboard rendering."""
        return [self.hourly_stats.get(f"{h:02d}", {}) for h in range(24)]

    def save_stats(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.hourly_stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving hourly learning stats: {e}")
