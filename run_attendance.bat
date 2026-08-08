@echo off
title CV Attendance System
chcp 65001 >nul

echo.
echo =========================================
echo   CV Attendance System - Windows Launcher
echo =========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Please install Python 3.11+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/3] Running unified launcher (run.py)...
echo.

python run.py %*

echo.
echo =========================================
echo  Launcher finished.
echo =========================================
echo.
pause
