@echo off
setlocal EnableExtensions
title UPDATED_BOT AUTO STOP
cd /d "%~dp0"
set "PYTHON=E:\ShoonyaAPI_Code\Testing_WEBUI\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" -c "import sys; sys.path.insert(0, '.'); import state; state.write_command('stop')"
set /a WAITED=0
:waitbot
set "BOTPID="
if not exist "state\bot.pid" goto botgone
for /f %%p in ("state\bot.pid") do set "BOTPID=%%p"
if "%BOTPID%"=="" goto botgone
powershell -NoProfile -Command "try { Get-Process -Id %BOTPID% -ErrorAction Stop | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 goto botgone
set /a WAITED+=1
if %WAITED% GEQ 15 goto killbot
powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
goto waitbot
:killbot
taskkill /F /PID %BOTPID% >nul 2>&1
:botgone
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'python*.exe' -and $_.CommandLine -like '*shoonya_scanner_bot.py*'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if exist "state\dashboard.pid" (
set "DASHPID="
for /f %%p in ("state\dashboard.pid") do set "DASHPID=%%p"
if not "%DASHPID%"=="" taskkill /F /PID %DASHPID% >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5010 ^| findstr LISTENING') do taskkill /F /T /PID %%p >nul 2>&1
del /q "state\command.json" >nul 2>&1
echo Stopped.
exit /b 0
