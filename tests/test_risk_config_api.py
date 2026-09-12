"""
Automated Unit Tests for the per-setup Risk Configuration feature
(RISK_PROFILE_DEFAULTS / calculate_lot_size overrides in bot_engine.py, and
MultiAccountManager.get_account / update_strategy_settings in account_manager.py).

This backs the /api/strategy/risk_config GET/POST endpoints in main.py that let the Web
Dashboard set a custom risk % per active pillar and have it apply to the live running bot
immediately (no restart, no MT5 reconnect). main.py itself is NOT imported here since this
sandbox does not have the `fastapi` package installed (network policy blocks PyPI) - the same
reason no test_main.py exists elsewhere in this suite. Everything that actually matters for
correctness (the lot-sizing math, config mutation, and the "no reconnect" guarantee) lives in
bot_engine.py and account_manager.py and is fully covered here.
"""

import unittest
from unittest.mock import MagicMock, patch

from bot_engine import (
    BotEngine,
    STRATEGY_MAGIC_MAP,
    RISK_PROFILE_DEFAULTS,
    RISK_OVERRIDE_MIN_PCT,
    RISK_OVERRIDE_MAX_PCT,
)
from account_manager import MultiAccountManager


class TestRiskProfileDefaults(unittest.TestCase):
    def test_all_six_active_pillars_have_a_risk_profile(self):
        """Test every active pillar in STRATEGY_MAGIC_MAP has a RISK_PROFILE_DEFAULTS entry."""
        for strat_id in STRATEGY_MAGIC_MAP:
            self.assertIn(strat_id, RISK_PROFILE_DEFAULTS)

    def test_risk_profile_modes_and_defaults_match_prior_hardcoded_values(self):
        """Test the profile table matches the exact percentages each pillar used before this
        feature existed, so the refactor is behavior-preserving with no override set."""
        expected = {
            "PULLBACK_DR_EKK":        (2.0, "STEP_UP_COMPOUNDING"),
            "RTM_M4_CONSERVATIVE":    (2.0, "STEP_UP_COMPOUNDING"),
            "RTM_M6_ELITE_GROWTH":    (2.0, "STEP_UP_COMPOUNDING"),
            "SMC_X_STO_H1":           (1.0, "FIXED"),
            "KC_LIQUIDITY_DOMINANCE": (1.5, "STEP_UP_COMPOUNDING"),
            "TUG_OF_WAR_M15":         (0.5, "FIXED"),
            "CONFLUENCE_SQUEEZE_M15": (0.5, "FIXED"),
        }
        for strat_id, (default_pct, mode) in expected.items():
            profile = RISK_PROFILE_DEFAULTS[strat_id]
            self.assertEqual(profile["default_pct"], default_pct)
            self.assertEqual(profile["mode"], mode)

    def test_override_bounds_are_sane(self):
        self.assertLess(RISK_OVERRIDE_MIN_PCT, RISK_OVERRIDE_MAX_PCT)
        self.assertGreater(RISK_OVERRIDE_MIN_PCT, 0.0)


