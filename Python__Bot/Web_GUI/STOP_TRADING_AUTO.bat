@echo off
setlocal EnableExtensions
title Shoonya Auto Stop

cd /d "%~dp0"

set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOG=%LOGDIR%\stop.log"
set "LAST=%LOGDIR%\last_stop.txt"

>>"%LOG%" echo ===== AUTO STOP %DATE% %TIME% =====

rem Ask the bot to stop cleanly (square-off happens only at EOD; this just halts trading)
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/stop' -Method Post -TimeoutSec 15 | Out-Null; 'stop_requested=ok' }catch{ 'stop_requested=unavailable' }" > "%LAST%" 2>&1
type "%LAST%" >> "%LOG%"

powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul 2>&1

rem Kill the ngrok tunnel
taskkill /F /IM ngrok.exe >nul 2>&1
if errorlevel 1 ( >>"%LOG%" echo ngrok: not running ) else ( >>"%LOG%" echo ngrok: killed )

rem Kill whatever is listening on port 5000
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    set "FOUND=1"
    taskkill /F /T /PID %%p >nul 2>&1
)
if defined FOUND ( >>"%LOG%" echo port5000: killed ) else ( >>"%LOG%" echo port5000: nothing listening )

>>"%LOG%" echo ===== STOP DONE %TIME% =====
exit /b 0
