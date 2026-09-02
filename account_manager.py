"""
Multi-Account & Multi-Bot Portfolio Manager for XAUUSD Scalping M5 WebApp
Automatically synchronizes with live active MT5 terminals on Windows and manages Strategy Analytics.
"""

import os
import json
import logging
import uuid
from datetime import datetime
from mt5_connector import MT5Connector
from bot_engine import GoldScalpingBot
from line_notifier import LineNotifier
from strategy_analytics import StrategyAnalyticsManager
from strategy_optimizer import RealTimeStrategyOptimizer
from exit_benchmark_tracker import ExitBenchmarkTracker
from regime_liquidity_scorer import MarketRegimeScorer

logger = logging.getLogger("AccountManager")

class AccountInstance:
    """Represents a single MT5 Account (either Bot or Manual Trading)."""
    def __init__(self, acc_dict: dict, global_config: dict):
        self.id = acc_dict.get("id", str(uuid.uuid4())[:8])
        self.name = acc_dict.get("name", "Account " + self.id)
        self.type = acc_dict.get("type", "BOT") # "BOT" or "MANUAL"
        self.login = acc_dict.get("login", 0)
        self.password = acc_dict.get("password", "")
        self.server = acc_dict.get("server", "")
        self.path = acc_dict.get("path", "")
        self.symbol = acc_dict.get("symbol", "XAUUSDc")
        self.magic_number = acc_dict.get("magic_number", 555888)
        self.simulation_mode = acc_dict.get("simulation_mode", False)

        # Merge strategy settings with overrides
        self.strategy_cfg = dict(global_config.get("strategy", {}))
        if "strategy" in acc_dict and isinstance(acc_dict["strategy"], dict):
            self.strategy_cfg.update(acc_dict["strategy"])

        # Connector and Bot Engine
        acc_mt5_config = {
            "mt5": {
                "account": self.login,
                "password": self.password,
                "server": self.server,
                "path": self.path,
                "symbol": self.symbol,
                "magic_number": self.magic_number,
                "simulation_mode": self.simulation_mode
            }
        }
        self.connector = MT5Connector(acc_mt5_config)
        
        # Auto-sync with live connected MT5 account if available
        if self.connector.is_connected and self.login == 0:
            live_acc = self.connector.get_account_info()
            if live_acc.get("login"):
                self.login = live_acc["login"]
                self.server = live_acc.get("server", self.server)
                self.name = f"Exness ({self.login})"

        self.bot_config = {
            "mt5": {
                "account": self.login,
                "password": self.password,
                "server": self.server,
                "path": self.path,
                "symbol": self.symbol,
                "magic_number": self.magic_number
            },
            "strategy": self.strategy_cfg,
            "line_notification": global_config.get("line_notification", {})
        }
        self.bot = GoldScalpingBot(self.connector, self.bot_config)
        self.bot.account_name = self.name

    def to_dict(self, mask_password: bool = True) -> dict:
        """Serialize account metadata."""
        acc_info = self.connector.get_account_info()
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "login": acc_info.get("login") if acc_info.get("connected") else self.login,
            "password": "******" if (mask_password and self.password) else self.password,
            "server": acc_info.get("server") if acc_info.get("connected") else self.server,
            "path": self.path,
            "symbol": self.symbol,
            "magic_number": self.magic_number,
            "simulation_mode": self.simulation_mode,
            "is_running": self.bot.is_running if self.type == "BOT" else False,
            "status": self.bot.bot_status if self.type == "BOT" else "MANUAL MONITOR",
            "strategy": self.strategy_cfg
        }

    def get_live_state(self) -> dict:
        """Get live balance, positions, bot status directly from MT5."""
        acc_info = self.connector.get_account_info()
        positions = self.connector.get_open_positions()

        return {
            "profile": self.to_dict(),
            "account": acc_info,
            "bot": {
                "is_running": self.bot.is_running,
                "status": self.bot.bot_status,
                "consecutive_losses": self.bot.consecutive_losses,
                "consecutive_wins": self.bot.consecutive_wins,
                "latest_trend": self.bot.latest_trend,
                "fast_ema": self.bot.fast_ema_val,
                "slow_ema": self.bot.slow_ema_val,
                "fast_slope": self.bot.fast_slope,
                "slow_slope": self.bot.slow_slope,
                "last_signal": self.bot.last_signal
            },
            "positions": positions,
            "logs": self.bot.logs[:20]
        }


