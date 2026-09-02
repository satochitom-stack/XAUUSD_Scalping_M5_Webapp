@echo off
title XAUUSD Scalping M5 - VPS Auto-Update & Launcher
cd /d "%~dp0"

echo =======================================================
echo   XAUUSD Scalping M5 - VPS Auto-Updater & Launcher
echo =======================================================
echo.

echo [1/2] Syncing latest updates from GitHub...
:: Reset any runtime auto-saved files (regime_scorer_stats.json, config.json) so git pull never gets blocked
git reset --hard HEAD
git pull origin main
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Normal pull failed due to conflict, forcing fresh sync from origin/main...
    git fetch origin main
    git reset --hard origin/main
)
echo [SUCCESS] Codebase updated to latest version successfully!
echo.

echo [2/2] Launching WebApp & Bot Engine...
call run_webapp.bat

