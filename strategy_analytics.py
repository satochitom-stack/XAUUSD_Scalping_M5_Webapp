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
    
    # Strategy Catalog Definition (Bot Strategies Only)
    STRATEGY_REGISTRY = {
        "CAPTAIN_SMC_DUAL": {
            "id": "CAPTAIN_SMC_DUAL",
            "name": "Captain SMC Signal V1.2 (Dual Auto)",
            "icon": "⭐",
            "category": "SMC_PRO",
            "timeframe": "M5",
            "best_session": "London & NY (14:00 - 04:00)",
            "magic_numbers": [888120, 888121, 888122, 888123, 888124, 888125, 555888, 555889, 555890],
            "description": "ระบบ Smart Money Concept อัตโนมัติ เข้าทั้ง Fast (ไส้ปฏิเสธ S/R 35%) และ Confirmed (CHoCH Break) พร้อม Multi-TP"
        },
        "TKT_SMC_GOLD_PRO_M15": {
            "id": "TKT_SMC_GOLD_PRO_M15",
            "name": "TKT SMC Gold Pro v8.0 (M15)",
            "icon": "⚜️",
            "category": "SMC_M15",
            "timeframe": "M15",
            "best_session": "London & NY AM Kill Zones (14:00 - 23:00)",
            "magic_numbers": [999150, 999151, 999152],
            "description": "ระบบสถาบัน Confluence Score ≥ 60% กรอง FVG Imbalance + Order Block + Kill Zone บน M15"
        },
        "ASIAN_RANGE_SNIPER": {
            "id": "ASIAN_RANGE_SNIPER",
            "name": "Asian Range Sniper: Mean Reversion",
            "icon": "⛩️",
            "category": "MEAN_REVERSION",
            "timeframe": "M5",
            "best_session": "Asian Session (07:00 - 14:00)",
            "magic_numbers": [555888, 555889, 555890],
            "description": "สไนเปอร์กรอบตลาดเอเชีย แตะขอบ Bollinger Band + Fast RSI 7 ดีดกลับเข้าหา SMA 20"
        },
        "EMA50_3CANDLES_H1": {
            "id": "EMA50_3CANDLES_H1",
            "name": "EMA 50 + 3 Confirmation Candles (H1 Pro)",
            "icon": "📈",
            "category": "TREND_FOLLOWING",
            "timeframe": "H1",
            "best_session": "London & NY (14:00 - 04:00)",
            "magic_numbers": [777888, 777889, 777890],
            "description": "เทรดตามเทรนด์ H1 เมื่อเกิดแท่งเทียนสีเดียวกัน 3 แท่งติดเหนือ/ใต้เส้น EMA 50 + ความชัน"
        },
        "NEWS_MOMENTUM_EXPANSION": {
            "id": "NEWS_MOMENTUM_EXPANSION",
            "name": "News Momentum Expansion",
            "icon": "⚡",
            "category": "NEWS_TRADING",
            "timeframe": "M5",
            "best_session": "High-Impact News Events (USD)",
            "magic_numbers": [666888, 666889, 666890],
            "description": "ดักจับแท่งเทียน Breakout ความผันผวนสูงช่วงข่าวใหญ่ (CPI, NFP, FOMC) พร้อม Trailing Stop กว้าง"
        },
        "M1_SNIPER_CONFIRMATION": {
            "id": "M1_SNIPER_CONFIRMATION",
            "name": "M1 Sniper Confirmation (Refine Zone)",
            "icon": "🎯",
            "category": "SCALPING",
            "timeframe": "M1 (M15 Refined)",
            "best_session": "Early Asia & NY Session (07-10 & 19-23)",
            "magic_numbers": [444888, 444889, 444890],
            "description": "ย่อยโซน M15/M5 รอคอนเฟิร์ม M1 Internal BOS เข้าจุดคมกริบ SL แคบ 100-150 จุด ดัน R:R สูง 1:3 - 1:5 (Golfpy Framework)"
        },
        "FLASH_MICRO_SCALPER": {
            "id": "FLASH_MICRO_SCALPER",
            "name": "Flash Micro-Scalper (9 EMA Quick-Bite)",
            "icon": "⚡",
            "category": "SCALPING",
            "timeframe": "M5",
            "best_session": "All Sessions 24/5 (Asia/London/NY)",
            "magic_numbers": [333888, 333889, 333890],
            "description": "สายซิ่งเทรดได้ทุกตลาด เกาะคลื่น EMA 9 & สวนสั้น RSI 4 Exhaustion เน้นปิดเก็บคำเล็ก 70-120 จุด"
        }
    }

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

                    # FILTER: Only include deals created by Auto Bots
                    # (Magic Number > 0 or comment containing Bot identifiers)
                    is_bot_deal = False
                    comment_lower = (d.comment or "").lower()
                    
                    bot_magics = [555888, 555889, 555890, 777888, 777889, 777890]
                    if d.magic in bot_magics or d.magic > 10000:
                        is_bot_deal = True
                    elif any(k in comment_lower for k in ["gold_", "bot", "ea", "ema50", "smc", "asian", "squeeze", "ribbon"]):
                        is_bot_deal = True

                    if not is_bot_deal:
                        # Skip manual trade!
                        continue

                    close_time = datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")
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

            bot_magics = [555888, 555889, 555890, 777888, 777889, 777890, 333888, 333889, 333890]
            strategy_name_map = {
                "CAPTAIN_SMC_DUAL": "Captain SMC Signal V1.2 (Dual Auto)",
                "TKT_SMC_GOLD_PRO_M15": "TKT SMC Gold Pro v8.0 (M15)",
                "ASIAN_RANGE_SNIPER": "Asian Range Sniper: Mean Reversion",
                "EMA50_3CANDLES_H1": "EMA 50 + 3 Confirmation Candles (H1 Pro)",
                "NEWS_MOMENTUM_EXPANSION": "News Momentum Expansion",
                "M1_SNIPER_CONFIRMATION": "M1 Sniper Confirmation (Refine Zone)",
                "FLASH_MICRO_SCALPER": "Flash Micro-Scalper (9 EMA Quick-Bite)"
            }

            for pid, p in positions.items():
                if not p["out"] or not p["in"]:
                    continue

                in_deal = p["in"][0]
                out_deals = p["out"]
                last_out = out_deals[-1]

                is_bot = (in_deal.magic in bot_magics) or (in_deal.magic > 10000)
                comment_lower = (in_deal.comment or "").lower() + " " + (last_out.comment or "").lower()
                if any(k in comment_lower for k in ["gold_", "bot", "ea", "ema50", "smc", "asian", "squeeze", "ribbon", "flash"]):
                    is_bot = True

                # Apply mode filter
                if resolved_mode == "manual" and is_bot:
                    continue
                if resolved_mode == "bot" and not is_bot:
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
        """Classify deal into respective strategy."""
        magic = deal.magic
        comment = (deal.comment or "").lower()

        # 0. TKT SMC Gold Pro v8.0 (Magic 999150..999155 or comment tkt / fvg / score)
        if (magic >= 999150 and magic <= 999155) or "tkt" in comment or "fvg" in comment or "m15" in comment:
            return "TKT_SMC_GOLD_PRO_M15"

        # 0.1 Captain SMC Signal V1.2 (Magic 888120..888125 or comment Captain_SMC)
        if (magic >= 888120 and magic <= 888125) or "captain" in comment:
            return "CAPTAIN_SMC_DUAL"

        # 1. H1 Strategy (Magic 777888, 777889, 777890 or comment containing H1 / EMA50)
        if magic in [777888, 777889, 777890] or "h1" in comment or "ema50" in comment:
            return "EMA50_3CANDLES_H1"

        # 2. Asian Range Sniper (00:00 - 07:00 Server / 07:00 - 14:00 Thai)
        if "asian" in comment or "⛩" in comment:
            return "ASIAN_RANGE_SNIPER"

        # 3. News Momentum Expansion (News Spike)
        if "news" in comment or "momentum" in comment or magic in [666888, 666889, 666890]:
            return "NEWS_MOMENTUM_EXPANSION"

        # 4. M1 Sniper Confirmation (Golfpy Framework)
        if "m1" in comment or "sniper" in comment or magic in [444888, 444889, 444890]:
            return "M1_SNIPER_CONFIRMATION"

        # 5. Flash Micro-Scalper (Quick-Bite)
        if "flash" in comment or magic in [333888, 333889, 333890]:
            return "FLASH_MICRO_SCALPER"

        # Default classification based on deal time if opened by M5 EA
        if magic in [555888, 555889, 555890]:
            deal_hour = datetime.fromtimestamp(deal.time).hour
            if 0 <= deal_hour < 7:
                return "ASIAN_RANGE_SNIPER"
            else:
                return "CAPTAIN_SMC_DUAL"

        return "CAPTAIN_SMC_DUAL"

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
                "avg_rr": "1:1.5",
                "status": "รอไม้บอท (0 Trades)",
                "recent_deals": []
            }

        total_gross_profit = 0.0
        total_gross_loss = 0.0
        total_bot_profit = 0.0
        total_wins = 0
        total_losses = 0

        # Accumulate real bot deals only
        for d in deals:
            st_id = d["strategy_id"]
            if st_id not in setups_data:
                st_id = "SECRET_EMA_PULLBACK"

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

            if len(st["recent_deals"]) < 10:
                st["recent_deals"].append(d)

        # Compute Winrate and Profit Factor for each strategy
        for st in setups_data.values():
            if st["total_trades"] > 0:
                st["winrate_pct"] = round((st["wins"] / st["total_trades"]) * 100.0, 1)
                st["profit_factor"] = round((st["gross_profit"] / (st["gross_loss"] + 1e-9)), 2) if st["gross_loss"] > 0 else (round(st["gross_profit"], 2) if st["gross_profit"] > 0 else 0.0)
                st["status"] = f"บอทเทรดแล้ว ({st['total_trades']} ไม้)"
            else:
                st["winrate_pct"] = 0.0
                st["profit_factor"] = 0.0
                st["status"] = "รอไม้บอท (0 Trades)"

        # Set active status tags based on session
        now_hour = datetime.now().hour
        is_asian = (7 <= now_hour < 14)
        if "ASIAN_RANGE_SNIPER" in setups_data:
            setups_data["ASIAN_RANGE_SNIPER"]["status"] = "🟢 ACTIVE (ตลาดเอเชีย)" if is_asian else "⚪ STANDBY (เอเชีย 07-14)"
        if "CAPTAIN_SMC_DUAL" in setups_data:
            setups_data["CAPTAIN_SMC_DUAL"]["status"] = "🟢 ACTIVE (London/NY)"
        if "TKT_SMC_GOLD_PRO_M15" in setups_data:
            setups_data["TKT_SMC_GOLD_PRO_M15"]["status"] = "🟢 ACTIVE (M15 Confluence)"
        if "EMA50_3CANDLES_H1" in setups_data:
            setups_data["EMA50_3CANDLES_H1"]["status"] = "🟢 MONITORING (H1 Bar)"

        total_trades = len(deals)
        overall_winrate = round((total_wins / total_trades * 100.0), 1) if total_trades > 0 else 0.0
        bot_profit_factor = round((total_gross_profit / (total_gross_loss + 1e-9)), 2) if total_gross_loss > 0 else 0.0

        # Sort setups
        setups_list = list(setups_data.values())
        setups_list.sort(key=lambda s: (s["total_trades"], s["winrate_pct"]), reverse=True)
        
        # Best setup from real bot trades
        traded_setups = [s for s in setups_list if s["total_trades"] > 0]
        best_setup = max(traded_setups, key=lambda s: s["winrate_pct"]) if traded_setups else setups_list[0]

        return {
            "overview": {
                "data_source": "100% REAL BOT DEALS (บันทึกเฉพาะไม้ที่บอทเทรดจริง)",
                "total_trades": total_trades,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "overall_winrate_pct": overall_winrate,
                "total_net_profit": total_bot_profit,
                "profit_factor": bot_profit_factor,
                "best_setup_name": best_setup["name"],
                "best_setup_winrate": best_setup["winrate_pct"],
                "best_setup_icon": best_setup["icon"]
            },
            "setups": setups_list,
            "real_deals_journal": deals # all real bot deals
        }

    def get_summary(self) -> dict:
        """Alias for get_real_stats_summary."""
        return self.get_real_stats_summary()

# Alias for backwards compatibility
StrategyAnalyticsManager = RealTradeAnalyticsManager
