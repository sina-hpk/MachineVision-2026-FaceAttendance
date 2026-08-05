@echo off
title CV Attendance System
chcp 65001 >nul

echo.
echo =========================================
echo   CV Attendance System - Auto Launcher
echo =========================================
echo.

REM Use the project's virtual environment if it exists
set PYTHON=python
if exist ".venv\Scripts\python.exe" set PYTHON=.venv\Scripts\python.exe

echo Using: %PYTHON%
echo.

REM Kill any existing python processes on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [1/3] Starting server (FastAPI)...
start /min cmd /c "%PYTHON% -m uvicorn main_fastapi:app --host 0.0.0.0 --port 8000"

echo [2/3] Waiting for server to start...
timeout /t 6 >nul

echo [3/3] Opening browser...
start "" "http://localhost:8000"

echo.
echo =========================================
echo  SERVER RUNNING AT: http://localhost:8000
echo  API Docs (Swagger): http://localhost:8000/docs
echo  Press Ctrl+C in the server window to stop
echo =========================================
echo.
pause
