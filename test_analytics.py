import sys
import json
from strategy_analytics import RealTradeAnalyticsManager

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

mgr = RealTradeAnalyticsManager()
res = mgr.get_real_stats_summary()

print("=== REAL MT5 OVERVIEW ===")
print(json.dumps(res['overview'], indent=2, ensure_ascii=False))

print("\n=== REAL SETUPS BREAKDOWN ===")
for s in res['setups']:
    print(f"{s['icon']} {s['name']}: {s['total_trades']} Trades ({s['wins']}W / {s['losses']}L) | Winrate: {s['winrate_pct']}% | Net: {s['total_profit_money']} | PF: {s['profit_factor']}")

print("\n=== RECENT REAL CLOSED DEALS IN MT5 ===")
for d in res['real_deals_journal'][:8]:
    print(f"#{d['ticket']} | {d['time']} | {d['symbol']} {d['type']} {d['volume']} | PnL: {d['net_profit']} | Strat: {d['strategy_id']} | Comment: {d['comment']}")
