"""
FastAPI Server & Multi-Account Command Hub for XAUUSD Scalping M5 Secret System
Supports unlimited MT5 accounts (Auto Bot & Manual Trading accounts) with Token Protection.
"""

import os
import sys
import json
import logging
import threading
import time

try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException, Depends, status, Request, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from account_manager import MultiAccountManager

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("WebApp")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "templates", "index.html")

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

app_config = load_config()

# Initialize Multi-Account Portfolio Manager
account_manager = MultiAccountManager(app_config)

# Background Multi-Bot Runner Thread
bot_thread_running = True

def background_portfolio_worker():
    """Background worker loop executing all active bots in parallel."""
    logger.info("Multi-Account Bot Runner background worker thread started.")
    while bot_thread_running:
        try:
            account_manager.run_all_bots_iteration()
        except Exception as e:
            logger.error(f"Error in background multi-bot worker: {e}")
        time.sleep(3.0)

# Start background thread
bot_thread = threading.Thread(target=background_portfolio_worker, daemon=True)
bot_thread.start()

# FastAPI App
app = FastAPI(title="XAUUSD Scalping M5 Multi-Account Hub", version="2.0.0")

from fastapi.middleware.cors import CORSMiddleware

# Enable CORS for Trade Journal web app and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- TOKEN AUTHENTICATION DEPENDENCY ---
def verify_token(x_access_token: Optional[str] = Header(None), token: Optional[str] = None):
    """Verify Access Token against authorized tokens list in config."""
    auth_cfg = app_config.get("auth", {})
    if not auth_cfg.get("require_token", True):
        return True

    valid_tokens = auth_cfg.get("access_tokens", ["GOLD_VIP_2026"])
    submitted_token = x_access_token or token

    if not submitted_token or submitted_token not in valid_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Access Token. Please authenticate."
        )
    return True

# --- MODELS ---
class TokenVerifyRequest(BaseModel):
    token: str

class AddAccountRequest(BaseModel):
    name: Optional[str] = "New Account"
    type: Optional[str] = "BOT" # "BOT" or "MANUAL"
    login: Optional[int] = 0
    password: Optional[str] = ""
    server: Optional[str] = ""
    path: Optional[str] = ""
    symbol: Optional[str] = "XAUUSD"
    magic_number: Optional[int] = 555888
    simulation_mode: Optional[bool] = False
    strategy: Optional[dict] = {}

class UpdateAccountRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    path: Optional[str] = None
    symbol: Optional[str] = None
    magic_number: Optional[int] = None
    simulation_mode: Optional[bool] = None
    strategy: Optional[dict] = None

