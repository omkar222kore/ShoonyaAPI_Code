@echo off
title Shoonya Algo Terminal
cd /d "%~dp0"

echo ============================================================
echo   SHOONYA ALGO TERMINAL - Starting...
echo ============================================================
echo.

set PYTHON=D:\Python__Bot\.venv\Scripts\python.exe
set PIP=D:\Python__Bot\.venv\Scripts\pip.exe

if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found at D:\Python__Bot\.venv
    pause
    exit /b 1
)

:: Install requirements if flask_socketio not present
"%PYTHON%" -c "import flask_socketio" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing dependencies...
    "%PIP%" install -r requirements.txt
)

echo ============================================================
echo   Dashboard:   http://localhost:5000
echo   Webhook:     http://localhost:5000/webhook
echo ============================================================
echo.

:: Auto-open browser after 3 seconds
start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5000"

:: Run the server
"%PYTHON%" app.py

pause
