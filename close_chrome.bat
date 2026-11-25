@echo off
setlocal

tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if errorlevel 1 (
    echo Chrome is not running.
    endlocal
    exit /b 0
)

echo Closing Chrome gracefully...
taskkill /IM chrome.exe /T >nul 2>&1

powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul 2>&1

tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if errorlevel 1 (
    echo Chrome closed.
    endlocal
    exit /b 0
)

echo Forcing Chrome to close...
taskkill /IM chrome.exe /T /F >nul 2>&1

tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if errorlevel 1 (
    echo Chrome closed.
    endlocal
    exit /b 0
)

echo Chrome could not be closed.
endlocal
exit /b 1
