# CODEX.md - Project Architecture & AI Collaboration Guide
> **Repository**: `XAUUSD_Scalping_M5_Webapp` (Backend Engine & Trading API)  
> **GitHub**: `https://github.com/satochitom-stack/XAUUSD_Scalping_M5_Webapp`  
> **Target Symbol**: `XAUUSDc` (Gold Cent) / `XAUUSD`  
> **System Status**: Active Trading on Exness MT5 (VPS Host)  
> **Last Synchronized**: 2026-09-10

---

## 1. System Overview & Core Philosophy
This codebase powers an automated algorithmic trading bot and FastAPI backend for Gold (`XAUUSD`) trading on MetaTrader 5 (MT5). The trading engine operates on a multi-timeframe confluence architecture with strict risk management, dynamic lot sizing, and multi-stage trailing profit locks.

### 🌟 Active Trading Model: The Elite 6 Pillars
Only **6 active setups** are permitted to scan the market and execute new trades. All other legacy models have been decommissioned and archived into `RETIRED_SETUPS`.

| Setup ID | Strategy Name | Timeframe | Trading Hours (UTC+7) | Risk Sizing | Target R:R | Exit Mechanism |
|---|---|:---:|:---:|:---:|:---:|---|
| `PULLBACK_DR_EKK` | Signature Pullback (#PullBack ร้อยล้าน) | M5 (H1 Filter) | 14:00 - 02:00 | 2.0% Step-Up Compounding | 1:2.5 (TP1 1.5R) | EMA 60 Pullback + Fib 38.2%-61.8% + S/R Flip + Runner |
| `RTM_M4_CONSERVATIVE` | RTM Quasimodo M4 (Conservative) | M15 (H1 Filter) | 14:00 - 23:00 | 2.0% Step-Up Compounding | 1:2.0 | Retest QML + M5 Rejection Wick $\ge 28\%$ + BE lock at 1.0R |
| `RTM_M6_ELITE_GROWTH` | RTM Quasimodo M6 (Elite Growth) | M15 (H1 Filter) | 14:00 - 23:00 | 2.0% Step-Up Compounding | 1:2.0 | Retest Golden Pocket 50%-65% + Rejection Wick + BE lock at 1.0R |
| `SMC_X_STO_H1` | SMC x STO Devil System (ระบบปีศาจ) | H1 | 14:00 - 04:00 | 1.0% Fixed Risk | 1:2.0 | EMA 50/200 Trend + Discount/Premium ATR + Single OB + Stoch 14,3,3 |
| `KC_LIQUIDITY_DOMINANCE` | KC Forex (Sweep x Candle Dominance) | M5 | 14:00 - 02:00 | 1.5% Step-Up Compounding | 1:2.0 | Liquidity Sweep 15-20 Bars + Dominance Rejection (Body $\ge 50\%$) + BE at 1.0R |
| `CONFLUENCE_SQUEEZE_M15` | AI Confluence Squeeze Breakout (Self-Designed) | M15 (H1 Filter) | 14:00 - 04:00 | 0.5% Fixed Risk | 1:2.0 (1.5-4.0R AI-bounded) | Volatility Squeeze (BB Width low-20%ile) + Expansion Breakout ($\ge$55% body, $\ge$1.3x ATR) + Structure Break + Volume $\ge$1.3x + London/NY + H1 Trend Filter; BE lock at 1.0R, +0.9R lock at 1.6R |
| `RETIRED_SETUPS` | เซตอัพที่เลิกใช้ (Archived) | Multi-TF | Historical Archive | None (No new orders) | N/A | Preserves all historical trade records and closed PnL |

---

## 2. Magic Numbers & Strategy Mapping

```python
STRATEGY_MAGIC_MAP = {
    "PULLBACK_DR_EKK":        {"base": 555860, "pos1": 555861, "pos2": 555862, "pos3": 555863},
    "RTM_M4_CONSERVATIVE":    {"base": 777004, "pos1": 777014, "pos2": 777024, "pos3": 777034},
    "RTM_M6_ELITE_GROWTH":    {"base": 777006, "pos1": 777016, "pos2": 777026, "pos3": 777036},
    "SMC_X_STO_H1":           {"base": 555770, "pos1": 555771, "pos2": 555772, "pos3": 555773},
    "KC_LIQUIDITY_DOMINANCE": {"base": 555880, "pos1": 555881, "pos2": 555882, "pos3": 555883},
    "CONFLUENCE_SQUEEZE_M15": {"base": 555950, "pos1": 555951, "pos2": 555952, "pos3": 555953},
}
```

### 📦 Archived / Retired Setups (DO NOT RE-ENABLE OR DELETE DATA)
The following Magic numbers represent decommissioned strategies whose historical PnL **must always be classified into `RETIRED_SETUPS`**:
- **News Momentum Expansion**: Magic `555889..555893`, `666888..666890`, comments containing `news`, `momentum`, `goldm5_pro`
- **Asian Range Sniper**: Magic `555820..555823`, comments containing `asian`
- **RTM M5 (All-Weather)**: Magic `777005, 777015, 777025, 777035`
- **RTM M7 (Max Alpha)**: Magic `777007, 777017, 777027, 777037`
- **Tug of War Volume Read M15**: Magic `555900..555903`
- **Legacy Models**: Flash Micro (`555801..555803`), EMA 50 Scalper (`555851..555852`)

---

## 3. Key Source Files & Responsibilities

1. **`bot_engine.py`**:
   - The main algorithmic execution engine (`ScalpingBotEngine`).
   - Handles candle bar close evaluation, technical indicators (EMA, ATR, Fibonacci, Stochastic), signal generation, order execution (`execute_buy`, `execute_sell`), and open position trailing (`manage_open_positions`).
   - Enforces `max_concurrent_setups = 6`.

2. **`strategy_analytics.py`**:
   - `RealTradeAnalyticsManager`: Connects to MT5 history deals API.
   - Filters deals using `EPOCH_START_TIME = datetime(2026, 9, 7, 15, 0, 0)`.
   - Classifies every deal into one of the 6 active pillars or `RETIRED_SETUPS`.
   - Computes 100% verified real Winrate, Profit Factor, Realized R:R, and Max Drawdown from closed deals.

3. **`strategy_optimizer.py`**:
   - `RealTimeStrategyOptimizer`: Real-time market regime classifier (`STRONG_BULLISH_TREND`, `HIGH_VOLATILITY`, `RANGING_CHOPPY`, etc.).
   - Dynamically calculates SL buffer, streak multipliers, and session heat adjustments.

4. **`main.py`**:
   - FastAPI REST API application server.
   - Provides endpoints for web dashboard integration:
     - `GET /api/system/status`
     - `GET /api/strategy-analytics/summary`
     - `GET /api/trades`
     - `GET /api/positions`
     - `POST /api/system/reload`
     - `GET /api/strategy/risk_config` / `POST /api/strategy/risk_config` - per-setup risk % override (see section 6 below)

5. **`config.json`**:
   - Holds account logins, MT5 path, risk parameters, API tokens, and system flags.

---

## 4. Ground Rules for AI Coding (Codex / Copilot Rules)

1. **Active Setup Count is Strictly 6**:
   - Never add a 7th active setup without explicit instruction.
   - `max_concurrent_setups` in `config.json` must match `6`.
   - `strategies_count` in `main.py` must return `6`.

2. **Preserve Real MT5 Historical Data**:
   - Never purge, delete, or mock closed deal history from MT5.
   - Any trade that does not match the 6 active pillars must seamlessly fallback to `RETIRED_SETUPS`.

3. **Risk Management & Compounding**:
   - `PULLBACK_DR_EKK`, `RTM_M4`, and `RTM_M6` utilize **2.0% Step-Up Compounding** (Tier base calculated against high-water equity).
   - `KC_LIQUIDITY_DOMINANCE` uses **1.5% Step-Up Compounding**.
   - `SMC_X_STO_H1` uses **1.0% Fixed Risk**.
   - `CONFLUENCE_SQUEEZE_M15` uses **0.5% Fixed Risk** (self-designed setup, no live track record yet; same Full AI Gating pipeline as every other pillar via `_process_single_setup_signal()`). Unlike Tug of War, it runs as an AI Trend Trail (trailing runner, not a fixed TP) since volatility-squeeze breakouts statistically tend to continue.
   - All 6 percentages above are **defaults only** - the user can override any of them per-setup, per-account, live from the Web Dashboard (see section 6, `/api/strategy/risk_config`). Never remove `RISK_PROFILE_DEFAULTS` in `bot_engine.py` or hardcode a risk % back into `calculate_lot_size()` - it must always resolve through that table + the `risk_overrides` lookup.

4. **Testing is Mandatory Before Commit**:
   - Always run the test suite to verify no regressions:
     ```bash
     python -m unittest discover tests
     ```
   - All tests must pass (37+ tests).

5. **Broker SL/TP Safety**:
   - When orders are placed, SL and TP are immediately submitted to the broker server.
   - Any legacy open positions awaiting closure must be left to resolve via their broker SL/TP.

---

## 5. REST API & Integration Reference
- **Local API Base**: `http://localhost:8000`
- **VPS API Base**: `http://139.180.157.124:12308`
- **Swagger Documentation**: `/docs`
- **Auth Header**:
  ```http
  X-Token: GOLD_VIP_2026
  ```

---

## 6. Per-Setup Risk Configuration API (Web Dashboard)
Lets the user set a custom risk % for any of the 6 active pillars independently, per account, from the web dashboard - **no bot restart and no MT5 reconnect required**. The change is applied to the live running bot on the very next iteration.

- **Single source of truth**: `RISK_PROFILE_DEFAULTS` in `bot_engine.py` - maps each active `strat_id` to its `default_pct` and sizing `mode` (`STEP_UP_COMPOUNDING` or `FIXED`). `calculate_lot_size()` always resolves risk % through this table plus any override, never a hardcoded literal.
- **Allowed range**: `RISK_OVERRIDE_MIN_PCT` (0.10%) to `RISK_OVERRIDE_MAX_PCT` (5.00%), enforced both at the API layer (rejects out-of-range writes with HTTP 400) and defensively inside `calculate_lot_size()` itself (clamps silently) in case a bad value ever reaches `config.json` through another path.
- **Storage**: `config["accounts"][i]["strategy"]["risk_overrides"]` - a `{strat_id: risk_pct}` dict, only containing the setups the user has actually overridden. Missing a key means "use the default".
- **Live-apply mechanism**: `MultiAccountManager.update_strategy_settings(acc_id, {"risk_overrides": {...}})` merges into `AccountInstance.strategy_cfg` (the *same dict object* `bot.config["strategy"]` already points to) and calls `bot.update_config(...)`, then persists to `config.json`. It deliberately does **not** call the heavier `update_account()` path, which always tears down and recreates the MT5 connector (`MT5Connector.__init__` re-runs `mt5.initialize()`) - unnecessary and disruptive for a risk-only tweak.

**`GET /api/strategy/risk_config?acc_id=<optional>`** (defaults to the currently selected account):
```json
{
  "status": true, "acc_id": "acc_c354ec", "acc_name": "Auto1",
  "step_up_compounding_enabled": true,
  "setups": [
    {"id": "PULLBACK_DR_EKK", "name": "...", "icon": "🎯", "sizing_mode": "STEP_UP_COMPOUNDING",
     "default_risk_pct": 2.0, "current_risk_pct": 2.0, "is_overridden": false,
     "min_risk_pct": 0.1, "max_risk_pct": 5.0},
    "... (one entry per active pillar, in STRATEGY_MAGIC_MAP order)"
  ]
}
```

**`POST /api/strategy/risk_config`** - partial update, only the setups being changed:
```json
{"acc_id": "acc_c354ec", "risk_overrides": {"KC_LIQUIDITY_DOMINANCE": 2.0, "PULLBACK_DR_EKK": null}}
```
`null` resets that one setup back to its factory default. Returns the same shape as the GET above (post-update state). A value outside `[0.10, 5.00]` or an unknown `strat_id` returns HTTP 400 with a message naming the offending setup(s) - no partial writes on error.