class TestCalculateLotSizeRiskOverride(unittest.TestCase):
    def setUp(self):
        self.mock_connector = MagicMock()
        self.mock_connector.get_account_info.return_value = {"balance": 10000.0, "equity": 10000.0}
        self.config = {
            "mt5": {"symbol": "XAUUSDc", "magic_number": 555888},
            "strategy": {"strategy_mode": "ALL", "enable_step_up_compounding": False}
        }
        self.bot = BotEngine(self.mock_connector, self.config)

    def test_no_override_uses_default_percent_fixed_mode(self):
        """Test TUG_OF_WAR_M15 (FIXED mode) uses its 0.5% default when no override is set."""
        lot = self.bot.calculate_lot_size(2.00, strat_id="TUG_OF_WAR_M15")
        # 10000 * 0.5% = 50 risk USD; 50 / (2.00 * 100) = 0.25 lot
        self.assertAlmostEqual(lot, 0.25, places=2)

    def test_no_override_uses_default_percent_step_up_mode(self):
        """Test PULLBACK_DR_EKK (STEP_UP mode, disabled here) uses its 2.0% default balance-based sizing."""
        lot = self.bot.calculate_lot_size(2.00, strat_id="PULLBACK_DR_EKK")
        # Step-up disabled -> plain balance * 2% = 200 risk USD; 200 / (2.00*100) = 1.0 lot
        self.assertAlmostEqual(lot, 1.0, places=2)

    def test_override_changes_fixed_mode_lot_size(self):
        """Test a risk_overrides entry changes TUG_OF_WAR_M15's sizing (FIXED mode)."""
        self.config["strategy"]["risk_overrides"] = {"TUG_OF_WAR_M15": 1.0}
        lot = self.bot.calculate_lot_size(2.00, strat_id="TUG_OF_WAR_M15")
        # 10000 * 1.0% = 100 risk USD; 100 / (2.00*100) = 0.5 lot (double the 0.5% default)
        self.assertAlmostEqual(lot, 0.5, places=2)

    def test_override_changes_step_up_mode_lot_size(self):
        """Test a risk_overrides entry changes PULLBACK_DR_EKK's sizing (STEP_UP mode)."""
        self.config["strategy"]["risk_overrides"] = {"PULLBACK_DR_EKK": 0.5}
        lot = self.bot.calculate_lot_size(2.00, strat_id="PULLBACK_DR_EKK")
        # Step-up disabled -> balance * 0.5% = 50 risk USD; 50 / (2.00*100) = 0.25 lot
        self.assertAlmostEqual(lot, 0.25, places=2)

    def test_override_only_affects_the_targeted_strategy(self):
        """Test setting an override for one setup does not change another setup's sizing."""
        self.config["strategy"]["risk_overrides"] = {"TUG_OF_WAR_M15": 2.0}
        lot_smc = self.bot.calculate_lot_size(2.00, strat_id="SMC_X_STO_H1")
        # SMC_X_STO_H1 has no override -> stays at its 1.0% default = 100 risk USD -> 0.5 lot
        self.assertAlmostEqual(lot_smc, 0.5, places=2)

    def test_override_above_max_is_clamped(self):
        """Test an out-of-range override (e.g. reaching config.json through another path) is
        defensively clamped to RISK_OVERRIDE_MAX_PCT rather than applied verbatim."""
        self.config["strategy"]["risk_overrides"] = {"TUG_OF_WAR_M15": 999.0}
        lot = self.bot.calculate_lot_size(2.00, strat_id="TUG_OF_WAR_M15")
        expected_risk_money = 10000.0 * (RISK_OVERRIDE_MAX_PCT / 100.0)
        expected_lot = round(expected_risk_money / (2.00 * 100.0), 2)
        self.assertAlmostEqual(lot, expected_lot, places=2)

    def test_override_below_min_is_clamped(self):
        """Test a too-small positive override is clamped up to RISK_OVERRIDE_MIN_PCT."""
        self.config["strategy"]["risk_overrides"] = {"TUG_OF_WAR_M15": 0.001}
        lot = self.bot.calculate_lot_size(2.00, strat_id="TUG_OF_WAR_M15")
        expected_risk_money = 10000.0 * (RISK_OVERRIDE_MIN_PCT / 100.0)
        expected_lot = max(0.01, round(expected_risk_money / (2.00 * 100.0), 2))
        self.assertAlmostEqual(lot, expected_lot, places=2)

    def test_zero_or_negative_override_is_ignored_falls_back_to_default(self):
        """Test a non-positive override value is treated as unset (falls back to the default %)."""
        self.config["strategy"]["risk_overrides"] = {"TUG_OF_WAR_M15": 0.0}
        lot = self.bot.calculate_lot_size(2.00, strat_id="TUG_OF_WAR_M15")
        self.assertAlmostEqual(lot, 0.25, places=2)  # same as the no-override default case

    def test_retired_or_unknown_strategy_ignores_risk_overrides(self):
        """Test risk_overrides has no effect on a strategy outside RISK_PROFILE_DEFAULTS (retired/unknown)."""
        self.config["strategy"]["risk_overrides"] = {"NEWS_MOMENTUM_EXPANSION": 3.0}
        lot = self.bot.calculate_lot_size(2.00, strat_id="NEWS_MOMENTUM_EXPANSION")
        # Still the hardcoded 0.5% - retired setups don't participate in the override system
        self.assertAlmostEqual(lot, 0.25, places=2)


class TestAccountManagerRiskSettings(unittest.TestCase):
    def _make_manager(self):
        """Build a MultiAccountManager against an in-memory config (never touches the real
        config.json on disk - _save_to_config is patched out in every test below)."""
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
    def test_get_account_by_id_and_by_selected_default(self, _mock_save):
        mgr = self._make_manager()
        inst = mgr.get_account("acc_test_1")
        self.assertIsNotNone(inst)
        self.assertEqual(inst.id, "acc_test_1")

        # Omitting acc_id falls back to the currently selected account
        default_inst = mgr.get_account(None)
        self.assertIsNotNone(default_inst)
        self.assertEqual(default_inst.id, "acc_test_1")

    @patch.object(MultiAccountManager, "_save_to_config")
    def test_get_account_returns_none_for_unknown_id(self, _mock_save):
        mgr = self._make_manager()
        self.assertIsNone(mgr.get_account("does_not_exist"))

    @patch.object(MultiAccountManager, "_save_to_config")
    def test_update_strategy_settings_merges_into_live_config_without_restart(self, mock_save):
        """Test update_strategy_settings() writes risk_overrides into the account's strategy_cfg,
        that the SAME dict the running bot reads from (bot.config["strategy"] is strategy_cfg by
        reference), applies immediately with no restart, and persists via _save_to_config."""
        mgr = self._make_manager()
        inst = mgr.get_account("acc_test_1")
        connector_before = inst.connector  # identity check: must NOT be replaced

        ok = mgr.update_strategy_settings("acc_test_1", {"risk_overrides": {"TUG_OF_WAR_M15": 1.25}})
        self.assertTrue(ok)

        self.assertEqual(inst.strategy_cfg.get("risk_overrides"), {"TUG_OF_WAR_M15": 1.25})
        # bot.config["strategy"] must reflect the change immediately (same object / no restart)
        self.assertEqual(inst.bot.config["strategy"].get("risk_overrides"), {"TUG_OF_WAR_M15": 1.25})
        # The MT5 connector must NOT have been torn down and recreated for a strategy-only update
        self.assertIs(inst.connector, connector_before)
        self.assertIs(inst.bot.connector, connector_before)
        mock_save.assert_called()

    @patch.object(MultiAccountManager, "_save_to_config")
    def test_update_strategy_settings_returns_false_for_unknown_account(self, _mock_save):
        mgr = self._make_manager()
        ok = mgr.update_strategy_settings("no_such_account", {"risk_overrides": {"TUG_OF_WAR_M15": 1.0}})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
