@echo off
chcp 65001 >nul
title XAUUSD Scalping M5 Bot (Local MT5 Mode)
cd /d "%~dp0"

echo ===================================================================
echo   XAUUSD Scalping M5 Secret System - Local MT5 Auto Bot
echo ===================================================================
echo [1/4] ตรวจสอบและซิงค์อัปเดตระบบล่าสุดจาก GitHub...
git pull origin main

echo.
echo [2/4] ตรวจสอบโปรแกรม MT5 Terminal 1...
tasklist /FI "IMAGENAME eq terminal64.exe" 2>NUL | find /I /N "terminal64.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [OK] MT5 Terminal กำลังเปิดทำงานอยู่
) else (
    echo [INFO] กำลังเปิดโปรแกรม MT5 Terminal...
    start "" "C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
    timeout /t 5 >nul
)

echo [3/4] เคลียร์พอร์ต 8000 สำหรับ WebApp Dashboard...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1

echo [4/4] กำลังเริ่มระบบบอท และเปิดหน้าจอ Dashboard...
echo.
echo -------------------------------------------------------------------
echo  Dashboard: http://localhost:8000
echo  Access Token: GOLD_VIP_2026
echo -------------------------------------------------------------------
echo.
start http://localhost:8000
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" run_webapp.py
) else (
    python run_webapp.py
)
pause
