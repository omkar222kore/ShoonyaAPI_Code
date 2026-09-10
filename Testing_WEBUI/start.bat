@echo off
echo ============================================
echo  BACKTEST MACHINE - Starting...
echo ============================================
start "" /B D:\Python__Bot\.venv\Scripts\python.exe app.py
timeout /t 4 /nobreak >nul
start http://127.0.0.1:5000
