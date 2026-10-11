@echo off
setlocal EnableExtensions
title Shoonya Algo Terminal - Setup ^& Start
cd /d "%~dp0"

echo ============================================================
echo   SHOONYA ALGO TERMINAL   -   Setup ^& Start
echo ============================================================
echo.

set "BASE_DIR=%~dp0"
set "PROJ_DIR=%BASE_DIR%.."
set "VENV=%PROJ_DIR%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "REQS=%BASE_DIR%requirements.txt"

:: ---------------------------------------------------------------
:: [1/5] Find a Python 3.9+ interpreter
:: ---------------------------------------------------------------
echo [1/5] Looking for Python...
set "SYS_PY="

py -3 -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY=py -3"
    goto :found_python
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY=python"
    goto :found_python
)

echo.
echo [ERROR] Python 3.9 or newer was not found on this PC.
echo.
echo   1. Download it from  https://www.python.org/downloads/
echo   2. During install TICK "Add python.exe to PATH"
echo   3. Run this file again
echo.
pause
exit /b 1

:found_python
for /f "delims=" %%V in ('%SYS_PY% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%V"
echo       Using Python %PYVER% via "%SYS_PY%"

:: ---------------------------------------------------------------
:: [2/5] Create the isolated virtual environment
:: ---------------------------------------------------------------
if exist "%PYTHON%" goto :have_venv

echo [2/5] Creating virtual environment (first run only)...
%SYS_PY% -m venv "%VENV%"
if not exist "%PYTHON%" (
    echo.
    echo [ERROR] Could not create the virtual environment at:
    echo         %VENV%
    pause
    exit /b 1
)
goto :deps

:have_venv
echo [2/5] Virtual environment already present.

:: ---------------------------------------------------------------
:: [3/5] Install dependencies (only when something is missing)
:: ---------------------------------------------------------------
:deps
echo [3/5] Checking dependencies...
"%PYTHON%" -c "import flask,flask_socketio,simple_websocket,pandas,openpyxl,yaml,NorenRestApiPy,pyotp,requests,websocket" >nul 2>&1
if not errorlevel 1 goto :deps_ok

echo       Installing packages - this may take a minute...
"%PYTHON%" -m pip install --upgrade pip --quiet
"%PYTHON%" -m pip install -r "%REQS%"
if errorlevel 1 (
    echo.
    echo [ERROR] Package installation failed.
    echo         Check your internet connection and run this file again.
    pause
    exit /b 1
)
goto :deps_ok

:deps_ok
echo       All dependencies ready.

:: ---------------------------------------------------------------
:: [4/5] Sanity-check the files the bot needs
:: ---------------------------------------------------------------
echo [4/5] Checking data files...
if not exist "%PROJ_DIR%\cred.yml" if not exist "%PROJ_DIR%\..\cred.yml" (
    echo       [WARN] cred.yml not found - broker login will fail.
)
if not exist "%PROJ_DIR%\NSE_symbols_filtered.xlsx" (
    echo       [WARN] NSE_symbols_filtered.xlsx not found - no symbols to trade.
)
if not exist "%PROJ_DIR%\ngrok.yml" if not exist "%BASE_DIR%ngrok.yml" (
    echo       [WARN] ngrok.yml not found - public webhook URL will be unavailable.
)
if not exist "%PROJ_DIR%\ngrok.exe" (
    echo       [WARN] ngrok.exe not found - public webhook URL will be unavailable.
)
echo       Check complete.

:: ---------------------------------------------------------------
:: [5/5] Launch
:: ---------------------------------------------------------------
echo [5/5] Starting the dashboard...
echo.
echo ============================================================
echo   Dashboard :  http://localhost:5000
echo   Webhook   :  http://localhost:5000/webhook
echo.
echo   Keep this window open. Press CTRL+C to stop the bot.
echo ============================================================
echo.

start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5000"

"%PYTHON%" app.py

echo.
echo Server stopped.
pause