class MultiAccountManager:
    """Manages the pool of MT5 accounts, bot instances, and strategy performance analytics."""
    def __init__(self, global_config: dict):
        self.global_config = global_config
        self.accounts = {}
        self.selected_account_id = None
        self.notifier = LineNotifier(self.global_config.get("line_notification", {}))
        self.analytics = StrategyAnalyticsManager()
        self.optimizer = RealTimeStrategyOptimizer()
        self.benchmark_tracker = ExitBenchmarkTracker()
        self.scorer = MarketRegimeScorer()

        # Initialize accounts from config
        self._load_accounts()

    def _load_accounts(self):
        acc_list = self.global_config.get("accounts", [])
        if not acc_list:
            acc_list = [
                {
                    "id": "acc_live_1",
                    "name": "Live MT5 Terminal",
                    "type": "BOT",
                    "login": 0,
                    "server": "",
                    "symbol": "XAUUSDc",
                    "magic_number": 555888
                }
            ]

        for a in acc_list:
            inst = AccountInstance(a, self.global_config)
            inst.bot.notifier = self.notifier
            self.accounts[inst.id] = inst
            # Auto-start bot accounts on startup (vital for headless VPS runs)
            if inst.type == "BOT" and a.get("auto_start", True):
                inst.bot.start()
                logger.info(f"🚀 [AUTO-START] Bot Engine auto-started for account {inst.name} (#{inst.login})")

        if self.accounts:
            self.selected_account_id = list(self.accounts.keys())[0]

    def add_account(self, acc_dict: dict) -> AccountInstance:
        """Add a new account to the pool."""
        inst = AccountInstance(acc_dict, self.global_config)
        inst.bot.notifier = self.notifier
        self.accounts[inst.id] = inst
        self.selected_account_id = inst.id
        self._save_to_config()
        logger.info(f"Added Account #{inst.id} ({inst.name}) Type={inst.type}")
        return inst

    def update_account(self, acc_id: str, updates: dict) -> bool:
        """Update existing account settings."""
        if acc_id in self.accounts:
            inst = self.accounts[acc_id]
            if "name" in updates and updates["name"]: inst.name = updates["name"]
            if "type" in updates and updates["type"]: inst.type = updates["type"]
            if "login" in updates and updates["login"] is not None: inst.login = updates["login"]
            if "password" in updates and updates["password"]: inst.password = updates["password"]
            if "server" in updates and updates["server"]: inst.server = updates["server"]
            if "path" in updates and updates["path"]: inst.path = updates["path"]
            if "symbol" in updates and updates["symbol"]: inst.symbol = updates["symbol"]
            if "magic_number" in updates and updates["magic_number"]: inst.magic_number = updates["magic_number"]
            if "strategy" in updates and isinstance(updates["strategy"], dict):
                inst.strategy_cfg.update(updates["strategy"])
                inst.bot.update_config({"strategy": inst.strategy_cfg})

            # Re-init connector
            acc_mt5_config = {
                "mt5": {
                    "account": inst.login,
                    "password": inst.password,
                    "server": inst.server,
                    "path": inst.path,
                    "symbol": inst.symbol,
                    "magic_number": inst.magic_number
                }
            }
            inst.connector = MT5Connector(acc_mt5_config)
            inst.bot.connector = inst.connector
            self._save_to_config()
            return True
        return False

    def delete_account(self, acc_id: str) -> bool:
        """Delete an account from the pool."""
        if acc_id in self.accounts:
            if self.accounts[acc_id].bot.is_running:
                self.accounts[acc_id].bot.stop()
            del self.accounts[acc_id]
            if self.selected_account_id == acc_id:
                self.selected_account_id = list(self.accounts.keys())[0] if self.accounts else None
            self._save_to_config()
            return True
        return False

    def select_account(self, acc_id: str) -> bool:
        """Change currently active account view."""
        if acc_id in self.accounts:
            self.selected_account_id = acc_id
            return True
        return False

    def start_bot(self, acc_id: str) -> bool:
        """Start bot for specific account."""
        if acc_id in self.accounts:
            inst = self.accounts[acc_id]
            if inst.type == "BOT":
                inst.bot.start()
                return True
        return False

    def stop_bot(self, acc_id: str) -> bool:
        """Stop bot for specific account."""
        if acc_id in self.accounts:
            self.accounts[acc_id].bot.stop()
            return True
        return False

    def start_all_bots(self):
        """Master Start: start all bot-enabled accounts."""
        for inst in self.accounts.values():
            if inst.type == "BOT" and not inst.bot.is_running:
                inst.bot.start()

    def stop_all_bots(self):
        """Master Stop: stop all bots."""
        for inst in self.accounts.values():
            if inst.bot.is_running:
                inst.bot.stop()

    def emergency_close_all_for_account(self, acc_id: str) -> int:
        """Close all orders for a specific account."""
        if acc_id in self.accounts:
            inst = self.accounts[acc_id]
            return inst.connector.close_all_positions(inst.magic_number)
        return 0

    def run_all_bots_iteration(self):
        """Iterate all active bots."""
        for inst in self.accounts.values():
            if inst.type == "BOT" and inst.bot.is_running:
                try:
                    inst.bot.run_iteration()
                except Exception as e:
                    logger.error(f"Error running bot on account {inst.name}: {e}")

    def get_portfolio_summary(self) -> dict:
        """Calculate total aggregate portfolio stats."""
        total_balance = 0.0
        total_equity = 0.0
        total_profit = 0.0
        total_positions = 0
        active_bots = 0
        accounts_list = []

        for inst in self.accounts.values():
            acc_info = inst.connector.get_account_info()
            positions = inst.connector.get_open_positions()

            bal = acc_info.get("balance", 0.0)
            eq = acc_info.get("equity", 0.0)
            pnl = acc_info.get("profit", 0.0)

            total_balance += bal
            total_equity += eq
            total_profit += pnl
            total_positions += len(positions)
            if inst.type == "BOT" and inst.bot.is_running:
                active_bots += 1

            accounts_list.append({
                "id": inst.id,
                "name": inst.name,
                "type": inst.type,
                "login": acc_info.get("login", inst.login),
                "server": acc_info.get("server", inst.server),
                "currency": acc_info.get("currency", "USD"),
                "balance": bal,
                "equity": eq,
                "profit": pnl,
                "positions_count": len(positions),
                "is_running": inst.bot.is_running if inst.type == "BOT" else False,
                "status": inst.bot.bot_status if inst.type == "BOT" else "MANUAL"
            })

        return {
            "portfolio": {
                "total_accounts": len(self.accounts),
                "active_bots": active_bots,
                "total_balance": round(total_balance, 2),
                "total_equity": round(total_equity, 2),
                "total_profit": round(total_profit, 2),
                "total_open_positions": total_positions
            },
            "accounts": accounts_list,
            "selected_account_id": self.selected_account_id
        }

    def get_selected_account_state(self) -> dict:
        """Get full state for currently selected account including strategy analytics."""
        if not self.selected_account_id or self.selected_account_id not in self.accounts:
            if self.accounts:
                self.selected_account_id = list(self.accounts.keys())[0]
            else:
                return {}

        inst = self.accounts[self.selected_account_id]
        state = inst.get_live_state()

        # Add market & portfolio summary
        sym_info = inst.connector.get_symbol_info(inst.symbol)
        state["market"] = {
            "symbol": sym_info.get("symbol", inst.symbol),
            "ask": sym_info.get("ask", 0.0),
            "bid": sym_info.get("bid", 0.0),
            "spread": sym_info.get("spread", 0.0),
            "max_spread": inst.strategy_cfg.get("max_spread_points", 35.0)
        }
        state["portfolio"] = self.get_portfolio_summary()["portfolio"]
        state["accounts_list"] = self.get_portfolio_summary()["accounts"]
        state["line"] = {
            "enabled": self.notifier.enabled
        }
        state["strategy_stats"] = self.analytics.get_summary()
        
        # Sync closed deals to optimizer and exit benchmark tracker
        deals = self.analytics.fetch_real_history_from_mt5()
        if deals:
            self.optimizer.sync_mt5_closed_deals(deals)
            if inst.type == "BOT" and hasattr(inst.bot, "optimizer"):
                inst.bot.optimizer.sync_mt5_closed_deals(deals)
            
            for deal in deals:
                ticket = deal.get("order") or deal.get("ticket")
                pnl = deal.get("net_profit", deal.get("profit", 0.0))
                reason = deal.get("comment", "")
                self.benchmark_tracker.on_trade_closed(ticket, pnl, reason)
                if inst.type == "BOT" and hasattr(inst.bot, "benchmark_tracker"):
                    inst.bot.benchmark_tracker.on_trade_closed(ticket, pnl, reason)

        state["learning_stats"] = self.optimizer.get_dashboard_summary()
        state["benchmark_stats"] = self.benchmark_tracker.get_benchmark_summary()
        
        # Calculate live Market Regime & Liquidity Quality Score (0-100)
        rates = inst.connector.get_rates(inst.symbol, "M5", 30)
        spread = sym_info.get("spread", 0.0)
        strat_mode = inst.strategy_cfg.get("strategy_mode", "ALL")
        if inst.type == "BOT" and hasattr(inst.bot, "scorer"):
            state["regime_score"] = inst.bot.scorer.evaluate_market_confluence(rates, spread, strat_mode)
        else:
            state["regime_score"] = self.scorer.evaluate_market_confluence(rates, spread, strat_mode)

        return state

    def _save_to_config(self):
        """Save account pool to config.json."""
        acc_list = []
        for inst in self.accounts.values():
            acc_list.append({
                "id": inst.id,
                "name": inst.name,
                "type": inst.type,
                "login": inst.login,
                "password": inst.password,
                "server": inst.server,
                "path": inst.path,
                "symbol": inst.symbol,
                "magic_number": inst.magic_number,
                "simulation_mode": inst.simulation_mode,
                "strategy": inst.strategy_cfg
            })
        self.global_config["accounts"] = acc_list
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.global_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save accounts to config: {e}")
