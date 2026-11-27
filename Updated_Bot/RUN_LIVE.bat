@echo off
setlocal EnableExtensions
title UPDATED_BOT LIVE START
cd /d "%~dp0"
set "PYTHON=E:\ShoonyaAPI_Code\Testing_WEBUI\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
if not exist "logs" mkdir "logs" >nul 2>&1
if not exist "state" mkdir "state" >nul 2>&1
del /q "state\command.json" >nul 2>&1
start "UPDATED_BOT_LIVE" /min cmd /c ""%PYTHON%" shoonya_scanner_bot.py --live 1>>"logs\bot_live.log" 2>&1"
echo Live bot started.
exit /b 0
