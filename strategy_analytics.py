"""
Real-Trade Analytics & Live History Journal Engine for MT5
Fetches and calculates 100% REAL Bot trade execution statistics directly from MetaTrader 5 deal history.
EXCLUDES all manual / non-bot trades.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("RealTradeAnalytics")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


class RealTradeAnalyticsManager:
    """Parses live MT5 deal history and generates verified trade statistics for BOT trades only."""
    
    # Strategy Catalog Definition (Bot Strategies Only - Elite 4 Pillars)
    STRATEGY_REGISTRY = {
        "ASIAN_RANGE_SNIPER": {
            "id": "ASIAN_RANGE_SNIPER",
            "name": "Asian Range Sniper: Mean Reversion",
            "icon": "⛩️",
            "category": "MEAN_REVERSION",
            "timeframe": "M5",
            "best_session": "Asian Session (07:00 - 14:00)",
            "magic_numbers": [555820, 555821, 555822, 555823, 555888, 555889, 555890],
            "avg_rr": "1:1.8",
            "description": "สไนเปอร์กรอบตลาดเอเชีย แตะขอบ Bollinger Band + Fast RSI 7 ดีดกลับเข้าหา SMA 20 (Win Rate 66.7% / DD 2.9%)"
        },
        "RTM_M4_CONSERVATIVE": {
            "id": "RTM_M4_CONSERVATIVE",
            "name": "RTM Quasimodo M4 (Conservative)",
            "icon": "🛡️",
            "category": "RTM_PRO",
            "timeframe": "M15 (H1 Filter)",
            "best_session": "London & NY (14:00 - 23:00)",
            "magic_numbers": [777004, 777014, 777024, 777034],
            "avg_rr": "1:2.0",
            "description": "RTM Quasimodo + ICT + Fib 61.8-78.6% (เกรด A/A+ เท่านั้น | ความเสี่ยงคงที่ 1.0% | TP 2.0R)"
        },
        "RTM_M5_ALL_WEATHER": {
            "id": "RTM_M5_ALL_WEATHER",
            "name": "RTM Quasimodo M5 (All-Weather)",
            "icon": "🌊",
            "category": "RTM_PRO",
            "timeframe": "M15 (H1 Filter)",
            "best_session": "London & NY (14:00 - 23:00)",
            "magic_numbers": [777005, 777015, 777025, 777035],
            "avg_rr": "1:2.0",
            "description": "RTM Quasimodo รองรับทุกสภาพตลาด (ความเสี่ยงสูงสุด 1.0%, เกรด B=0.5%, A/A+=1.0% | TP 2.0R)"
        },
        "RTM_M6_ELITE_GROWTH": {
            "id": "RTM_M6_ELITE_GROWTH",
            "name": "RTM Quasimodo M6 (Elite Growth)",
            "icon": "👑",
            "category": "RTM_PRO",
            "timeframe": "M15 (H1 Filter)",
            "best_session": "London & NY (14:00 - 23:00)",
            "magic_numbers": [777006, 777016, 777026, 777036],
            "avg_rr": "1:2.0",
            "description": "RTM Elite Confluence คัดเฉพาะไม้คุณภาพสูง (เกรด A=1.0%, A+=2.0% | TP 2.0R | Quick Harvest)"
        },
        "RTM_M7_MAX_ALPHA": {
            "id": "RTM_M7_MAX_ALPHA",
            "name": "RTM Quasimodo M7 (Max Alpha)",
            "icon": "🎯",
            "category": "RTM_PRO",
            "timeframe": "M15 (H1 Filter)",
            "best_session": "London & NY (14:00 - 23:00)",
            "magic_numbers": [777007, 777017, 777027, 777037],
            "avg_rr": "1:3.5",
            "description": "RTM Elite Confluence รันเทรนด์เป้าไกล (เกรด A=1.0%, A+=2.0% | TP 3.5R | Trend Runner)"
        },
        "SMC_X_STO_H1": {
            "id": "SMC_X_STO_H1",
            "name": "SMCxSTO ระบบปีศาจ (H1 Devil System)",
            "icon": "😈",
            "category": "SMC_PRO",
            "timeframe": "H1",
            "best_session": "London & NY (14:00 - 04:00)",
            "magic_numbers": [555770, 555771, 555772, 555773],
            "avg_rr": "1:2.0",
            "description": "ระบบ SMCxSTO กฎข้อเดียว: เทรนด์ EMA 50/200 + โซน Discount/Premium (ATR) + Order Block + Stochastic Oversold/Overbought"
        },
        "NEWS_MOMENTUM_EXPANSION": {
            "id": "NEWS_MOMENTUM_EXPANSION",
            "name": "News Momentum Expansion",
            "icon": "⚡",
            "category": "NEWS_TRADING",
            "timeframe": "M5",
            "best_session": "High-Impact News Events (USD)",
            "magic_numbers": [555890, 555891, 555892, 555893, 666888, 666889, 666890],
            "avg_rr": "1:1.8",
            "description": "ดักจับแท่งเทียน Breakout ความผันผวนสูงช่วงข่าวใหญ่ (CPI, NFP, FOMC) พร้อม Trailing Stop กว้าง"
        }
    }

    # Allowed Magic Numbers for Elite 4 Pillars (7 active models)
    ELITE_MAGIC_NUMBERS = {
        777004, 777014, 777024, 777034,  # RTM M4
        777005, 777015, 777025, 777035,  # RTM M5
        777006, 777016, 777026, 777036,  # RTM M6
        777007, 777017, 777027, 777037,  # RTM M7
        555770, 555771, 555772, 555773,  # SMC x STO H1
        555820, 555821, 555822, 555823,  # Asian Range Sniper
        555890, 555891, 555892, 555893, 666888, 666889, 666890  # News Momentum Expansion
    }
    
    # System Epoch Cutoff: Start recording fresh from 2026-09-07 15:00:00 (Today's update)
    EPOCH_START_TIME = datetime(2026, 9, 7, 15, 0, 0)

    def __init__(self, connector=None):
        self.connector = connector

    def fetch_real_history_from_mt5(self, days: int = 90) -> List[dict]:
        """Fetch real closed trade deals executed ONLY BY BOTS from MT5."""
        closed_deals = []
        if not MT5_AVAILABLE:
            return closed_deals

        try:
            if not mt5.terminal_info():
                mt5.initialize()

            from_date = datetime.now() - timedelta(days=days)
            to_date = datetime.now() + timedelta(days=1)
            deals = mt5.history_deals_get(from_date, to_date)
            if deals:
                for d in deals:
                    # Filter out non-trade entries and non-symbol deals
                    if d.entry not in [1, 2, 3] or not d.symbol:
                        continue

                    # FILTER 1: Time Cutoff (Only deals from system epoch 2026-09-07 15:00:00 onwards)
                    deal_dt = datetime.fromtimestamp(d.time)
                    if deal_dt < self.EPOCH_START_TIME:
                        continue

                    # FILTER 2: Only include deals created by Elite 4 Pillars Auto Bots
                    if d.magic not in self.ELITE_MAGIC_NUMBERS:
                        continue

                    close_time = deal_dt.strftime("%Y-%m-%d %H:%M:%S")
                    strategy_id = self._classify_deal_strategy(d)

                    closed_deals.append({
                        "ticket": d.ticket,
                        "order": d.order,
                        "symbol": d.symbol,
                        "type": "BUY" if d.type == 0 else ("SELL" if d.type == 1 else "CLOSE"),
                        "volume": round(d.volume, 2),
                        "price": round(d.price, 3),
                        "profit": round(float(d.profit), 2),
                        "commission": round(float(d.commission), 2),
                        "swap": round(float(d.swap), 2),
                        "net_profit": round(float(d.profit + d.commission + d.swap), 2),
                        "magic": d.magic,
                        "comment": d.comment or "",
                        "time": close_time,
                        "strategy_id": strategy_id
                    })
        except Exception as e:
            logger.error(f"Error fetching MT5 history deals: {e}")

        # Sort descending by time
        closed_deals.sort(key=lambda x: x["time"], reverse=True)
        return closed_deals

    def fetch_trades_for_journal(self, days: int = 90, mode: str = "auto", user: Optional[str] = None) -> List[dict]:
        """
        Fetch closed positions from MT5 formatted specifically for FXLOG PRO (Trade Journal).
        Supports:
        - mode='manual': Manual trades executed by user (@TOM, magic == 0 or non-bot).
        - mode='bot': Trades executed by MT5 Bots (7 Secret System setups).
        - mode='auto': Auto-detect based on user name or active connected MT5 account.
        """
        journal_trades = []
        if not MT5_AVAILABLE:
            return journal_trades

        try:
            manual_mt5_path = r"C:\Users\Windows11\AppData\Local\Programs\MetaTrader 5 EXNESS 2\terminal64.exe"
            is_manual_request = (mode and mode.lower() == "manual") or (user and ("tom" in user.lower() or "manual" in user.lower()))

            if is_manual_request and os.path.exists(manual_mt5_path):
                if not mt5.terminal_info() or getattr(mt5.account_info(), 'login', 0) != 257508244:
                    mt5.shutdown()
                    mt5.initialize(path=manual_mt5_path)
            else:
                if not mt5.terminal_info():
                    mt5.initialize()

            acc_info = mt5.account_info()
            active_login = acc_info.login if acc_info else 0

            # Determine mode if auto
            resolved_mode = mode.lower()
            if resolved_mode == "auto":
                if user and ("tom" in user.lower() or "manual" in user.lower()):
                    resolved_mode = "manual"
                elif active_login == 257508244: # Tom's Manual Trading Account
                    resolved_mode = "manual"
                elif active_login == 159415028: # Auto Bot Account
                    resolved_mode = "bot"
                elif user and "bot" in user.lower():
                    resolved_mode = "bot"
                else:
                    resolved_mode = "all"

            from_date = datetime.now() - timedelta(days=days)
            to_date = datetime.now() + timedelta(days=1)
            deals = mt5.history_deals_get(from_date, to_date)
            if not deals:
                return journal_trades

            # Group deals by position_id to pair Entry (IN) and Exit (OUT)
            positions = {}
            for d in deals:
                if not d.position_id or not d.symbol:
                    continue
                pid = d.position_id
                if pid not in positions:
                    positions[pid] = {
                        "in": [],
                        "out": [],
                        "symbol": d.symbol,
                        "magic": d.magic,
                        "comment": d.comment or ""
                    }
                if d.entry == 0:
                    positions[pid]["in"].append(d)
                elif d.entry in [1, 2, 3]:
                    positions[pid]["out"].append(d)

            strategy_name_map = {
                # 🟢 4 เสาหลัก (Active Models Only)
                "ASIAN_RANGE_SNIPER": "Asian Range Sniper: Mean Reversion",
                "RTM_M4_CONSERVATIVE": "RTM Quasimodo M4 (Conservative)",
                "RTM_M5_ALL_WEATHER": "RTM Quasimodo M5 (All-Weather)",
                "RTM_M6_ELITE_GROWTH": "RTM Quasimodo M6 (Elite Growth)",
                "RTM_M7_MAX_ALPHA": "RTM Quasimodo M7 (Max Alpha)",
                "SMC_X_STO_H1": "SMC x STO Devil (H1 Devil System)",
                "NEWS_MOMENTUM_EXPANSION": "News Momentum Expansion (Spikes)"
            }

            for pid, p in positions.items():
                if not p["out"] or not p["in"]:
                    continue

                in_deal = p["in"][0]
                out_deals = p["out"]
                last_out = out_deals[-1]

                is_bot = (in_deal.magic in self.ELITE_MAGIC_NUMBERS) or (in_deal.magic > 10000)
                comment_lower = (in_deal.comment or "").lower() + " " + (last_out.comment or "").lower()
                if any(k in comment_lower for k in ["gold_", "bot", "ea", "ema50", "smc", "asian", "squeeze", "ribbon", "flash", "rtm", "devil"]):
                    is_bot = True

                # Apply mode filter
                if resolved_mode == "manual" and is_bot:
                    continue
                if resolved_mode == "bot" and not is_bot:
                    continue

                # For Bot Trades: Enforce fresh epoch cutoff and elite magic numbers
                close_dt = datetime.fromtimestamp(last_out.time)
                if is_bot:
                    if close_dt < self.EPOCH_START_TIME:
                        continue
                    if in_deal.magic not in self.ELITE_MAGIC_NUMBERS:
                        continue

                # Calculate financials
                entry_price = round(float(in_deal.price), 3)
                exit_price = round(float(last_out.price), 3)
                volume = round(float(in_deal.volume), 2)
                net_pnl = round(float(sum(od.profit + od.commission + od.swap for od in out_deals)), 2)

                trade_type = "BUY" if in_deal.type == 0 else "SELL"
                sym = in_deal.symbol
                clean_pair = "XAU/USD" if "XAU" in sym.upper() or "GOLD" in sym.upper() else sym

                open_dt = datetime.fromtimestamp(in_deal.time)
                close_dt = datetime.fromtimestamp(last_out.time)
                open_str = open_dt.strftime("%Y-%m-%d %H:%M")
                close_str = close_dt.strftime("%Y-%m-%d %H:%M")

                # Session calculation
                hour = close_dt.hour
                if 6 <= hour < 14:
                    session_str = "Asia Session (06:00-14:00)"
                elif 14 <= hour < 19:
                    session_str = "London Session (14:00-19:00)"
                else:
                    session_str = "New York Session (19:00-04:00)"

                # Fetch history orders for this position to get exact TP and SL
                pos_orders = mt5.history_orders_get(position=pid)
                sl_val = None
                tp_val = None
                if pos_orders:
                    for po in pos_orders:
                        if po.sl > 0 and sl_val is None:
                            sl_val = round(float(po.sl), 3)
                        if po.tp > 0 and tp_val is None:
                            tp_val = round(float(po.tp), 3)

                # Determine status & R:R
                price_diff = abs(exit_price - entry_price)
                if net_pnl > 0:
                    status_val = "WIN"
                elif net_pnl < 0:
                    if sl_val and abs(exit_price - sl_val) > 0.5:
                        status_val = "CUT"
                    elif price_diff < 1.5:
                        status_val = "CUT"
                    else:
                        status_val = "LOSS"
                else:
                    status_val = "BE"

                # Calculate R:R Ratio as float number only if SL was actually set
                rr_ratio_val = None
                if sl_val and abs(entry_price - sl_val) > 0:
                    risk = abs(entry_price - sl_val)
                    reward = abs(tp_val - entry_price) if tp_val else price_diff
                    rr_ratio_val = round(reward / risk, 1)

                if is_bot:
                    strat_key = self._classify_deal_strategy(in_deal)
                    strat_name = strategy_name_map.get(strat_key, strat_key)
                    trade_id = f"bot-mt5-{pid}"
                    notes_str = f"🤖 MT5 Bot Deal #{pid} | Magic: {in_deal.magic} | {in_deal.comment or last_out.comment or ''}".strip()
                    mental_tags = ["🤖 Automated Bot Trade"]
                    technique_str = strat_name
                    psychology_str = "มั่นใจตามแผน (Executed Setup)"
                else:
                    trade_id = f"manual-mt5-{pid}"
                    notes_str = f"✋ MT5 Manual Trade #{pid} | Vol: {volume} | Net: ${net_pnl:+,.2f}"
                    mental_tags = ["🎯 Manual Trade"]
                    # User selects their own setup/technique in the journal!
                    technique_str = "-"
                    psychology_str = "มีวินัยตามแผน (Manual Trade)"

                journal_trades.append({
                    "id": trade_id,
                    "ticket": pid,
                    "magic": int(in_deal.magic or 0),
                    "pair": clean_pair,
                    "type": trade_type,
                    "entryPrice": entry_price,
                    "exitPrice": exit_price,
                    "lotSize": volume,
                    "tp": tp_val,
                    "sl": sl_val,
                    "profit": net_pnl,
                    "status": status_val,
                    "rrRatio": rr_ratio_val,
                    "date": close_str,
                    "openDate": open_str,
                    "closeDate": close_str,
                    "closedAt": close_str,
                    "technique": technique_str,
                    "timeframe": "M5",
                    "session": session_str,
                    "notes": notes_str,
                    "mentalTags": mental_tags,
                    "disciplineStatus": "system",
                    "psychology": psychology_str
                })

        except Exception as e:
            logger.error(f"Error fetching trades for journal: {e}")

        # Sort descending by close date
        journal_trades.sort(key=lambda x: x["closeDate"], reverse=True)
        return journal_trades

    def fetch_open_positions_for_journal(self, user: Optional[str] = None) -> List[dict]:
        """
        Fetch currently ACTIVE / OPEN positions from MT5 formatted for FXLOG PRO.
        Used exclusively in "บันทึกการเทรดใหม่" (New Trade View) to log ongoing live trades.
        """
        open_trades = []
        if not MT5_AVAILABLE:
            return open_trades

        try:
            manual_mt5_path = r"C:\Users\Windows11\AppData\Local\Programs\MetaTrader 5 EXNESS 2\terminal64.exe"
            is_manual_request = (user and ("tom" in user.lower() or "manual" in user.lower())) or True # default to manual if available

            if is_manual_request and os.path.exists(manual_mt5_path):
                if not mt5.terminal_info() or getattr(mt5.account_info(), 'login', 0) != 257508244:
                    mt5.shutdown()
                    mt5.initialize(path=manual_mt5_path)
            else:
                if not mt5.terminal_info():
                    mt5.initialize()

            positions = mt5.positions_get()
            if not positions:
                return open_trades

            for p in positions:
                # Map Symbol
                sym_clean = p.symbol.upper()
                if "XAU" in sym_clean or "GOLD" in sym_clean:
                    pair_str = "XAU/USD"
                elif "EURUSD" in sym_clean:
                    pair_str = "EUR/USD"
                elif "GBPUSD" in sym_clean:
                    pair_str = "GBP/USD"
                elif "USDJPY" in sym_clean:
                    pair_str = "USD/JPY"
                elif "BTC" in sym_clean:
                    pair_str = "BTC/USD"
                else:
                    pair_str = p.symbol

                pos_type = "BUY" if p.type == 0 else "SELL"
                entry_price = round(float(p.price_open), 3 if "JPY" in pair_str or "XAU" in pair_str else 5)
                current_price = round(float(p.price_current), 3 if "JPY" in pair_str or "XAU" in pair_str else 5)
                sl_val = round(float(p.sl), 3 if "JPY" in pair_str or "XAU" in pair_str else 5) if p.sl > 0 else None
                tp_val = round(float(p.tp), 3 if "JPY" in pair_str or "XAU" in pair_str else 5) if p.tp > 0 else None
                volume = round(float(p.volume), 2)
                profit = round(float(p.profit + getattr(p, "swap", 0.0)), 2)

                dt_open = datetime.fromtimestamp(p.time)
                date_str = dt_open.strftime("%Y-%m-%d %H:%M")

                open_hour = dt_open.hour
                if 6 <= open_hour < 14:
                    session_str = "Asia Session (06:00-14:00)"
                elif 14 <= open_hour < 19:
                    session_str = "London Session (14:00-19:00)"
                else:
                    session_str = "New York Session (19:00-04:00)"

                open_trades.append({
                    "ticket": p.ticket,
                    "id": f"mt5-open-{p.ticket}",
                    "pair": pair_str,
                    "type": pos_type,
                    "lotSize": volume,
                    "entryPrice": entry_price,
                    "currentPrice": current_price,
                    "exitPrice": None,
                    "sl": sl_val,
                    "tp": tp_val,
                    "profit": profit,
                    "date": date_str,
                    "openDate": date_str,
                    "session": session_str,
                    "timeframe": "M5",
                    "status": "ACTIVE",
                    "isClosed": False,
                    "magic": p.magic,
                    "comment": p.comment or ""
                })

            return open_trades
        except Exception as e:
            logger.error(f"Error fetching open positions for journal: {e}")
            return []

    def _classify_deal_strategy(self, deal) -> str:
        """Classify deal into respective Elite 4 Pillars strategy."""
        magic = deal.magic
        comment = (deal.comment or "").lower()

        # 1. Active: RTM Quasimodo Multi-Model Setups (M4, M5, M6, M7)
        if magic in [777004, 777014, 777024, 777034] or "rtm_m4" in comment or "m4_cons" in comment:
            return "RTM_M4_CONSERVATIVE"
        if magic in [777005, 777015, 777025, 777035] or "rtm_m5" in comment or "m5_allw" in comment:
            return "RTM_M5_ALL_WEATHER"
        if magic in [777006, 777016, 777026, 777036] or "rtm_m6" in comment or "m6_elite" in comment:
            return "RTM_M6_ELITE_GROWTH"
        if magic in [777007, 777017, 777027, 777037] or "rtm_m7" in comment or "m7_alpha" in comment:
            return "RTM_M7_MAX_ALPHA"
        if "rtm" in comment or "quasimodo" in comment:
            return "RTM_M6_ELITE_GROWTH"

        # 2. Active: SMCxSTO ระบบปีศาจ (H1 Devil System by SMC by Bossz)
        if "sto" in comment or "devil" in comment or "smcxsto" in comment or (555770 <= magic <= 555773):
            return "SMC_X_STO_H1"

        # 3. Active: High-Impact News Momentum Expansion (News Spike)
        if "news" in comment or "goldm5_pro" in comment or (555889 <= magic <= 555893) or magic in [666888, 666889, 666890]:
            return "NEWS_MOMENTUM_EXPANSION"

        # 4. Active: Asian Range Sniper
        if "asian" in comment or "⛩" in comment or "gold_asian" in comment or (555820 <= magic <= 555823):
            return "ASIAN_RANGE_SNIPER"

        return "RTM_M5_ALL_WEATHER"

    def get_real_stats_summary(self) -> dict:
        """Calculate 100% verified real trading statistics for BOTS ONLY from MT5 deal history."""
        deals = self.fetch_real_history_from_mt5(days=90)
        
        # Initialize stats per strategy
        setups_data = {}
        for k, v in self.STRATEGY_REGISTRY.items():
            setups_data[k] = {
                "id": v["id"],
                "name": v["name"],
                "icon": v["icon"],
                "category": v["category"],
                "timeframe": v["timeframe"],
                "best_session": v["best_session"],
                "description": v["description"],
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "winrate_pct": 0.0,
                "total_profit_money": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "profit_factor": 0.0,
                "avg_rr": v.get("avg_rr", "1:2.0"),
                "status": "🟢 บอทรันพร้อมเทรด (0 ไม้)",
                "recent_deals": []
            }

        total_gross_profit = 0.0
        total_gross_loss = 0.0
        total_bot_profit = 0.0
        total_wins = 0
        total_losses = 0

        # Fetch Account balance for realistic Drawdown % calculation
        acc_balance = 11000.0
        if MT5_AVAILABLE:
            try:
                acc = mt5.account_info()
                if acc and getattr(acc, 'balance', 0) > 0:
                    acc_balance = float(acc.balance)
            except Exception:
                pass

        # Collect deals per strategy for individual Drawdown calculation
        strat_deals = {k: [] for k in setups_data}

        # Accumulate real bot deals only
        for d in deals:
            st_id = d["strategy_id"]
            if st_id not in setups_data:
                st_id = "RTM_M5_ALL_WEATHER"

            st = setups_data[st_id]
            profit = d["net_profit"]
            st["total_trades"] += 1
            st["total_profit_money"] = round(st["total_profit_money"] + profit, 2)
            total_bot_profit = round(total_bot_profit + profit, 2)

            if profit > 0:
                st["wins"] += 1
                total_wins += 1
                st["gross_profit"] = round(st["gross_profit"] + profit, 2)
                total_gross_profit = round(total_gross_profit + profit, 2)
            elif profit < 0:
                st["losses"] += 1
                total_losses += 1
                st["gross_loss"] = round(st["gross_loss"] + abs(profit), 2)
                total_gross_loss = round(total_gross_loss + abs(profit), 2)

            strat_deals[st_id].append(d)
            if len(st["recent_deals"]) < 10:
                st["recent_deals"].append(d)

        # Compute Winrate, Profit Factor, and Drawdown for each strategy
        for k, st in setups_data.items():
            if st["total_trades"] > 0:
                st["winrate_pct"] = round((st["wins"] / st["total_trades"]) * 100.0, 1)
                st["profit_factor"] = round((st["gross_profit"] / (st["gross_loss"] + 1e-9)), 2) if st["gross_loss"] > 0 else (99.99 if st["gross_profit"] > 0 else 0.0)
                st["status"] = f"บอทเทรดแล้ว ({st['total_trades']} ไม้)"

                # Realized RR and Exit Stages Breakdown
                target_rr = 3.5 if k == "RTM_M7_MAX_ALPHA" else (2.0 if ("RTM_" in k or k == "SMC_X_STO_H1") else (1.8 if k in ["NEWS_MOMENTUM_EXPANSION", "ASIAN_RANGE_SNIPER"] else 2.0))
                risk_per_lot = 850.0 if "RTM_" in k else (900.0 if k == "SMC_X_STO_H1" else (500.0 if k == "ASIAN_RANGE_SNIPER" else 700.0))
                
                stages = {"full_tp": 0, "trailing_lock": 0, "mid_profit": 0, "break_even": 0, "full_sl": 0, "early_cut": 0}
                total_realized_r = 0.0
                
                for deal_item in strat_deals[k]:
                    d_profit = deal_item["net_profit"]
                    d_lot = deal_item.get("volume", 0.01) or 0.01
                    d_risk = max(d_lot * risk_per_lot, 1.0)
                    r_val = round(d_profit / d_risk, 2)
                    total_realized_r += r_val
                    
                    if r_val >= (target_rr - 0.2):
                        stages["full_tp"] += 1
                    elif r_val >= (1.6 if target_rr >= 3.0 else 0.75):
                        stages["trailing_lock"] += 1
                    elif r_val >= 0.4:
                        stages["mid_profit"] += 1
                    elif r_val >= -0.15:
                        stages["break_even"] += 1
                    elif r_val <= -0.85:
                        stages["full_sl"] += 1
                    else:
                        stages["early_cut"] += 1

                st["avg_realized_rr"] = round(total_realized_r / st["total_trades"], 1)
                st["target_rr"] = target_rr
                st["exit_stages"] = stages

                # Calculate real Peak-to-Trough Drawdown
                s_deals = sorted(strat_deals[k], key=lambda x: x["time"])
                s_cum = 0.0
                s_peak = 0.0
                s_max_dd_usd = 0.0
                for deal_item in s_deals:
                    s_cum += deal_item["net_profit"]
                    if s_cum > s_peak:
                        s_peak = s_cum
                    dd_val = s_peak - s_cum
                    if dd_val > s_max_dd_usd:
                        s_max_dd_usd = dd_val

                st["max_drawdown_usd"] = round(s_max_dd_usd, 2)
                st["max_drawdown_pct"] = round((s_max_dd_usd / acc_balance) * 100.0, 2) if acc_balance > 0 else 0.0
            else:
                st["winrate_pct"] = 0.0
                st["profit_factor"] = 0.0
                st["avg_realized_rr"] = 0.0
                st["target_rr"] = 3.5 if k == "RTM_M7_MAX_ALPHA" else (2.0 if ("RTM_" in k or k == "SMC_X_STO_H1") else (1.8 if k in ["NEWS_MOMENTUM_EXPANSION", "ASIAN_RANGE_SNIPER"] else 2.0))
                st["exit_stages"] = {"full_tp": 0, "trailing_lock": 0, "mid_profit": 0, "break_even": 0, "full_sl": 0, "early_cut": 0}
                st["max_drawdown_usd"] = 0.0
                st["max_drawdown_pct"] = 0.0
                st["status"] = "🟢 บอทรันพร้อมเทรด (0 ไม้)"

        # Set active status tags based on session
        now_hour = datetime.now().hour
        is_asian = (7 <= now_hour < 14)
        if "ASIAN_RANGE_SNIPER" in setups_data:
            setups_data["ASIAN_RANGE_SNIPER"]["status"] = "🟢 ACTIVE (ตลาดเอเชีย 07-14)" if is_asian else "⚪ STANDBY (เอเชีย 07-14)"
        if "RTM_M4_CONSERVATIVE" in setups_data:
            setups_data["RTM_M4_CONSERVATIVE"]["status"] = "🟢 ACTIVE (Confluence Grade A/A+)"
        if "RTM_M5_ALL_WEATHER" in setups_data:
            setups_data["RTM_M5_ALL_WEATHER"]["status"] = "🟢 ACTIVE (All-Weather Grade B/A/A+)"
        if "RTM_M6_ELITE_GROWTH" in setups_data:
            setups_data["RTM_M6_ELITE_GROWTH"]["status"] = "🟢 ACTIVE (Elite Growth 2.0R)"
        if "RTM_M7_MAX_ALPHA" in setups_data:
            setups_data["RTM_M7_MAX_ALPHA"]["status"] = "🟢 ACTIVE (Max Alpha 3.5R)"
        if "SMC_X_STO_H1" in setups_data:
            setups_data["SMC_X_STO_H1"]["status"] = "🟢 ACTIVE (Devil H1 OB+STO)"
        if "NEWS_MOMENTUM_EXPANSION" in setups_data:
            setups_data["NEWS_MOMENTUM_EXPANSION"]["status"] = "⚪ STANDBY (รอจังหวะข่าว USD)"

        total_trades = len(deals)
        overall_winrate = round((total_wins / total_trades * 100.0), 1) if total_trades > 0 else 0.0
        bot_profit_factor = round((total_gross_profit / (total_gross_loss + 1e-9)), 2) if total_gross_loss > 0 else (99.99 if total_gross_profit > 0 else 0.0)

        # Calculate Overall Portfolio Max Drawdown from closed deals
        sorted_all_deals = sorted(deals, key=lambda x: x["time"])
        port_cum = 0.0
        port_peak = 0.0
        port_max_dd_usd = 0.0
        for d in sorted_all_deals:
            port_cum += d["net_profit"]
            if port_cum > port_peak:
                port_peak = port_cum
            d_drop = port_peak - port_cum
            if d_drop > port_max_dd_usd:
                port_max_dd_usd = d_drop

        port_max_dd_pct = round((port_max_dd_usd / acc_balance) * 100.0, 2) if (acc_balance > 0 and total_trades > 0) else 0.0

        # Sort setups
        setups_list = list(setups_data.values())
        setups_list.sort(key=lambda s: (s["total_trades"], s["winrate_pct"]), reverse=True)
        
        # Best setup from real bot trades
        traded_setups = [s for s in setups_list if s["total_trades"] > 0]
        best_setup = max(traded_setups, key=lambda s: (s["winrate_pct"], s["total_profit_money"])) if traded_setups else None

        return {
            "overview": {
                "data_source": "100% REAL BOT DEALS (บันทึกเฉพาะไม้ที่บอทเทรดจริง)",
                "total_trades": total_trades,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "overall_winrate_pct": overall_winrate,
                "total_net_profit": total_bot_profit,
                "profit_factor": bot_profit_factor,
                "max_drawdown_pct": port_max_dd_pct,
                "max_drawdown_usd": round(port_max_dd_usd, 2),
                "best_setup_name": best_setup["name"] if best_setup else "รอประเดิมสถิติ (รอปิดไม้แรก)",
                "best_setup_winrate": best_setup["winrate_pct"] if best_setup else 0.0,
                "best_setup_icon": best_setup["icon"] if best_setup else "🎯"
            },
            "setups": setups_list,
            "real_deals_journal": deals # all real bot deals
        }

    def get_summary(self) -> dict:
        """Alias for get_real_stats_summary."""
        return self.get_real_stats_summary()

# Alias for backwards compatibility
StrategyAnalyticsManager = RealTradeAnalyticsManager
