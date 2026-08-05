@echo off
title CV Attendance System
chcp 65001 >nul

echo.
echo =========================================
echo   CV Attendance System - Auto Launcher
echo =========================================
echo.

REM Kill any existing python processes on port 5000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [1/3] Starting server...
start /min cmd /c "python main.py web --port 5000"

echo [2/3] Waiting for server to start...
timeout /t 4 >nul

echo [3/3] Opening browser...
start "" "http://localhost:5000"

echo.
echo =========================================
echo  SERVER RUNNING AT: http://localhost:5000
echo  Press Ctrl+C in the server window to stop
echo =========================================
echo.
pause