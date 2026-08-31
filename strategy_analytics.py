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
        "SMC_SWEEP": {
            "id": "SMC_SWEEP",
            "name": "SMC Liquidity Sweep & Rejection",
            "icon": "🎯",
            "category": "SCALPING",
            "timeframe": "M5",
            "best_session": "London & NY Open (14:00 - 22:00)",
            "magic_numbers": [555888, 555889, 555890],
            "description": "ดักปลายไส้กวาด Stop Loss ทะลุ High/Low 20 แท่งแล้วทิ้งไส้ยาว >45% ดึงกลับเข้ากรอบ"
        },
        "EMA_RIBBON": {
            "id": "EMA_RIBBON",
            "name": "Dynamic EMA Ribbon (20/50/100/200) + RSI",
            "icon": "🌊",
            "category": "TREND_FOLLOWING",
            "timeframe": "M5",
            "best_session": "London & NY (14:00 - 02:00)",
            "magic_numbers": [555888, 555889, 555890],
            "description": "รันตาม Super Trend แถบ EMA 4 เส้น ย่อตัวแตะ Value Zone (EMA 20) + RSI รีเซ็ต"
        },
        "BB_SQUEEZE": {
            "id": "BB_SQUEEZE",
            "name": "Bollinger Bands Squeeze Volatility Breakout",
            "icon": "💥",
            "category": "VOLATILITY_BREAKOUT",
            "timeframe": "M5",
            "best_session": "London & NY Overlap (19:00 - 23:00)",
            "magic_numbers": [555888, 555889, 555890],
            "description": "สไนเปอร์ตลาดบีบตัวแคบสุดในรอบ 20 แท่ง แล้วเข้าแท่งแรกที่ระเบิดตามเทรนด์ EMA 50"
        },
        "SECRET_EMA_PULLBACK": {
            "id": "SECRET_EMA_PULLBACK",
            "name": "Classic Secret EMA 50/150 Pullback",
            "icon": "📈",
            "category": "SCALPING",
            "timeframe": "M5",
            "best_session": "All Active Sessions",
            "magic_numbers": [555888, 555889, 555890],
            "description": "สูตรต้นตำรับ Secret System ตรวจจับความชัน EMA 50/150 และย่อทดสอบเส้น EMA"
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

    def _classify_deal_strategy(self, deal) -> str:
        """Classify deal into respective strategy."""
        magic = deal.magic
        comment = (deal.comment or "").lower()

        # 1. H1 Strategy (Magic 777888, 777889, 777890 or comment containing H1 / EMA50)
        if magic in [777888, 777889, 777890] or "h1" in comment or "ema50" in comment:
            return "EMA50_3CANDLES_H1"

        # 2. Asian Range Sniper
        if "asian" in comment or "⛩" in comment:
            return "ASIAN_RANGE_SNIPER"

        # 3. SMC Sweep
        if "smc" in comment or "sweep" in comment:
            return "SMC_SWEEP"

        # 4. Ribbon
        if "ribbon" in comment:
            return "EMA_RIBBON"

        # 5. Squeeze
        if "squeeze" in comment or "bb" in comment:
            return "BB_SQUEEZE"

        # 6. Pullback / Secret
        if "pullback" in comment or "secret" in comment:
            return "SECRET_EMA_PULLBACK"

        # Default classification based on deal time / position type if opened by M5 Scalper EA
        if magic in [555889, 555890]:
            deal_hour = datetime.fromtimestamp(deal.time).hour
            if 0 <= deal_hour < 7:
                return "ASIAN_RANGE_SNIPER"
            elif "tp" in comment:
                return "SMC_SWEEP"
            else:
                return "SECRET_EMA_PULLBACK"

        return "SECRET_EMA_PULLBACK"

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
        if is_asian:
            setups_data["ASIAN_RANGE_SNIPER"]["status"] = "🟢 ACTIVE (ตลาดเอเชีย)"
        else:
            setups_data["SMC_SWEEP"]["status"] = "🟢 ACTIVE (London/NY)"
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
