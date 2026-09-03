@echo off
title ZeroBreakout Terminal Launcher
echo ===================================================
echo        ZeroBreakout - NSE Stock Pattern Scanner
echo ===================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking backend server on port 8001 ...
netstat -ano | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [2/3] Starting ZeroBreakout server on http://127.0.0.1:8001 ...
    start /min "" python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --log-level info
    timeout /t 3 /nobreak >nul
) else (
    echo [2/3] Backend server is already running on port 8001.
)

echo [3/3] Launching ZeroBreakout in browser...
start http://127.0.0.1:8001/

echo.
echo ZeroBreakout Terminal launched successfully!
timeout /t 2 >nul
