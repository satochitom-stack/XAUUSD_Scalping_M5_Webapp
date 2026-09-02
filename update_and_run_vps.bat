@echo off
title XAUUSD Scalping M5 - VPS Auto-Update & Launcher
cd /d "%~dp0"

echo =======================================================
echo   XAUUSD Scalping M5 - VPS Auto-Updater & Launcher
echo =======================================================
echo.

echo [1/2] Syncing latest updates from GitHub...
git pull origin main
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Continuing with local files...
) else (
    echo [SUCCESS] Codebase updated to latest version successfully!
)
echo.

echo [2/2] Launching WebApp & Bot Engine...
call run_webapp.bat

