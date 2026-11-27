@echo off
setlocal EnableExtensions EnableDelayedExpansion
title UPDATED_BOT AUTO START
cd /d "%~dp0"
set "PYTHON=E:\ShoonyaAPI_Code\Testing_WEBUI\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
if not exist "logs" mkdir "logs" >nul 2>&1
if not exist "state" mkdir "state" >nul 2>&1
echo [%date% %time%] Refreshing Shoonya super token >> "logs\token.log"
"%PYTHON%" -c "import sys,state; sys.exit(state.refresh_token())" >nul 2>> "logs\token.log"
if errorlevel 1 echo [%date% %time%] Token refresh failed; using existing token >> "logs\token.log"
echo [%date% %time%] Refreshing FYERS token >> "logs\fyers_token.log"
set "FYERS_LOGIN_OK=0"
for /L %%i in (1,1,3) do (
  if "!FYERS_LOGIN_OK!"=="0" (
    "%PYTHON%" fyers_auto_login.py >> "logs\fyers_token.log" 2>&1
    if not errorlevel 1 (
      set "FYERS_LOGIN_OK=1"
    ) else (
      echo [%date% %time%] FYERS login attempt %%i failed >> "logs\fyers_token.log"
      timeout /t 5 /nobreak >nul
    )
  )
)
if "!FYERS_LOGIN_OK!"=="0" (
  echo [%date% %time%] FYERS login failed after 3 attempts; aborting start >> "logs\fyers_token.log"
  echo FYERS login failed after 3 attempts. See logs\fyers_token.log
  exit /b 1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5010 ^| findstr LISTENING') do taskkill /F /T /PID %%p >nul 2>&1
del /q "state\command.json" >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'python*.exe' -and $_.CommandLine -like '*shoonya_scanner_bot.py*'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
del /q "state\bot.pid" >nul 2>&1
del /q "state\dashboard.pid" >nul 2>&1
start "UPDATED_BOT_DASHBOARD" /min cmd /c ""%PYTHON%" dashboard.py 1>>"logs\dashboard.log" 2>&1"
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:5010/' -TimeoutSec 2 -UseBasicParsing; if($r.StatusCode -eq 200){$ok=$true;break} }catch{}; Start-Sleep -Seconds 1 }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
echo Dashboard failed to start. See logs\dashboard.log
exit /b 1
)
start "UPDATED_BOT_PAPER" /min cmd /c ""%PYTHON%" shoonya_scanner_bot.py --paper 1>>"logs\bot.log" 2>&1"
start "" "http://127.0.0.1:5010"
echo Started dashboard and paper bot.
exit /b 0
