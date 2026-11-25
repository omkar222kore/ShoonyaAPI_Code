@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Shoonya Auto Start (LIVE)

cd /d "%~dp0"

set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "DAY=%%d"
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%d"
set "LOG=%LOGDIR%\autostart.log"
set "SRVLOG=%LOGDIR%\server_%DAY%.log"
set "STATUS=%LOGDIR%\last_status.txt"

set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=E:\ShoonyaAPI_Code\Python__Bot\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    call :log "[ERROR] Python venv not found: %PYTHON%"
    exit /b 1
)

rem Default is LIVE. Pass "paper" as first argument for a virtual dry run.
set "VBODY=false"
if /i "%~1"=="paper" set "VBODY=true"

call :log "===== AUTO START %STAMP% ====="

rem ---------------------------------------------------------------
rem 1) Is the web server already listening?
rem ---------------------------------------------------------------
call :live_server_ok
if not errorlevel 1 goto :have_server

call :log "Port 5000 is not the live app - freeing port..."
call :kill_port_5000
powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1

call :log "Starting web server (app.py)..."
start "SHOONYA_SERVER" /min cmd /c ""%PYTHON%" app.py 1>>"%SRVLOG%" 2>&1"
call :log "Waiting up to 90s for live app on port 5000..."
call :wait_live_server
if errorlevel 1 (
    call :log "[ERROR] Live app did not come up within 90s (see %SRVLOG%)"
    exit /b 1
)
call :log "Live server is up."
goto :after_server

:have_server
call :log "Live server already running on port 5000."

:after_server

rem ---------------------------------------------------------------
rem 2) Open the dashboard first, then continue starting
rem ---------------------------------------------------------------
call :log "Opening dashboard http://127.0.0.1:5000 ..."
start "" "http://127.0.0.1:5000"
powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1

rem ---------------------------------------------------------------
rem 3) Read current status (also tells us if the bot is already on)
rem ---------------------------------------------------------------
call :status
for /f "usebackq tokens=1,* delims==" %%a in ("%STATUS%") do set "ST_%%a=%%b"

if /i "!ST_running!"=="true" (
    call :log "Bot is already running in !ST_mode! mode - nothing to start."
    exit /b 0
)

rem ---------------------------------------------------------------
rem 4) Start + auto-login (JKEY fetched from cred.yml by the app)
rem ---------------------------------------------------------------
call :log "Sending START (virtual=%VBODY%)..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $b=@{virtual=$%VBODY%}|ConvertTo-Json; $r=Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/start' -Method Post -ContentType 'application/json' -Body $b -TimeoutSec 300; 'started=' + [string]$r.status + ' mode=' + [string]$r.mode; exit 0 }catch{ $m=$_.ErrorDetails.Message; if(-not $m){ $m=$_.Exception.Message }; 'start_error=' + $m; exit 1 }" > "%LOGDIR%\last_start.txt" 2>&1
set "START_RC=%errorlevel%"
type "%LOGDIR%\last_start.txt" >> "%LOG%"
if not "%START_RC%"=="0" (
    call :log "[ERROR] START request failed - see last_start.txt"
    exit /b 1
)

rem ---------------------------------------------------------------
rem 4) Verify the bot is actually running and log the webhook URL
rem ---------------------------------------------------------------
powershell -NoProfile -Command "Start-Sleep -Seconds 5" >nul 2>&1
call :status
for /f "usebackq tokens=1,* delims==" %%a in ("%STATUS%") do set "ST2_%%a=%%b"

if /i "!ST2_running!"=="true" (
    call :log "Bot is RUNNING in !ST2_mode! mode."
    if defined ST2_webhook call :log "Webhook URL: !ST2_webhook!"
    exit /b 0
)

call :log "[ERROR] Bot did not report running after START."
call :log "Status file: %STATUS%"
exit /b 1

rem ---------------------------------------------------------------
rem helpers
rem ---------------------------------------------------------------
:live_server_ok
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $s=Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/status' -TimeoutSec 3; if($s.PSObject.Properties.Name -contains 'eod_time'){exit 0}else{exit 1} }catch{ exit 1 }"
exit /b %errorlevel%

:wait_live_server
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 90;$i++){ try{ $s=Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/status' -TimeoutSec 2; if($s.PSObject.Properties.Name -contains 'eod_time'){ $ok=$true; break } }catch{}; Start-Sleep -Seconds 1 }; if($ok){exit 0}else{exit 1}"
exit /b %errorlevel%

:kill_port_5000
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /T /PID %%p >nul 2>&1
)
exit /b 0

:status
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $s=Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/status' -TimeoutSec 5; 'running=' + ([string]$s.running).ToLower(); 'mode=' + [string]$s.mode; 'webhook=' + [string]$s.webhook_url }catch{ 'running=false'; 'mode=unknown'; 'webhook=' }" > "%STATUS%" 2>&1
exit /b 0

:log
>>"%LOG%" echo [%TIME%] %~1
echo [%TIME%] %~1
exit /b 0