class LineConfigRequest(BaseModel):
    enabled: bool
    channel_access_token: Optional[str] = ""
    user_id: Optional[str] = ""
    notify_token: Optional[str] = ""
    notify_on_open: Optional[bool] = True
    notify_on_close: Optional[bool] = True
    notify_on_be: Optional[bool] = True
    notify_on_safety: Optional[bool] = True

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the Web Dashboard HTML page directly."""
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH)
    return HTMLResponse("<h2>Error: templates/index.html not found</h2>", status_code=404)

@app.post("/api/auth/verify")
async def verify_auth_token(payload: TokenVerifyRequest):
    """Verify if the entered token is valid."""
    auth_cfg = app_config.get("auth", {})
    valid_tokens = auth_cfg.get("access_tokens", ["GOLD_VIP_2026"])
    if payload.token in valid_tokens:
        return {"status": True, "message": "Authentication successful"}
    return JSONResponse(status_code=401, content={"status": False, "message": "Invalid Access Token"})

@app.get("/api/config")
async def get_app_config(_: bool = Depends(verify_token)):
    """Return application configuration."""
    return app_config

@app.get("/api/status")
async def get_system_status(_: bool = Depends(verify_token)):
    """Fetch complete live state for currently selected account + portfolio summary."""
    return account_manager.get_selected_account_state()

@app.get("/api/accounts")
async def list_accounts(_: bool = Depends(verify_token)):
    """Get list of all accounts."""
    return account_manager.get_portfolio_summary()

@app.post("/api/accounts/select/{acc_id}")
async def select_active_account(acc_id: str, _: bool = Depends(verify_token)):
    """Switch active account view."""
    success = account_manager.select_account(acc_id)
    if success:
        return {"status": True, "selected_id": acc_id}
    raise HTTPException(status_code=404, detail="Account ID not found")

@app.post("/api/accounts/add")
async def add_new_account(payload: AddAccountRequest, _: bool = Depends(verify_token)):
    """Add a new account profile (Bot or Manual)."""
    try:
        inst = account_manager.add_account(payload.model_dump())
        return {"status": True, "account": inst.to_dict()}
    except Exception as e:
        logger.error(f"Error adding account: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/accounts/update/{acc_id}")
async def update_account_profile(acc_id: str, payload: UpdateAccountRequest, _: bool = Depends(verify_token)):
    """Update existing account settings."""
    try:
        success = account_manager.update_account(acc_id, payload.model_dump(exclude_unset=True))
        if success:
            return {"status": True, "message": "Account updated successfully"}
        raise HTTPException(status_code=404, detail="Account ID not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/accounts/{acc_id}")
async def delete_account_profile(acc_id: str, _: bool = Depends(verify_token)):
    """Delete an account profile."""
    success = account_manager.delete_account(acc_id)
    if success:
        return {"status": True, "message": "Account deleted successfully"}
    raise HTTPException(status_code=404, detail="Account ID not found")

# --- BOT CONTROLS ---

@app.post("/api/accounts/{acc_id}/start")
async def start_account_bot(acc_id: str, _: bool = Depends(verify_token)):
    """Start bot for specific account."""
    success = account_manager.start_bot(acc_id)
    if success:
        return {"status": True, "message": "Bot started for account"}
    raise HTTPException(status_code=400, detail="Failed to start bot or account is Manual type")

@app.post("/api/accounts/{acc_id}/stop")
async def stop_account_bot(acc_id: str, _: bool = Depends(verify_token)):
    """Stop bot for specific account."""
    success = account_manager.stop_bot(acc_id)
    if success:
        return {"status": True, "message": "Bot stopped for account"}
    raise HTTPException(status_code=400, detail="Failed to stop bot")

@app.post("/api/accounts/start_all")
async def start_all_bots(_: bool = Depends(verify_token)):
    """Master Start: start all bot accounts."""
    account_manager.start_all_bots()
    return {"status": True, "message": "All bots started"}

@app.post("/api/accounts/stop_all")
async def stop_all_bots(_: bool = Depends(verify_token)):
    """Master Stop: stop all bots."""
    account_manager.stop_all_bots()
    return {"status": True, "message": "All bots stopped"}

@app.post("/api/accounts/{acc_id}/close_all")
async def emergency_close_all_for_acc(acc_id: str, _: bool = Depends(verify_token)):
    """Emergency close all positions for specific account."""
    count = account_manager.emergency_close_all_for_account(acc_id)
    return {"status": True, "closed_count": count}

@app.post("/api/positions/close/{ticket}")
async def close_position_by_ticket(ticket: int, _: bool = Depends(verify_token)):
    """Close position on selected account."""
    sel_id = account_manager.selected_account_id
    if sel_id and sel_id in account_manager.accounts:
        inst = account_manager.accounts[sel_id]
        success = inst.connector.close_position(ticket)
        if success:
            return {"status": True, "message": f"Position #{ticket} closed"}
    raise HTTPException(status_code=400, detail=f"Failed to close position #{ticket}")

# --- LINE NOTIFICATION API ---
@app.post("/api/line/config")
async def update_line_config(payload: LineConfigRequest, _: bool = Depends(verify_token)):
    """Save LINE notification configuration."""
    if "line_notification" not in app_config:
        app_config["line_notification"] = {}

    app_config["line_notification"]["enabled"] = payload.enabled
    app_config["line_notification"]["channel_access_token"] = payload.channel_access_token
    app_config["line_notification"]["user_id"] = payload.user_id
    app_config["line_notification"]["notify_token"] = payload.notify_token
    app_config["line_notification"]["notify_on_open"] = payload.notify_on_open
    app_config["line_notification"]["notify_on_close"] = payload.notify_on_close
    app_config["line_notification"]["notify_on_be"] = payload.notify_on_be
    app_config["line_notification"]["notify_on_safety"] = payload.notify_on_safety

    save_config(app_config)
    account_manager.notifier.update_config(app_config["line_notification"])
    for inst in account_manager.accounts.values():
        inst.bot.notifier.update_config(app_config["line_notification"])
    return {"status": True, "message": "LINE settings saved successfully"}

@app.post("/api/line/test")
async def send_line_test(_: bool = Depends(verify_token)):
    """Trigger a test message to LINE."""
    res = account_manager.notifier.send_test_notification()
    if res.get("status"):
        return res
    return JSONResponse(status_code=400, content=res)

@app.get("/api/strategy/stats")
async def get_strategy_performance_stats(_: bool = Depends(verify_token)):
    """Fetch aggregated and per-setup strategy performance analytics."""
    return account_manager.analytics.get_summary()

@app.get("/api/strategy/learning_stats")
async def get_strategy_learning_stats(_: bool = Depends(verify_token)):
    """Fetch real-time AI win/loss learning feedback and dynamic parameter scorecard."""
    return account_manager.optimizer.get_dashboard_summary()

@app.post("/api/strategy/learning/reset")
async def reset_strategy_learning(_: bool = Depends(verify_token)):
    """Reset AI learning memory back to factory defaults."""
    account_manager.optimizer.reset_learning()
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "optimizer"):
            inst.bot.optimizer.reset_learning()
    return {"status": True, "message": "AI Real-Time Learning Memory Reset Successfully"}

@app.post("/api/strategy/learning/toggle")
async def toggle_strategy_learning(_: bool = Depends(verify_token)):
    """Toggle AI Real-Time Adaptive Learning Mode."""
    account_manager.optimizer.enabled = not account_manager.optimizer.enabled
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "optimizer"):
            inst.bot.optimizer.enabled = account_manager.optimizer.enabled
    status_str = "ENABLED" if account_manager.optimizer.enabled else "DISABLED"
    return {"status": True, "enabled": account_manager.optimizer.enabled, "message": f"AI Learning {status_str}"}

# --- ECONOMIC NEWS RADAR API ---
@app.get("/api/news/calendar")
async def get_economic_news_calendar(_: bool = Depends(verify_token)):
    """Get live economic news status and upcoming high impact events."""
    return {
        "status": account_manager.optimizer.news_calendar.get_news_status(),
        "upcoming": account_manager.optimizer.news_calendar.get_upcoming_events(10)
    }

@app.post("/api/news/sync")
async def sync_economic_news_calendar(_: bool = Depends(verify_token)):
    """Force re-generate and sync weekly economic news calendar."""
    account_manager.optimizer.news_calendar.generate_weekly_calendar()
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "optimizer"):
            inst.bot.optimizer.news_calendar.generate_weekly_calendar()
    return {"status": True, "message": "Economic news calendar synced successfully"}

# --- EXIT STRATEGY A/B BENCHMARK API (Trailing Stop vs Multi-Stage TP1/2/3) ---
@app.get("/api/benchmark/exit_stats")
async def get_exit_benchmark_stats(_: bool = Depends(verify_token)):
    """Fetch comparative analytics: Trailing Stop vs Multi-Stage TP1/2/3."""
    return account_manager.benchmark_tracker.get_benchmark_summary()

@app.post("/api/benchmark/toggle_mode")
async def toggle_exit_execution_mode(_: bool = Depends(verify_token)):
    """Toggle execution mode between TRAILING_STOP and MULTI_STAGE_TP."""
    curr = account_manager.benchmark_tracker.execution_exit_mode
    new_mode = "MULTI_STAGE_TP" if curr == "TRAILING_STOP" else "TRAILING_STOP"
    account_manager.benchmark_tracker.execution_exit_mode = new_mode
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "benchmark_tracker"):
            inst.bot.benchmark_tracker.execution_exit_mode = new_mode
    account_manager.benchmark_tracker.save_state()
    return {"status": True, "execution_exit_mode": new_mode, "message": f"Exit Execution Mode switched to {new_mode}"}

@app.post("/api/benchmark/reset")
async def reset_exit_benchmark_stats(_: bool = Depends(verify_token)):
    """Reset Exit Benchmark comparison history."""
    account_manager.benchmark_tracker.benchmark_history = []
    account_manager.benchmark_tracker.active_shadow_trades = {}
    account_manager.benchmark_tracker.save_state()
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "benchmark_tracker"):
            inst.bot.benchmark_tracker.benchmark_history = []
            inst.bot.benchmark_tracker.active_shadow_trades = {}
    return {"status": True, "message": "Exit Benchmark History Reset Successfully"}

# --- 🎯 MARKET REGIME & LIQUIDITY FILTER SCORE API ---
@app.get("/api/regime/score")
async def get_market_regime_score(_: bool = Depends(verify_token)):
    """Get live market regime & institutional liquidity quality score (0-100)."""
    state = account_manager.get_selected_account_state()
    return state.get("regime_score", {})

@app.post("/api/regime/threshold")
async def set_regime_score_threshold(payload: dict, _: bool = Depends(verify_token)):
    """Update minimum confluence score threshold (e.g. 70, 65, 60)."""
    new_th = int(payload.get("threshold", 70))
    new_th = max(40, min(95, new_th))
    account_manager.scorer.threshold = new_th
    account_manager.scorer.save_state()
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "scorer"):
            inst.bot.scorer.threshold = new_th
            inst.bot.scorer.save_state()
    return {"status": True, "threshold": new_th, "message": f"Confluence Quality Threshold updated to {new_th} pts"}

@app.post("/api/regime/toggle")
async def toggle_regime_scorer(_: bool = Depends(verify_token)):
    """Toggle Market Regime Quality Filter on/off."""
    curr = account_manager.scorer.is_enabled
    account_manager.scorer.is_enabled = not curr
    account_manager.scorer.save_state()
    for inst in account_manager.accounts.values():
        if inst.type == "BOT" and hasattr(inst.bot, "scorer"):
            inst.bot.scorer.is_enabled = not curr
            inst.bot.scorer.save_state()
    return {"status": True, "is_enabled": not curr, "message": f"Quality Filter {'Enabled' if not curr else 'Disabled'}"}

# --- 📖 AUTO-SYNC TO TRADE JOURNAL API ---
@app.get("/api/journal/export_trades")
async def export_trades_for_journal(
    days: int = 90,
    mode: str = "auto",
    user: Optional[str] = None,
    token: Optional[str] = None
):
    """
    Export 100% verified MT5 deals mapped to Trade Journal (FXLOG PRO) standard schema:
    Supports:
    - mode="manual": Manual trades executed by user (@TOM, magic == 0).
    - mode="bot": Bot trades executed by 7 Secret System setups.
    - mode="auto": Automatically detects based on username or active MT5 account.
    """
    try:
        journal_trades = account_manager.analytics.fetch_trades_for_journal(
            days=days,
            mode=mode,
            user=user
        )
        return {
            "status": True,
            "mode": mode,
            "user": user,
            "count": len(journal_trades),
            "trades": journal_trades
        }
    except Exception as e:
        logger.error(f"Error exporting trades for journal: {e}")
        return JSONResponse(status_code=500, content={"status": False, "error": str(e), "trades": []})

@app.get("/api/journal/open_positions")
async def get_open_positions_for_journal(user: Optional[str] = Query("TOM")):
    """
    Fetch live ACTIVE / OPEN positions from MT5 to auto-fill NewTradeView in FXLOG PRO.
    Only returns ongoing positions currently floating in MT5.
    """
    try:
        open_trades = account_manager.analytics.fetch_open_positions_for_journal(user=user)
        return {
            "status": True,
            "user": user,
            "count": len(open_trades),
            "trades": open_trades
        }
    except Exception as e:
        logger.error(f"Error fetching open positions for journal: {e}")
        return JSONResponse(status_code=500, content={"status": False, "error": str(e), "trades": []})

@app.get("/api/journal/closed_trades")
async def get_closed_trades_for_journal(
    days: int = Query(3, description="Days of history to inspect"),
    mode: str = Query("manual", description="'manual', 'bot', or 'auto'"),
    user: Optional[str] = Query("TOM", description="Target journal username (e.g. TOM, BOT)")
):
    """
    Fetch closed trades from MT5 to record in TradeLogView in FXLOG PRO.
    """
    return await export_trades_for_journal(days=days, mode=mode, user=user)

if __name__ == "__main__":
    import uvicorn
    host = app_config.get("server", {}).get("host", "127.0.0.1")
    port = app_config.get("server", {}).get("port", 8000)
    print(f"\n=======================================================")
    print(f"🚀 XAUUSD Scalping M5 Multi-Account Hub Started")
    print(f"🔗 URL: http://{host}:{port}")
    print(f"🔑 Access Token: {app_config.get('auth', {}).get('access_tokens', ['GOLD_VIP_2026'])[0]}")
    print(f"=======================================================")
    uvicorn.run(app, host=host, port=port)

