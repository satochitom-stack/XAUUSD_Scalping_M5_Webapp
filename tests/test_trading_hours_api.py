"""
Automated Unit Tests for the per-setup Trading Hours Configuration feature
(DEFAULT_TRADING_HOURS, is_time_in_range, is_setup_in_trading_hours in bot_engine.py,
and MultiAccountManager.update_strategy_settings hot-reloading).

This verifies:
1. All active setups have default trading hours configured, and Asian setups
   (PULLBACK_DR_EKK, RTM_M6_ELITE_GROWTH, SMC_X_STO_H1) default to 14:00 - 24:00.
2. Time window checks properly handle standard intervals, midnight boundaries ("24:00" and "00:00"),
   and overnight spans crossing midnight (e.g. 19:00 - 02:00).
3. BotEngine respects dynamic overrides configured in strategy_cfg["trading_hours_overrides"].
4. AccountManager hot-reloads trading hours immediately without disconnecting MT5.
"""

import unittest
from datetime import time as dtime
from unittest.mock import MagicMock, patch

from bot_engine import (
    BotEngine,
    STRATEGY_MAGIC_MAP,
    DEFAULT_TRADING_HOURS,
    is_time_in_range,
)
from account_manager import MultiAccountManager


class TestTradingHoursDefaults(unittest.TestCase):
    def test_all_active_strategies_have_trading_hours(self):
        """Verify that every active strategy in STRATEGY_MAGIC_MAP has a default schedule."""
        for strat_id in STRATEGY_MAGIC_MAP:
            self.assertIn(strat_id, DEFAULT_TRADING_HOURS)
            cfg = DEFAULT_TRADING_HOURS[strat_id]
            self.assertIn("start", cfg)
            self.assertIn("end", cfg)

    def test_asian_setups_default_to_14_to_24(self):
        """Verify that RTM M6 and SMCxSTO default to 14:00 - 24:00, and PULLBACK_DR_EKK defaults to 24h."""
        self.assertEqual(DEFAULT_TRADING_HOURS["PULLBACK_DR_EKK"]["start"], "00:00")
        self.assertEqual(DEFAULT_TRADING_HOURS["PULLBACK_DR_EKK"]["end"], "24:00")
        for strat_id in ["RTM_M6_ELITE_GROWTH", "SMC_X_STO_H1"]:
            cfg = DEFAULT_TRADING_HOURS[strat_id]
            self.assertEqual(cfg["start"], "14:00", f"{strat_id} start should be 14:00")
            self.assertEqual(cfg["end"], "24:00", f"{strat_id} end should be 24:00")


class TestIsTimeInRange(unittest.TestCase):
    def test_same_day_window(self):
        # 14:00 to 20:00
        self.assertFalse(is_time_in_range(dtime(13, 59), "14:00", "20:00"))
        self.assertTrue(is_time_in_range(dtime(14, 0), "14:00", "20:00"))
        self.assertTrue(is_time_in_range(dtime(17, 30), "14:00", "20:00"))
        self.assertTrue(is_time_in_range(dtime(20, 0), "14:00", "20:00"))
        self.assertFalse(is_time_in_range(dtime(20, 1), "14:00", "20:00"))

    def test_until_midnight_24_00(self):
        # 14:00 to 24:00 (end of day)
        self.assertFalse(is_time_in_range(dtime(13, 59), "14:00", "24:00"))
        self.assertTrue(is_time_in_range(dtime(14, 0), "14:00", "24:00"))
        self.assertTrue(is_time_in_range(dtime(23, 59, 59), "14:00", "24:00"))
        self.assertFalse(is_time_in_range(dtime(0, 30), "14:00", "24:00"))

    def test_until_midnight_00_00(self):
        # 14:00 to 00:00 should treat 00:00 as end-of-day 23:59:59 when end <= start
        self.assertFalse(is_time_in_range(dtime(13, 59), "14:00", "00:00"))
        self.assertTrue(is_time_in_range(dtime(14, 0), "14:00", "00:00"))
        self.assertTrue(is_time_in_range(dtime(22, 0), "14:00", "00:00"))
        self.assertTrue(is_time_in_range(dtime(23, 59, 59), "14:00", "00:00"))

    def test_cross_midnight_window(self):
        # 19:00 to 02:00
        self.assertFalse(is_time_in_range(dtime(18, 59), "19:00", "02:00"))
        self.assertTrue(is_time_in_range(dtime(19, 0), "19:00", "02:00"))
        self.assertTrue(is_time_in_range(dtime(23, 45), "19:00", "02:00"))
        self.assertTrue(is_time_in_range(dtime(0, 30), "19:00", "02:00"))
        self.assertTrue(is_time_in_range(dtime(2, 0), "19:00", "02:00"))
        self.assertFalse(is_time_in_range(dtime(2, 1), "19:00", "02:00"))
        self.assertFalse(is_time_in_range(dtime(12, 0), "19:00", "02:00"))

    def test_24_hours_active(self):
        # 00:00 to 24:00
        self.assertTrue(is_time_in_range(dtime(0, 0), "00:00", "24:00"))
        self.assertTrue(is_time_in_range(dtime(12, 0), "00:00", "24:00"))
        self.assertTrue(is_time_in_range(dtime(23, 59), "00:00", "24:00"))


