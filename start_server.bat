@echo off
title ZeroBreakout Server
echo ===================================================
echo        ZeroBreakout - NSE Stock Pattern Scanner
echo ===================================================
echo.

cd /d "%~dp0"
echo Starting ZeroBreakout on http://127.0.0.1:8001 ...
echo Opening browser...
start http://127.0.0.1:8001/

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
pause
