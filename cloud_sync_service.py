"""
Cloud Firestore Sync Service for MT5 Bot Intelligence
Synchronizes real bot trade statistics, winrate by setup, hourly heatmap, and AI learning insights
directly to Firebase Firestore so the user can view the dashboard anywhere.
"""

import time
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("CloudFirestoreSync")

FIREBASE_PROJECT_ID = "trading-journal-c8490"
FIRESTORE_REST_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"

class CloudFirestoreSyncService:
    def __init__(self, analytics_manager, scorer_manager=None):
        self.analytics = analytics_manager
        self.scorer = scorer_manager
        self.last_sync_time = 0
        self.sync_interval_seconds = 60 # Sync every 60 seconds or on trade close

    def _convert_value_to_firestore(self, val: Any) -> dict:
        """Helper to convert Python types to Firestore REST JSON fields."""
        if val is None:
            return {"nullValue": None}
        elif isinstance(val, bool):
            return {"booleanValue": val}
        elif isinstance(val, int):
            return {"integerValue": str(val)}
        elif isinstance(val, float):
            return {"doubleValue": val}
        elif isinstance(val, str):
            return {"stringValue": val}
        elif isinstance(val, list):
            return {"arrayValue": {"values": [self._convert_value_to_firestore(v) for v in val]}}
        elif isinstance(val, dict):
            return {"mapValue": {"fields": {k: self._convert_value_to_firestore(v) for k, v in val.items()}}}
        return {"stringValue": str(val)}

    def sync_summary_to_firestore(self) -> bool:
        """Push complete bot analytics summary and setup stats to Firestore."""
        try:
            stats = self.analytics.get_real_stats_summary()
            regime_info = {
                "score": 71,
                "grade": "A",
                "title": "High Quality Confluence"
            }
            if self.scorer and hasattr(self.scorer, "get_current_regime_state"):
                sc_state = self.scorer.get_current_regime_state()
                regime_info["score"] = sc_state.get("score", 71)
                regime_info["grade"] = sc_state.get("grade", "A")
                regime_info["title"] = sc_state.get("grade_title", "High Quality Confluence")

            # Document Payload
            doc_data = {
                "updated_at": datetime.now().isoformat(),
                "overview": stats.get("overview", {}),
                "setups": stats.get("setups", []),
                "regime": regime_info
            }

            # Convert to Firestore REST Payload
            fields = {k: self._convert_value_to_firestore(v) for k, v in doc_data.items()}
            payload = json.dumps({"fields": fields}).encode("utf-8")

            API_KEY = "AIzaSyBKkyrbGoh5qsaWOplOvOVFrm42GDIgHzk"
            url = f"{FIRESTORE_REST_BASE}/bot_intelligence/summary?key={API_KEY}"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PATCH"
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in [200, 201]:
                    self.last_sync_time = time.time()
                    logger.info("✅ Successfully synced real bot stats to Cloud Firestore.")
                    return True
        except Exception as e:
            logger.error(f"Error syncing to Firestore: {e}")
        return False

