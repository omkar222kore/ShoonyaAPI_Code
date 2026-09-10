@echo off
title STOP ALL - Shoonya Terminal
echo ============================================
echo   STOPPING SHOONYA PROCESSES...
echo ============================================

:: 1. Kill ngrok
echo [1/3] Killing ngrok...
taskkill /F /T /IM ngrok.exe >nul 2>&1

:: 2. Kill web server (port 5000)
echo [2/3] Killing WebApp server (port 5000)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /T /PID %%p >nul 2>&1
)

:: 3. Kill legacy bot exe
echo [3/3] Killing BuySell_updated.exe...
taskkill /F /T /IM BuySell_updated.exe >nul 2>&1

echo.
echo   ALL STOPPED - Relaunch with start_webapp.bat
echo ============================================
pause
