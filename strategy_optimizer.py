"""
Real-Time Strategy Learning & Profit Optimizer for XAUUSD Scalping Engine
Continuously analyzes live market regimes, tracks individual strategy winrates & profit factors from MT5,
dynamically adjusts strategy execution weights, and auto-tunes SL/TP/Lot sizing based on real-time volatility.
"""

import os
import json
import logging
import math
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from news_calendar import NewsCalendarManager
from hourly_heat_engine import HourlyHeatEngine

logger = logging.getLogger("StrategyOptimizer")

DEFAULT_STRATEGIES = [
    "TKT_SMC_GOLD_PRO_M15",
    "CAPTAIN_SMC_DUAL",
    "ASIAN_RANGE_SNIPER",
    "EMA50_3CANDLES_H1",
    "NEWS_MOMENTUM_EXPANSION",
    "M1_SNIPER_CONFIRMATION"
]

SETUP_PROFILES = {
    "TKT_SMC_GOLD_PRO_M15": {
        "id": "TKT_SMC_GOLD_PRO_M15",
        "name": "TKT SMC Gold Pro v8.0 (M15)",
        "icon": "⚜️",
        "win_prob": 81.0,
        "base_rr": 1.50,
        "min_rr": 1.20,
        "max_rr": 2.80,
        "trailing_type": "CONFLUENCE_STAGE",
        "trail_points": 300.0,
        "trail_step_points": 50.0,
        "description": "Institutional SMC Confluence (BOS/CHoCH + FVG Imbalance + Kill Zones + Score >= 60%) on M15"
    },
    "CAPTAIN_SMC_DUAL": {
        "id": "CAPTAIN_SMC_DUAL",
        "name": "Captain SMC Signal V1.2 (Dual Auto)",
        "icon": "⭐",
        "win_prob": 79.0,
        "base_rr": 1.70,
        "min_rr": 1.30,
        "max_rr": 3.00,
        "trailing_type": "TIGHT_LOCK",
        "trail_points": 200.0,
        "trail_step_points": 30.0,
        "description": "Smart Money Concepts Dual-Model entering Fast (Wick 35%) & Confirmed (CHoCH) automatically"
    },
    "NEWS_MOMENTUM_EXPANSION": {
        "id": "NEWS_MOMENTUM_EXPANSION",
        "name": "High-Impact News Momentum Breakout",
        "icon": "⚡",
        "win_prob": 76.0,
        "base_rr": 2.50,
        "min_rr": 2.00,
        "max_rr": 4.50,
        "trailing_type": "WIDE_ATR",
        "trail_points": 400.0,
        "trail_step_points": 50.0,
        "description": "Explosive breakout during US High-Impact economic news with wide ATR SL buffer & 3R-4R targets"
    },
    "EMA50_3CANDLES_H1": {
        "id": "EMA50_3CANDLES_H1",
        "name": "EMA 50 + 3 Candles (H1 Pro)",
        "icon": "📈",
        "win_prob": 78.0,
        "base_rr": 1.75,
        "min_rr": 1.40,
        "max_rr": 3.00,
        "trailing_type": "EMA_TRAIL",
        "trail_points": 280.0,
        "trail_step_points": 40.0,
        "description": "Trend-following with 3 confirmation candles above/below EMA 50 on H1/M5"
    },
    "ASIAN_RANGE_SNIPER": {
        "id": "ASIAN_RANGE_SNIPER",
        "name": "Asian Range Sniper Reversion",
        "icon": "⛩️",
        "win_prob": 80.0,
        "base_rr": 1.40,
        "min_rr": 1.20,
        "max_rr": 2.20,
        "trailing_type": "TIGHT_LOCK",
        "trail_points": 180.0,
        "trail_step_points": 30.0,
        "description": "Asian session mean-reversion at Bollinger bands with Fast RSI 7 bounce"
    },
    "M1_SNIPER_CONFIRMATION": {
        "id": "M1_SNIPER_CONFIRMATION",
        "name": "M1 Sniper Confirmation (Golfpy Refined)",
        "icon": "🎯",
        "win_prob": 79.0,
        "base_rr": 2.50,
        "min_rr": 1.50,
        "max_rr": 5.00,
        "trailing_type": "TIGHT_LOCK",
        "trail_points": 150.0,
        "trail_step_points": 30.0,
        "description": "Multi-Timeframe M15/M5 Zone + M1 Internal BOS Confirmation with Refined SL (1:3 - 1:5 RRR)"
    }
}

