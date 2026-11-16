@echo off
setlocal EnableExtensions
title Shoonya Algo Terminal - Start
cd /d "%~dp0"

echo Starting Shoonya WebApp...
set "PYTHON=E:\ShoonyaAPI_Code\Python__Bot\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found at %PYTHON%
    pause
    exit /b 1
)

"%PYTHON%" -c "import sys; print('Using Python', sys.version.split()[0])"

if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
if exist "..\__pycache__" rmdir /s /q "..\__pycache__" 2>nul

start "" http://127.0.0.1:5000

echo.
echo Server is running...
echo Open http://127.0.0.1:5000 in your browser
echo Press CTRL+C to stop this window
echo.

"%PYTHON%" app.py
pause
