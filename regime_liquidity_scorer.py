"""
Market Regime & Liquidity Filter Score Engine (0-100 Institutional Confluence Quality Scorer)
Evaluates real-time market quality across 4 pillars before executing any trade:
1. Session & Time Confluence (0-25 pts)
2. Institutional Tick Volume & Flow (0-25 pts)
3. Volatility & Trend Power (ADX / ATR / Bandwidth) (0-25 pts)
4. Spread & Execution Safety (0-25 pts)
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("RegimeScorer")

class MarketRegimeScorer:
    """Evaluates market context and calculates institutional quality score (0-100)."""

    def __init__(self, data_file_path: Optional[str] = None):
        if data_file_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_file_path = os.path.join(base_dir, "regime_scorer_stats.json")
        self.data_file_path = data_file_path

        self.threshold = 70  # Default minimum score required for execution (Grade A/A+)
        self.is_enabled = True
        self.saved_junk_trades = 0
        self.recent_evaluations: List[dict] = []
        self._load_state()

    def _load_state(self):
        if os.path.exists(self.data_file_path):
            try:
                with open(self.data_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.threshold = data.get("threshold", 70)
                    self.is_enabled = data.get("is_enabled", True)
                    self.saved_junk_trades = data.get("saved_junk_trades", 0)
                    self.recent_evaluations = data.get("recent_evaluations", [])[-50:]
                    logger.info(f"Loaded Regime Scorer state: Threshold={self.threshold}, Saved Junk Trades={self.saved_junk_trades}")
            except Exception as e:
                logger.error(f"Error loading regime scorer data: {e}")

    def save_state(self):
        try:
            payload = {
                "threshold": self.threshold,
                "is_enabled": self.is_enabled,
                "saved_junk_trades": self.saved_junk_trades,
                "last_updated": datetime.now().isoformat(),
                "recent_evaluations": self.recent_evaluations[-50:]
            }
            with open(self.data_file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save regime scorer data: {e}")

    def evaluate_market_confluence(self, df: pd.DataFrame, current_spread: float, setup_id: str, 
                                   server_time: Optional[datetime] = None) -> dict:
        """Calculate real-time 0-100 Confluence Quality Score."""
        now = server_time or datetime.now()
        current_time = now.time()

        # ==========================================
        # 1. Session & Time Pillar (0 - 25 pts)
        # ==========================================
        session_score = 15
        session_name = "REGULAR SESSION"
        session_desc = "Normal Market Liquidity"

        # Asian Session (00:00 - 08:00 Server Time)
        if dtime(0, 0) <= current_time < dtime(8, 0):
            session_name = "ASIAN SESSION"
            if setup_id == "ASIAN_RANGE_SNIPER":
                session_score = 25
                session_desc = "Peak Asian Range Prime Timing (Ideal)"
            else:
                session_score = 15
                session_desc = "Moderate Asian Liquidity"

        # London Session (08:00 - 13:00 Server Time / ~14:00 - 18:00 TH)
        elif dtime(8, 0) <= current_time < dtime(13, 0):
            session_name = "LONDON SESSION"
            session_score = 25
            session_desc = "High European Institutional Liquidity Flow"

        # NY / London Overlap (13:00 - 17:00 Server Time / ~19:00 - 23:00 TH)
        elif dtime(13, 0) <= current_time < dtime(17, 0):
            session_name = "NY / LONDON OVERLAP"
            session_score = 25
            session_desc = "Maximum Global Liquidity & High Momentum"

        # Late NY Session (17:00 - 21:00 Server Time)
        elif dtime(17, 0) <= current_time < dtime(21, 0):
            session_name = "LATE NY SESSION"
            session_score = 18
            session_desc = "Moderate US Afternoon Liquidity"

        # Midnight Rollover Deadzone (21:00 - 23:59 Server Time)
        else:
            session_name = "ROLLOVER / DEADZONE"
            session_score = 5
            session_desc = "Low Liquidity / Widened Spreads Warning"

        # ==========================================
        # 2. Institutional Tick Volume Pillar (0 - 25 pts)
        # ==========================================
        volume_score = 15
        vol_ratio = 1.0
        vol_desc = "Normal Average Volume"

        if not df.empty and 'tick_volume' in df.columns and len(df) >= 20:
            current_vol = float(df['tick_volume'].iloc[-1])
            avg_vol_20 = float(df['tick_volume'].iloc[-21:-1].mean())
            if avg_vol_20 > 0:
                vol_ratio = round(current_vol / avg_vol_20, 2)

            if vol_ratio >= 1.60:
                volume_score = 25
                vol_desc = f"Institutional Volume Surge ({vol_ratio}x avg)"
            elif vol_ratio >= 1.20:
                volume_score = 22
                vol_desc = f"Healthy Above-Average Volume ({vol_ratio}x avg)"
            elif vol_ratio >= 0.85:
                volume_score = 16
                vol_desc = f"Normal Baseline Volume ({vol_ratio}x avg)"
            elif vol_ratio >= 0.60:
                volume_score = 8
                vol_desc = f"Thin / Weak Volume Drift ({vol_ratio}x avg)"
            else:
                volume_score = 2
                vol_desc = f"Extremely Dry / Illiquid ({vol_ratio}x avg)"

        # ==========================================
        # 3. Volatility & Trend Power Pillar (0 - 25 pts)
        # ==========================================
        trend_score = 15
        trend_desc = "Moderate Market Movement"
        adx_val = 20.0

        if not df.empty and len(df) >= 15:
            # Approximate ADX / ATR Trend Strength
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            
            # Simple True Range calculation
            tr = np.maximum(highs[1:] - lows[1:], np.abs(highs[1:] - closes[:-1]))
            tr = np.maximum(tr, np.abs(lows[1:] - closes[:-1]))
            atr_14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else 2.0
            
            # Setup specific trend evaluation
            if setup_id == "ASIAN_RANGE_SNIPER":
                # Asian range sniper prefers calm, tight ranges
                if atr_14 <= 3.0:
                    trend_score = 25
                    trend_desc = f"Calm Mean-Reverting Range (ATR: {atr_14:.2f})"
                else:
                    trend_score = 15
                    trend_desc = f"Elevated Asian Range (ATR: {atr_14:.2f})"
            elif setup_id == "FLASH_MICRO_SCALPER":
                if atr_14 >= 1.0:
                    trend_score = 25
                    trend_desc = f"Optimal Micro-Volatility for Flash Scalp (ATR: {atr_14:.2f})"
                else:
                    trend_score = 16
                    trend_desc = f"Subdued Micro-Volatility (ATR: {atr_14:.2f})"
            elif setup_id == "M1_SNIPER_CONFIRMATION":
                if 1.0 <= atr_14 <= 4.5:
                    trend_score = 25
                    trend_desc = f"Ideal Zone Volatility for M1 Refinement (ATR: {atr_14:.2f})"
                else:
                    trend_score = 18
                    trend_desc = f"M1 Volatility Adequate (ATR: {atr_14:.2f})"
            elif setup_id == "BB_SQUEEZE":
                # BB Squeeze prefers compression transitioning into expansion
                trend_score = 23
                trend_desc = f"Volatility Squeeze Compression (ATR: {atr_14:.2f})"
            else:
                # Trend following setups (EMA50, SMC, Ribbon, News)
                if atr_14 >= 2.50:
                    trend_score = 25
                    trend_desc = f"Strong Dynamic Trend Flow (ATR: {atr_14:.2f})"
                elif atr_14 >= 1.50:
                    trend_score = 20
                    trend_desc = f"Healthy Trend Expansion (ATR: {atr_14:.2f})"
                else:
                    trend_score = 10
                    trend_desc = f"Low Volatility / Stagnant (ATR: {atr_14:.2f})"

        # ==========================================
        # 4. Spread & Execution Safety Pillar (0 - 25 pts)
        # ==========================================
        spread_score = 20
        spread_desc = f"Spread {current_spread:.1f} pts"

        if current_spread <= 15.0:
            spread_score = 25
            spread_desc = f"Super Tight Spread ({current_spread:.1f} pts)"
        elif current_spread <= 25.0:
            spread_score = 22
            spread_desc = f"Good Execution Spread ({current_spread:.1f} pts)"
        elif current_spread <= 35.0:
            spread_score = 14
            spread_desc = f"Acceptable Spread ({current_spread:.1f} pts)"
        elif current_spread <= 45.0:
            spread_score = 5
            spread_desc = f"Widened Spread Alert ({current_spread:.1f} pts)"
        else:
            spread_score = 0
            spread_desc = f"Dangerous Widened Spread ({current_spread:.1f} pts)"

        # ==========================================
        # Total Confluence Score & Grading
        # ==========================================
        total_score = min(100, max(0, session_score + volume_score + trend_score + spread_score))

        if total_score >= 85:
            grade = "A+"
            grade_color = "emerald"
            grade_title = "🌟 Institutional A+ Prime Setup (Highest Conviction)"
            lot_recommendation = 1.15
        elif total_score >= 70:
            grade = "A"
            grade_color = "gold"
            grade_title = "✅ High Quality Confluence (Standard Execution)"
            lot_recommendation = 1.00
        elif total_score >= 55:
            grade = "B"
            grade_color = "amber"
            grade_title = "⚠️ Marginal Quality / Lower Momentum (Cautious)"
            lot_recommendation = 0.50
        else:
            grade = "C"
            grade_color = "rose"
            grade_title = "🚫 Low Quality / Illiquid Junk Signal (Reject/Protect)"
            lot_recommendation = 0.00

        is_allowed = (total_score >= self.threshold) if self.is_enabled else True

        result = {
            "score": total_score,
            "grade": grade,
            "grade_color": grade_color,
            "grade_title": grade_title,
            "is_allowed": is_allowed,
            "threshold": self.threshold,
            "is_enabled": self.is_enabled,
            "lot_recommendation": lot_recommendation,
            "pillars": {
                "session": {
                    "score": session_score,
                    "max": 25,
                    "name": session_name,
                    "desc": session_desc
                },
                "volume": {
                    "score": volume_score,
                    "max": 25,
                    "ratio": vol_ratio,
                    "desc": vol_desc
                },
                "trend": {
                    "score": trend_score,
                    "max": 25,
                    "desc": trend_desc
                },
                "spread": {
                    "score": spread_score,
                    "max": 25,
                    "spread_pts": current_spread,
                    "desc": spread_desc
                }
            },
            "saved_junk_trades_count": self.saved_junk_trades,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        return result

    def record_filtered_trade(self, setup_id: str, score_data: dict):
        """Record when a junk trade is blocked to protect capital."""
        self.saved_junk_trades += 1
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "setup": setup_id,
            "score": score_data.get("score", 0),
            "grade": score_data.get("grade", "C"),
            "reason": f"Score {score_data.get('score')} < {self.threshold} | {score_data.get('pillars', {}).get('volume', {}).get('desc', '')}"
        }
        self.recent_evaluations.insert(0, entry)
        if len(self.recent_evaluations) > 50:
            self.recent_evaluations.pop()
        self.save_state()
        logger.warning(f"🛡️ [CAPITAL PROTECTED] Blocked Junk Trade {setup_id} | Score: {score_data.get('score')}/100 ({score_data.get('grade')}) | Total Saved: {self.saved_junk_trades}")
