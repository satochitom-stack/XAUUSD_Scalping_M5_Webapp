@echo off
setlocal enabledelayedexpansion
title XAUUSD Scalping M5 Bot WebApp
cd /d "%~dp0"

echo ===================================================
echo   XAUUSD Scalping M5 Secret System WebApp Launcher
echo ===================================================
echo.

:: 0. Check local .venv
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

:: 1. Check Python in PATH
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=python"
    goto :PYTHON_FOUND
)

:: 2. Check py launcher
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=py"
    goto :PYTHON_FOUND
)

:: 3. Check AppData Local Python311
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :PYTHON_FOUND
)

:: 4. Check AppData Local Python312
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :PYTHON_FOUND
)

:: 5. Check Program Files
if exist "%ProgramFiles%\Python311\python.exe" (
    set "PATH=%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts;%PATH%"
    set "PY_CMD=%ProgramFiles%\Python311\python.exe"
    goto :PYTHON_FOUND
)

echo [ERROR] Python not found on your system.
echo Please restart your terminal or computer, or download Python from https://www.python.org/
pause
exit /b 1

:PYTHON_FOUND
echo [OK] Using Python: %PY_CMD%
%PY_CMD% --version
echo.

echo [1/2] Checking / Installing required libraries...
%PY_CMD% -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo Retrying pip install with basic dependencies...
    %PY_CMD% -m pip install fastapi uvicorn pydantic pandas numpy jinja2 requests
)

echo.
echo [2/2] Starting WebApp Server & Bot Engine...
%PY_CMD% run_webapp.py

pause
