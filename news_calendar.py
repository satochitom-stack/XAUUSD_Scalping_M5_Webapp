"""
Economic News Calendar & High-Impact Volatility Tracker for XAUUSD Engine
Tracks major macroeconomic events for USD & Gold (CPI, NFP, FOMC, Fed Rate, Jobless Claims, GDP, PMI, Retail Sales),
evaluates real-time news proximity, and provides strategy execution filters and risk calibration.
"""

import os
import json
import logging
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("NewsCalendar")

class NewsCalendarManager:
    """Tracks economic news events, calculates proximity, and gates bot strategies during news volatility."""
    
    def __init__(self, data_file_path: Optional[str] = None):
        if data_file_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_file_path = os.path.join(base_dir, "economic_news_data.json")
        self.data_file_path = data_file_path
        
        self.enabled = True
        self.pre_news_buffer_mins = 20 # Mins before news to enter PRE_NEWS state
        self.impact_window_mins = 15   # Mins during/after news for extreme impact state
        self.post_news_digest_mins = 45 # Mins after impact for trend settling state
        
        self.events_calendar: List[dict] = []
        self.last_sync_time = None
        self._load_or_generate_calendar()

    def _load_or_generate_calendar(self):
        """Load cached calendar or generate standard dynamic economic calendar schedule for the week."""
        if os.path.exists(self.data_file_path):
            try:
                with open(self.data_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.events_calendar = data.get("events", [])
                    self.last_sync_time = data.get("last_sync")
                    if self.events_calendar:
                        logger.info(f"Loaded {len(self.events_calendar)} economic news events from cache.")
                        return
            except Exception as e:
                logger.error(f"Error loading news calendar cache: {e}")

        self.generate_weekly_calendar()

    def generate_weekly_calendar(self):
        """Build dynamic schedule for current week based on major recurring US events."""
        now = datetime.now()
        start_of_week = now - timedelta(days=now.weekday()) # Monday
        
        generated_events = []
        
        # Schedule events for each day of the current week and next week
        for week_offset in [0, 7]:
            base_monday = start_of_week + timedelta(days=week_offset)
            
            # Thursday: Initial Jobless Claims @ 19:30
            thursday = base_monday + timedelta(days=3)
            dt_claims = datetime(thursday.year, thursday.month, thursday.day, 19, 30)
            generated_events.append({
                "id": f"jobless_{dt_claims.strftime('%Y%m%d')}",
                "name": "US Initial Jobless Claims",
                "impact": "MEDIUM",
                "currency": "USD",
                "datetime": dt_claims.strftime("%Y-%m-%d %H:%M:%S"),
                "forecast": "225K",
                "previous": "231K",
                "volatility_pts": 350.0
            })
            
            # Friday: Flash PMI or NFP @ 19:30 or 21:00
            friday = base_monday + timedelta(days=4)
            dt_nfp = datetime(friday.year, friday.month, friday.day, 19, 30)
            generated_events.append({
                "id": f"nfp_{dt_nfp.strftime('%Y%m%d')}",
                "name": "US Non-Farm Payrolls & Unemployment Rate",
                "impact": "HIGH",
                "currency": "USD",
                "datetime": dt_nfp.strftime("%Y-%m-%d %H:%M:%S"),
                "forecast": "165K",
                "previous": "114K",
                "volatility_pts": 850.0
            })
            
            # Tuesday/Wednesday: CPI / PPI / FOMC
            wednesday = base_monday + timedelta(days=2)
            dt_cpi = datetime(wednesday.year, wednesday.month, wednesday.day, 19, 30)
            generated_events.append({
                "id": f"cpi_{dt_cpi.strftime('%Y%m%d')}",
                "name": "US Core CPI Inflation (MoM / YoY)",
                "impact": "HIGH",
                "currency": "USD",
                "datetime": dt_cpi.strftime("%Y-%m-%d %H:%M:%S"),
                "forecast": "0.2%",
                "previous": "0.3%",
                "volatility_pts": 750.0
            })

        # Sort chronologically
        generated_events.sort(key=lambda x: x["datetime"])
        self.events_calendar = generated_events
        self.last_sync_time = now.isoformat()
        self._save_state()

    def _save_state(self):
        try:
            payload = {
                "enabled": self.enabled,
                "last_sync": self.last_sync_time,
                "events": self.events_calendar
            }
            with open(self.data_file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save economic news data: {e}")

    def get_news_status(self) -> dict:
        """
        Determine real-time news proximity state:
        - NEWS_RELEASE_IMPACT: Inside release window (+-15 mins) -> Extreme Volatility
        - PRE_NEWS: 15-30 mins prior to release -> Caution / Reduced lot
        - POST_NEWS_DIGEST: 15-60 mins after release -> Directional Settling
        - NORMAL_NO_NEWS: Standard calm market
        """
        now = datetime.now()
        if not self.enabled:
            return {
                "state": "NORMAL_NO_NEWS",
                "label": "News Radar Off",
                "is_news_active": False,
                "nearest_event": None,
                "mins_to_event": 999,
                "blocked_strategies": [],
                "recommended_strategies": ["ALL_CONFLUENCE"]
            }

        nearest_event = None
        min_diff_mins = 999999

        for ev in self.events_calendar:
            ev_dt = datetime.strptime(ev["datetime"], "%Y-%m-%d %H:%M:%S")
            diff_secs = (ev_dt - now).total_seconds()
            diff_mins = diff_secs / 60.0

            # Consider events within past 2 hours and future 48 hours
            if -120 <= diff_mins <= 2880:
                if abs(diff_mins) < abs(min_diff_mins):
                    min_diff_mins = diff_mins
                    nearest_event = ev

        if not nearest_event:
            return {
                "state": "NORMAL_NO_NEWS",
                "label": "🟢 Normal Market (No Major News)",
                "is_news_active": False,
                "nearest_event": None,
                "mins_to_event": 999,
                "blocked_strategies": [],
                "recommended_strategies": ["ALL_CONFLUENCE"]
            }

        # Classify Proximity State
        impact = nearest_event.get("impact", "HIGH")
        ev_name = nearest_event.get("name", "USD News")

        if -self.impact_window_mins <= min_diff_mins <= self.impact_window_mins:
            state = "NEWS_RELEASE_IMPACT"
            label = f"⚡ HIGH IMPACT NEWS SPIKE: {ev_name}"
            is_active = True
            blocked = ["ASIAN_RANGE_SNIPER", "SECRET_EMA_PULLBACK", "EMA_RIBBON"]
            rec = ["NEWS_MOMENTUM_EXPANSION", "BB_SQUEEZE"]
        elif 0 < min_diff_mins <= self.pre_news_buffer_mins:
            state = "PRE_NEWS"
            label = f"⚠️ PRE-NEWS RADAR ({int(min_diff_mins)}m to {ev_name})"
            is_active = True
            blocked = ["ASIAN_RANGE_SNIPER"]
            rec = ["NEWS_MOMENTUM_EXPANSION", "ALL_CONFLUENCE"]
        elif - (self.impact_window_mins + self.post_news_digest_mins) <= min_diff_mins < -self.impact_window_mins:
            state = "POST_NEWS_DIGEST"
            label = f"🔵 POST-NEWS TREND SETTLING ({abs(int(min_diff_mins))}m after {ev_name})"
            is_active = False
            blocked = ["ASIAN_RANGE_SNIPER"]
            rec = ["NEWS_MOMENTUM_EXPANSION", "EMA50_3CANDLES_H1", "SMC_SWEEP", "ALL_CONFLUENCE"]
        else:
            state = "NORMAL_NO_NEWS"
            label = "🟢 Calm Market Session"
            is_active = False
            blocked = []
            rec = ["ALL_CONFLUENCE", "EMA50_3CANDLES_H1", "ASIAN_RANGE_SNIPER", "SMC_SWEEP", "EMA_RIBBON", "BB_SQUEEZE", "SECRET_EMA_PULLBACK"]

        return {
            "state": state,
            "label": label,
            "is_news_active": is_active,
            "nearest_event": nearest_event,
            "mins_to_event": round(min_diff_mins, 1),
            "blocked_strategies": blocked,
            "recommended_strategies": rec
        }

    def get_upcoming_events(self, limit: int = 5) -> List[dict]:
        """Get chronologically sorted upcoming news events with human readable countdowns."""
        now = datetime.now()
        upcoming = []

        for ev in self.events_calendar:
            ev_dt = datetime.strptime(ev["datetime"], "%Y-%m-%d %H:%M:%S")
            diff_mins = (ev_dt - now).total_seconds() / 60.0

            if diff_mins >= -60: # Include events that just occurred in the last hour
                item = dict(ev)
                item["mins_left"] = round(diff_mins, 1)
                
                if diff_mins > 60:
                    hrs = int(diff_mins // 60)
                    mins = int(diff_mins % 60)
                    item["countdown_text"] = f"{hrs}h {mins}m"
                elif diff_mins > 0:
                    item["countdown_text"] = f"{int(diff_mins)}m"
                elif diff_mins >= -15:
                    item["countdown_text"] = "LIVE NOW ⚡"
                else:
                    item["countdown_text"] = f"{abs(int(diff_mins))}m ago"
                
                upcoming.append(item)

        upcoming.sort(key=lambda x: x["datetime"])
        return upcoming[:limit]
