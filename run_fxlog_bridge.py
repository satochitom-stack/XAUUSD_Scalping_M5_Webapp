"""
FXLOG PRO - Local MT5 Journal Bridge
Runs on http://127.0.0.1:8000
Bridges MT5 manual trading deals to FXLOG PRO (https://trade-journal-1.vercel.app/)
Safe: Zero automated trading / bot logic. Read-only journal bridge.
"""
import sys
import os
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from strategy_analytics import RealTradeAnalyticsManager

app = FastAPI(title="FXLOG PRO MT5 Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_pna_header(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    from fastapi.responses import Response
    response = Response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

analytics = RealTradeAnalyticsManager()

@app.get("/")
def index():
    return {"service": "FXLOG PRO MT5 Bridge", "status": "online"}

@app.get("/api/journal/closed_trades")
async def get_closed_trades(
    days: int = Query(3, description="Days of history"),
    mode: str = Query("manual", description="Mode"),
    user: str = Query("TOM", description="Target user")
):
    trades = analytics.fetch_trades_for_journal(days=days, mode=mode, user=user)
    return {
        "status": True,
        "mode": mode,
        "user": user,
        "count": len(trades),
        "trades": trades
    }

@app.get("/api/journal/open_positions")
async def get_open_positions_for_journal(user: str = Query("TOM", description="Target user")):
    """Fetch live active / open positions from MT5 to auto-fill NewTradeView in FXLOG PRO."""
    open_trades = analytics.fetch_open_positions_for_journal(user=user)
    return {
        "status": True,
        "user": user,
        "count": len(open_trades),
        "trades": open_trades
    }

@app.get("/api/status")
async def get_status():
    import MetaTrader5 as mt5
    acc = mt5.account_info() if mt5.terminal_info() else None
    return {
        "status": "online",
        "service": "FXLOG PRO MT5 Bridge",
        "account": acc.login if acc else None,
        "balance": acc.balance if acc else 0.0,
        "currency": acc.currency if acc else "USD"
    }

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("[!] Failed to initialize MT5. Please make sure MT5 is open.")
    else:
        acc = mt5.account_info()
        print("\n=======================================================")
        print("[*] FXLOG PRO - Local MT5 Journal Bridge")
        if acc:
            print(f"[OK] Connected to MT5 Account: #{acc.login} ({acc.server})")
            print(f"[*] Balance: {acc.balance} {acc.currency}")
        print("[*] Listening on: http://127.0.0.1:8000")
        print("[*] Mode: READ-ONLY (No bot trading, purely for Journal sync)")
        print("=======================================================\n")

    uvicorn.run(app, host="127.0.0.1", port=8000)