class TestBotEngineTradingHours(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.config = {
            "mt5": {"symbol": "XAUUSDc", "magic_number": 555888},
            "strategy": {"strategy_mode": "ALL"}
        }
        self.bot = BotEngine(self.mock_connector, self.config)

    def test_default_hours_respected(self):
        # PULLBACK_DR_EKK default is 24h (00:00 - 24:00)
        in_h, reason, s, e = self.bot.is_setup_in_trading_hours("PULLBACK_DR_EKK", check_time=dtime(10, 0))
        self.assertTrue(in_h)
        self.assertEqual(reason, "IN_HOURS")
        self.assertEqual(s, "00:00")
        self.assertEqual(e, "24:00")

        # RTM_M6_ELITE_GROWTH default is 14:00 - 24:00
        in_h, reason, s, e = self.bot.is_setup_in_trading_hours("RTM_M6_ELITE_GROWTH", check_time=dtime(10, 0))
        self.assertFalse(in_h)
        self.assertIn("OUTSIDE TRADING HOURS", reason)
        self.assertEqual(s, "14:00")
        self.assertEqual(e, "24:00")

        in_h, reason, _, _ = self.bot.is_setup_in_trading_hours("RTM_M6_ELITE_GROWTH", check_time=dtime(16, 0))
        self.assertTrue(in_h)
        self.assertEqual(reason, "IN_HOURS")

    def test_dynamic_override_applied(self):
        # Apply override for PULLBACK_DR_EKK to 08:00 - 12:00
        self.config["strategy"]["trading_hours_overrides"] = {
            "PULLBACK_DR_EKK": {"start_time": "08:00", "end_time": "12:00"}
        }
        in_h, reason, s, e = self.bot.is_setup_in_trading_hours("PULLBACK_DR_EKK", check_time=dtime(10, 0))
        self.assertTrue(in_h)
        self.assertEqual(reason, "IN_HOURS")
        self.assertEqual(s, "08:00")
        self.assertEqual(e, "12:00")

        # 16:00 is now outside the overridden hours
        in_h, reason, _, _ = self.bot.is_setup_in_trading_hours("PULLBACK_DR_EKK", check_time=dtime(16, 0))
        self.assertFalse(in_h)
        self.assertIn("OUTSIDE TRADING HOURS", reason)


class TestAccountManagerTradingHoursSettings(unittest.TestCase):
    def _make_manager(self):
        global_config = {
            "line_notification": {},
            "accounts": [
                {
                    "id": "acc_test_1",
                    "name": "TestBotAcct",
                    "type": "BOT",
                    "login": 0,
                    "password": "",
                    "server": "",
                    "path": "",
                    "symbol": "XAUUSDc",
                    "magic_number": 555888,
                    "simulation_mode": True,
                    "auto_start": False,
                    "strategy": {"strategy_mode": "ALL"}
                }
            ]
        }
        return MultiAccountManager(global_config)

    @patch.object(MultiAccountManager, "_save_to_config")
    def test_update_trading_hours_settings_live_sync(self, mock_save):
        mgr = self._make_manager()
        inst = mgr.get_account("acc_test_1")
        connector_before = inst.connector

        new_hours = {
            "PULLBACK_DR_EKK": {"start_time": "15:00", "end_time": "23:00"}
        }
        ok = mgr.update_strategy_settings("acc_test_1", {"trading_hours_overrides": new_hours})
        self.assertTrue(ok)

        # Check in memory mutation
        self.assertEqual(inst.strategy_cfg.get("trading_hours_overrides"), new_hours)
        self.assertEqual(inst.bot.config["strategy"].get("trading_hours_overrides"), new_hours)

        # Ensure no reconnection occurred
        self.assertIs(inst.connector, connector_before)
        self.assertIs(inst.bot.connector, connector_before)
        mock_save.assert_called()


if __name__ == "__main__":
    unittest.main()
