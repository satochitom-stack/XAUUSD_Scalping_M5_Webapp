@echo off
setlocal enabledelayedexpansion
title FXLOG PRO - MT5 Journal Bridge (Manual Trading)
cd /d "%~dp0"

echo ===================================================
echo   FXLOG PRO - MT5 Local Journal Bridge Launcher
echo   Connects MT5 (#257508244) to trade-journal-1.vercel.app
echo ===================================================
echo.

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    if not "%%a"=="" (
        taskkill /F /PID %%a >nul 2>&1
    )
)

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" run_fxlog_bridge.py
    goto :EOF
)

python run_fxlog_bridge.py
pause