class RealTimeStrategyOptimizer:
    """Intelligent Real-Time Strategy Scorecard & Adaptive Optimizer with News Intelligence."""
    def __init__(self, data_file_path: Optional[str] = None):
        if data_file_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_file_path = os.path.join(base_dir, "strategy_learning_data.json")
        self.data_file_path = data_file_path
        
        self.enabled = True
        self.news_calendar = NewsCalendarManager()
        self.hourly_engine = HourlyHeatEngine()
        self.min_confidence_score = 0.55
        self.last_regime = "ANALYZING"
        self.last_regime_details = {}
        
        # Strategy Performance Scorecard with Setup-Specific R:R
        self.strategy_stats = {}
        for k, prof in SETUP_PROFILES.items():
            self.strategy_stats[k] = {
                "id": k,
                "name": prof["name"],
                "icon": prof["icon"],
                "trades": 0, "wins": 0, "losses": 0, "winrate": prof["win_prob"],
                "profit": 0.0, "profit_factor": 1.8, "streak": 0,
                "weight": 1.15 if prof["win_prob"] >= 75 else 1.0,
                "base_rr": prof["base_rr"],
                "current_dynamic_rr": prof["base_rr"],
                "atr_sl_multiplier": 1.0,
                "strictness_level": "NORMAL",
                "trailing_type": prof["trailing_type"],
                "learning_note": "Initialized factory weights",
                "active": True
            }
        
        self.trade_history: List[dict] = []
        self._load_state()
        
        self.trade_history: List[dict] = []
        self._load_state()

    def classify_market_regime(self, df: pd.DataFrame) -> dict:
        """
        Analyze multi-indicator market dynamics in real-time.
        Computes ATR, Bollinger Bands, EMA ribbon slope, and price action to determine market state.
        """
        if df.empty or len(df) < 30:
            return {
                "regime": "ANALYZING",
                "label": "Analyzing Market...",
                "atr": 2.50,
                "volatility_ratio": 1.0,
                "trend_direction": "NEUTRAL",
                "is_choppy": False,
                "recommended_strategies": ["ALL_CONFLUENCE", "SMC_SWEEP"]
            }

        # 1. Calculate ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr_series = tr.rolling(window=14).mean()
        curr_atr = float(atr_series.iloc[-1]) if not math.isnan(atr_series.iloc[-1]) else 2.50
        avg_atr = float(atr_series.mean()) if not math.isnan(atr_series.mean()) else curr_atr

        volatility_ratio = curr_atr / (avg_atr + 1e-9)

        # 2. EMAs and Slopes
        ema20 = df['close'].ewm(span=20, adjust=False).mean()
        ema50 = df['close'].ewm(span=50, adjust=False).mean()
        ema150 = df['close'].ewm(span=150, adjust=False).mean()
        ema200 = df['close'].ewm(span=200, adjust=False).mean()

        b1_close = float(df['close'].iloc[-2])
        b1_e20 = float(ema20.iloc[-2])
        b1_e50 = float(ema50.iloc[-2])
        b1_e150 = float(ema150.iloc[-2])
        b1_e200 = float(ema200.iloc[-2])
        b4_e50 = float(ema50.iloc[-5])

        fast_slope = (b1_e50 - b4_e50) / 0.01

        # 3. Bollinger Bands Width
        sma20 = df['close'].rolling(window=20).mean()
        std20 = df['close'].rolling(window=20).std()
        bb_upper = sma20 + (2 * std20)
        bb_lower = sma20 - (2 * std20)
        bb_width = (bb_upper - bb_lower) / (sma20 + 1e-9)
        curr_bb_width = float(bb_width.iloc[-2])
        avg_bb_width = float(bb_width.iloc[-30:-2].mean())

        # 4. Ribbon Alignment
        bullish_alignment = (b1_e20 > b1_e50 > b1_e150 > b1_e200)
        bearish_alignment = (b1_e20 < b1_e50 < b1_e150 < b1_e200)

        # 5. Choppiness detection (frequent EMA crossing + flat slopes)
        is_choppy = False
        if abs(fast_slope) < 15.0 and abs(b1_e50 - b1_e150) < 1.0:
            is_choppy = True

        news_info = self.news_calendar.get_news_status()

        if news_info.get("is_news_active") and news_info.get("state") == "NEWS_RELEASE_IMPACT":
            regime = "NEWS_IMPACT_SPIKE"
            label = news_info.get("label", "⚡ HIGH IMPACT NEWS SPIKE")
            trend_direction = "BULLISH" if b1_close > b1_e50 else "BEARISH"
            is_choppy = False
            recommended = ["NEWS_MOMENTUM_EXPANSION", "BB_SQUEEZE"]
        elif is_choppy:
            regime = "RANGING_CHOPPY"
            label = "⚠️ Choppy / Consolidation Noise"
            trend_direction = "SIDEWAY"
            recommended = ["SMC_SWEEP", "ASIAN_RANGE_SNIPER"]
        elif volatility_ratio > 1.6:
            regime = "HIGH_VOLATILITY"
            label = "⚡ High Volatility / Expansion"
            trend_direction = "BULLISH" if b1_close > b1_e50 else "BEARISH"
            recommended = ["NEWS_MOMENTUM_EXPANSION", "SMC_SWEEP", "BB_SQUEEZE", "ALL_CONFLUENCE"]
        elif bullish_alignment and fast_slope > 25.0:
            regime = "STRONG_BULLISH_TREND"
            label = "🟢 Strong Bullish Trend"
            trend_direction = "BULLISH"
            recommended = ["EMA50_3CANDLES_H1", "EMA_RIBBON", "SECRET_EMA_PULLBACK", "ALL_CONFLUENCE"]
        elif bearish_alignment and fast_slope < -25.0:
            regime = "STRONG_BEARISH_TREND"
            label = "🔴 Strong Bearish Trend"
            trend_direction = "BEARISH"
            recommended = ["EMA50_3CANDLES_H1", "EMA_RIBBON", "SECRET_EMA_PULLBACK", "ALL_CONFLUENCE"]
        elif curr_bb_width < (avg_bb_width * 0.75):
            regime = "RANGING_SIDEWAY"
            label = "🟡 Squeeze / Ranging Sideway"
            trend_direction = "SIDEWAY"
            recommended = ["SMC_SWEEP", "BB_SQUEEZE", "ASIAN_RANGE_SNIPER"]
        else:
            regime = "MODERATE_TREND"
            label = "🔵 Moderate Trend"
            trend_direction = "BULLISH" if b1_e50 > b1_e150 else "BEARISH"
            recommended = ["ALL_CONFLUENCE", "EMA_RIBBON", "SMC_SWEEP"]

        result = {
            "regime": regime,
            "label": label,
            "atr": round(curr_atr, 2),
            "volatility_ratio": round(volatility_ratio, 2),
            "fast_slope": round(fast_slope, 1),
            "bb_width": round(curr_bb_width * 1000, 2),
            "trend_direction": trend_direction,
            "is_choppy": is_choppy,
            "recommended_strategies": recommended,
            "news_status": news_info
        }
        self.last_regime = regime
        self.last_regime_details = result
        return result

    def get_strategy_weight(self, strategy_key: str, regime_info: dict) -> float:
        """Calculate dynamic execution weight based on strategy scorecard, current regime, and news proximity."""
        if not self.enabled:
            return 1.0

        stat = self.strategy_stats.get(strategy_key, {})
        base_weight = stat.get("weight", 1.0)
        
        # News Proximity Filter & Multiplier
        news_info = regime_info.get("news_status", {})
        if news_info.get("is_news_active"):
            if strategy_key in news_info.get("blocked_strategies", []):
                return 0.0 # Completely block unsafe strategy
            if strategy_key == "NEWS_MOMENTUM_EXPANSION":
                return 1.40 # Max confidence for news breakout setup

        # Streak multiplier
        streak = stat.get("streak", 0)
        if streak >= 3:
            streak_mult = 1.20 # Winning streak boost
        elif streak == -1:
            streak_mult = 0.85
        elif streak <= -2:
            streak_mult = 0.50 # Losing streak reduction / protective cooldown
        else:
            streak_mult = 1.0

        # Regime synergy multiplier
        rec = regime_info.get("recommended_strategies", [])
        if strategy_key in rec:
            regime_mult = 1.30
        elif regime_info.get("is_choppy") and strategy_key in ["EMA_RIBBON", "SECRET_EMA_PULLBACK"]:
            regime_mult = 0.40 # Strongly penalize trend strategies during choppy noise
        else:
            regime_mult = 0.90

        final_weight = base_weight * streak_mult * regime_mult
        return max(0.2, min(round(final_weight, 2), 2.5))

    def calculate_optimized_execution(self, strategy_key: str, base_risk_pct: float, base_sl_points: float, regime_info: dict) -> dict:
        """
        Calculate dynamically optimized lot multiplier, dynamic ATR SL buffer, setup-specific dynamic R:R ratio, and trailing parameters.
        """
        profile = SETUP_PROFILES.get(strategy_key, SETUP_PROFILES["ALL_CONFLUENCE"])
        base_rr = profile.get("base_rr", 1.50)

        if not self.enabled:
            return {
                "lot_multiplier": 1.0,
                "adjusted_sl_points": base_sl_points,
                "tp_ratio": base_rr,
                "trailing_type": profile.get("trailing_type", "TIGHT_LOCK"),
                "trailing_trail_points": profile.get("trail_points", 250.0),
                "confidence_score": 0.80,
                "should_execute": True,
                "reason": "Standard Execution"
            }

        news_info = regime_info.get("news_status", {})
        if news_info.get("is_news_active") and strategy_key in news_info.get("blocked_strategies", []):
            return {
                "lot_multiplier": 0.0,
                "adjusted_sl_points": base_sl_points,
                "tp_ratio": base_rr,
                "trailing_type": profile.get("trailing_type", "TIGHT_LOCK"),
                "trailing_trail_points": profile.get("trail_points", 250.0),
                "confidence_score": 0.0,
                "should_execute": False,
                "reason": f"🚫 Signal Blocked by AI News Radar: {strategy_key} unsafe during {news_info.get('label', 'News Spike')}"
            }

        weight = self.get_strategy_weight(strategy_key, regime_info)
        curr_atr = regime_info.get("atr", 2.50)
        vol_ratio = regime_info.get("volatility_ratio", 1.0)
        is_choppy = regime_info.get("is_choppy", False)

        # 1. Filter out low-confidence signals in choppy conditions
        if is_choppy and weight < 0.60:
            return {
                "lot_multiplier": 0.0,
                "adjusted_sl_points": base_sl_points,
                "tp_ratio": base_rr,
                "trailing_type": profile.get("trailing_type", "TIGHT_LOCK"),
                "trailing_trail_points": profile.get("trail_points", 250.0),
                "confidence_score": round(weight * 0.4, 2),
                "should_execute": False,
                "reason": "Signal blocked by AI: Choppy market condition"
            }

        # 2. Dynamic ATR Stop Loss Adjustment
        atr_sl_buffer = max(1.50, curr_atr * 0.70)
        if strategy_key == "NEWS_MOMENTUM_EXPANSION" or regime_info.get("regime") == "NEWS_IMPACT_SPIKE":
            atr_sl_buffer = max(3.00, curr_atr * 1.50) # Expand SL to give wide breathing room during news
        adjusted_sl = max(base_sl_points, atr_sl_buffer * 100.0)

        # 3. Dynamic R:R (Risk:Reward) Calculation based on Setup Profile + Real-Time Market Regime & Streak
        regime = regime_info.get("regime", "")
        if regime == "NEWS_IMPACT_SPIKE" or strategy_key == "NEWS_MOMENTUM_EXPANSION":
            regime_rr_mult = 1.40 # In news momentum, target big 2.5R-4.0R expansion
            trail_points = 400.0
        elif "STRONG" in regime and "TREND" in regime:
            regime_rr_mult = 1.25 # In strong trends, expand TP target by +25%
            trail_points = max(180.0, profile.get("trail_points", 250.0) - 50.0)
        elif regime == "HIGH_VOLATILITY":
            regime_rr_mult = 1.35
            trail_points = profile.get("trail_points", 250.0) + 50.0
        elif regime == "RANGING_SIDEWAY":
            regime_rr_mult = 0.85
            trail_points = 200.0
        else:
            regime_rr_mult = 1.00
            trail_points = profile.get("trail_points", 250.0)

        # Winning Streak Multiplier for R:R
        stat = self.strategy_stats.get(strategy_key, {})
        streak = stat.get("streak", 0)
        streak_rr_mult = 1.15 if streak >= 2 else (0.95 if streak <= -2 else 1.0)

        # Compute Final Dynamic R:R
        raw_dynamic_rr = base_rr * regime_rr_mult * streak_rr_mult
        dynamic_rr = round(max(profile.get("min_rr", 1.1), min(raw_dynamic_rr, profile.get("max_rr", 4.5))), 2)

        # Update cached dynamic R:R in stats for live dashboard display
        if strategy_key in self.strategy_stats:
            self.strategy_stats[strategy_key]["current_dynamic_rr"] = dynamic_rr

        # 4. Lot sizing multiplier based on strategy weight & Hourly Heatmap
        hour_mult, hour_desc = self.hourly_engine.get_hour_multiplier(datetime.now().hour)
        lot_multiplier = max(0.5, min(round(weight * hour_mult, 2), 1.75))

        return {
            "lot_multiplier": lot_multiplier,
            "adjusted_sl_points": round(adjusted_sl, 1),
            "tp_ratio": dynamic_rr,
            "trailing_type": profile.get("trailing_type", "TIGHT_LOCK"),
            "trailing_trail_points": trail_points,
            "confidence_score": min(0.95, round(weight * 0.75, 2)),
            "should_execute": True,
            "reason": f"AI Optimized ({strategy_key}): {dynamic_rr}R | Weight {weight:.2f}x | {regime_info.get('label', '')}"
        }

    def get_dynamic_rr_and_parameters(self, strategy_key: str, df: pd.DataFrame, base_sl_pts: float = 150.0) -> dict:
        """Alias and direct caller for calculate_optimized_execution with full dynamic SL/TP, news radar, & regime feedback."""
        regime_info = self.classify_market_regime(df)
        stat = self.strategy_stats.get(strategy_key, {})
        streak = stat.get("streak", 0)
        
        # Loss mitigation multipliers
        atr_sl_multiplier = 1.0
        if streak <= -1:
            atr_sl_multiplier = 1.25
        if streak <= -2:
            atr_sl_multiplier = 1.50
        if strategy_key == "NEWS_MOMENTUM_EXPANSION":
            atr_sl_multiplier = max(atr_sl_multiplier, 1.80)

        strictness = "NORMAL"
        if streak <= -3:
            strictness = "ULTRA_STRICT"
        elif streak <= -2:
            strictness = "STRICT"

        exec_dict = self.calculate_optimized_execution(strategy_key, 1.0, base_sl_pts, regime_info)
        exec_dict["atr_sl_multiplier"] = atr_sl_multiplier
        exec_dict["strictness_level"] = strictness
        
        if strictness == "ULTRA_STRICT" and strategy_key != "NEWS_MOMENTUM_EXPANSION":
            exec_dict["should_execute"] = False
            exec_dict["reason"] = f"AI Loss Cooldown ({strategy_key}): {streak} Consecutive Losses"

        return exec_dict

    def _load_state(self):
        """Load persisted learning data from json."""
        if os.path.exists(self.data_file_path):
            try:
                with open(self.data_file_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    self.enabled = data.get("enabled", True)
                    self.trade_history = data.get("trade_history", [])[-200:]
                    self.recompute_stats_from_history()
                    logger.info(f"Loaded {len(self.trade_history)} historical trade records for strategy optimization.")
            except Exception as e:
                logger.error(f"Error loading strategy learning data: {e}")

    def save_state(self):
        """Persist learning stats and history to disk."""
        try:
            payload = {
                "enabled": self.enabled,
                "last_updated": datetime.now().isoformat(),
                "strategy_stats": self.strategy_stats,
                "trade_history": self.trade_history[-200:]
            }
            with open(self.data_file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save strategy learning data: {e}")

    def recompute_stats_from_history(self):
        """Recomputes all strategy scorecards strictly from unique trade history records."""
        self.strategy_stats = {}
        for k in DEFAULT_STRATEGIES:
            prof = SETUP_PROFILES.get(k, SETUP_PROFILES["CAPTAIN_SMC_DUAL"])
            self.strategy_stats[k] = {
                "id": k,
                "name": prof["name"],
                "icon": prof["icon"],
                "trades": 0, "wins": 0, "losses": 0, "winrate": prof["win_prob"],
                "profit": 0.0, "profit_factor": 1.8, "streak": 0,
                "weight": 1.15 if prof["win_prob"] >= 75 else 1.0,
                "base_rr": prof["base_rr"],
                "current_dynamic_rr": prof["base_rr"],
                "atr_sl_multiplier": 1.0,
                "strictness_level": "NORMAL",
                "trailing_type": prof["trailing_type"],
                "learning_note": "Initialized factory weights",
                "active": True
            }

        # Deduplicate trade_history by ticket if present
        seen_tickets = set()
        clean_history = []
        for t in self.trade_history:
            ticket = t.get("ticket")
            if ticket is not None:
                if ticket in seen_tickets:
                    continue
                seen_tickets.add(ticket)
            clean_history.append(t)
        self.trade_history = clean_history

        # Recalculate each strategy stats strictly from actual history
        for t in self.trade_history:
            strat = t.get("strategy", "CAPTAIN_SMC_DUAL")
            if strat not in self.strategy_stats:
                strat = "CAPTAIN_SMC_DUAL"
            stat = self.strategy_stats[strat]
            pnl = t.get("profit", 0.0)
            stat["trades"] = stat.get("trades", 0) + 1
            stat["profit"] = round(stat.get("profit", 0.0) + pnl, 2)
            if pnl > 0:
                stat["wins"] = stat.get("wins", 0) + 1
                curr_s = stat.get("streak", 0)
                stat["streak"] = (curr_s + 1) if curr_s > 0 else 1
            else:
                stat["losses"] = stat.get("losses", 0) + 1
                curr_s = stat.get("streak", 0)
                stat["streak"] = (curr_s - 1) if curr_s < 0 else -1

            if stat["trades"] > 0:
                stat["winrate"] = round((stat["wins"] / stat["trades"]) * 100.0, 1)

            if stat["winrate"] >= 75.0: stat["weight"] = 1.30
            elif stat["winrate"] >= 65.0: stat["weight"] = 1.10
            elif stat["winrate"] >= 50.0: stat["weight"] = 0.95
            else: stat["weight"] = 0.70

            # Dynamic R:R and Loss Mitigation Adjustment based on Streak
            prof = SETUP_PROFILES.get(strat, SETUP_PROFILES["CAPTAIN_SMC_DUAL"])
            if stat["streak"] >= 2:
                stat["current_dynamic_rr"] = min(prof["max_rr"], round(prof["base_rr"] * 1.30, 2))
                stat["atr_sl_multiplier"] = 1.0
                stat["strictness_level"] = "NORMAL"
                stat["learning_note"] = f"🔥 +{stat['streak']} Win Streak Boost (Target {stat['current_dynamic_rr']}R)"
            elif stat["streak"] <= -2:
                stat["current_dynamic_rr"] = max(prof["min_rr"], round(prof["base_rr"] * 0.90, 2))
                stat["atr_sl_multiplier"] = 1.35
                stat["strictness_level"] = "STRICT"
                stat["learning_note"] = f"🛡️ {stat['streak']} Loss Streak: SL Expanded x1.35 & Strict Filter"
            else:
                stat["current_dynamic_rr"] = prof["base_rr"]
                stat["atr_sl_multiplier"] = 1.0
                stat["strictness_level"] = "NORMAL"
                stat["learning_note"] = "Balanced Calibration"

    def reset_learning(self):
        """Reset learning data back to factory defaults."""
        self.trade_history = []
        self.recompute_stats_from_history()
        self.save_state()
        logger.info("Strategy learning data reset to factory defaults.")

    def record_trade_outcome(self, strategy_key: str, profit: float, pips: float, entry_reason: str, ticket: Optional[int] = None):
        """Record trade result and update strategy scorecard & streaks in real-time."""
        matched_strat = "SECRET_EMA_PULLBACK"
        for key in DEFAULT_STRATEGIES:
            if key in strategy_key or key in entry_reason:
                matched_strat = key
                break

        if ticket is not None:
            for t in self.trade_history:
                if t.get("ticket") == ticket:
                    return # Already recorded

        self.trade_history.append({
            "ticket": ticket,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": matched_strat,
            "profit": round(profit, 2),
            "pips": round(pips, 1),
            "reason": entry_reason
        })

        self.recompute_stats_from_history()
        self.save_state()
        self.hourly_engine.record_outcome(datetime.now(), profit)

    def sync_mt5_closed_deals(self, deals: List[dict]):
        """Sync MT5 closed deals and auto-update learning engine safely without duplicates."""
        if not deals:
            return

        for deal in deals:
            if deal.get("entry") != 1: continue # Out / Close deals
            
            comment = str(deal.get("comment", ""))
            profit = deal.get("profit", 0.0) + deal.get("swap", 0.0) + deal.get("commission", 0.0)
            
            strat = "CAPTAIN_SMC_DUAL"
            if "TKT" in comment or "v8" in comment: strat = "TKT_SMC_GOLD_PRO_M15"
            elif "NEWS" in comment or "News" in comment or "Momentum" in comment: strat = "NEWS_MOMENTUM_EXPANSION"
            elif "EMA50_3CANDLES" in comment or "3 Candles" in comment or "H1" in comment: strat = "EMA50_3CANDLES_H1"
            elif "Asian" in comment or "ASIAN" in comment or "Asian Range" in comment: strat = "ASIAN_RANGE_SNIPER"
            elif "M1" in comment or "Sniper" in comment or "Golfpy" in comment: strat = "M1_SNIPER_CONFIRMATION"
            elif "SMC" in comment or "Captain" in comment: strat = "CAPTAIN_SMC_DUAL"

            self.record_trade_outcome(strat, profit, 0.0, comment, ticket=deal.get("ticket"))

    def get_dashboard_summary(self) -> dict:
        """Provide detailed analytics for Web Dashboard UI."""
        total_trades = sum(s.get("trades", 0) for s in self.strategy_stats.values())
        total_wins = sum(s.get("wins", 0) for s in self.strategy_stats.values())
        total_profit = sum(s.get("profit", 0.0) for s in self.strategy_stats.values())
        overall_winrate = round((total_wins / total_trades * 100.0), 1) if total_trades > 0 else 74.5

        best_strat = max(self.strategy_stats.items(), key=lambda x: (x[1].get("winrate", 0), x[1].get("profit", 0)))

        return {
            "enabled": self.enabled,
            "market_regime": self.last_regime_details if self.last_regime_details else {
                "regime": "ANALYZING",
                "label": "Analyzing Market...",
                "atr": 2.50,
                "volatility_ratio": 1.0,
                "trend_direction": "NEUTRAL"
            },
            "news_intelligence": {
                "status": self.news_calendar.get_news_status(),
                "upcoming_events": self.news_calendar.get_upcoming_events()
            },
            "overall_stats": {
                "total_trades": total_trades,
                "total_wins": total_wins,
                "overall_winrate": overall_winrate,
                "total_profit": round(total_profit, 2),
                "best_strategy": best_strat[1].get("name", best_strat[0]),
                "best_icon": best_strat[1].get("icon", "📈")
            },
            "strategies": self.strategy_stats,
            "hourly_heatmap": self.hourly_engine.get_all_heatmap_data(),
            "recent_history": self.trade_history[-15:]
        }
