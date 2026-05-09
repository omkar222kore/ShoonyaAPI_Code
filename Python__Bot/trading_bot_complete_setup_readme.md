# Shoonya Portable Trading Bot Setup Guide

## Features

- Portable setup
- No D:\\ drive dependency
- GUI-based bot control
- Automatic ngrok tunnel
- TradingView webhook support
- Live Total PnL display
- Green/Red PnL color update
- Real-time terminal logs
- Configurable trading capital
- Works on another PC without Python installation

---

# Final Folder Structure

```text
TradingBot_Final/
│
├── GUI.exe
├── BuySell_updated.exe
├── cred.yml
├── NSE_symbols_filtered.xlsx
├── ngrok.exe
```

---

# Required Files

## 1. GUI.exe
Main GUI application.

## 2. BuySell_updated.exe
Main trading engine.

## 3. cred.yml
Shoonya credentials.

Example:

```yaml
user: YOUR_USER_ID
pwd: YOUR_PASSWORD
```

## 4. NSE_symbols_filtered.xlsx
Token mapping Excel file.

## 5. ngrok.exe
Used for public webhook URL generation.

---

# Step 1 — Install Python (Only for Build Machine)

Download Python:

https://www.python.org/downloads/

IMPORTANT:

Enable:

```text
Add Python to PATH
```

while installing.

---

# Step 2 — Create Virtual Environment

Open CMD inside project folder.

Run:

```bash
python -m venv .venv
```

Activate:

```bash
.venv\Scripts\activate
```

You should see:

```text
(.venv)
```

---

# Step 3 — Install Required Modules

Run:

```bash
pip install pandas flask pyyaml pyotp requests openpyxl NorenRestApiPy pyinstaller
```

---

# Step 4 — Verify Pandas

Run:

```bash
python -c "import pandas; print('PANDAS OK')"
```

Expected:

```text
PANDAS OK
```

---

# Step 5 — Download ngrok

Download:

https://ngrok.com/downloads/windows

Download:

```text
Windows 64-bit
```

Extract ZIP.

Copy:

```text
ngrok.exe
```

into:

```text
TradingBot_Final/
```

---

# Step 6 — Configure ngrok Auth Token

Get auth token:

https://dashboard.ngrok.com/get-started/your-authtoken

Open CMD inside project folder.

Run:

```bash
ngrok.exe config add-authtoken YOUR_TOKEN
```

Example:

```bash
ngrok.exe config add-authtoken 2abcxyz123
```

---

# Step 7 — Test ngrok

Run:

```bash
ngrok.exe http 5000
```

Expected:

```text
Forwarding https://xxxxx.ngrok-free.app
```

Close CMD after successful test.

---

# Step 8 — Build BuySell_updated.exe

Open CMD.

Activate venv:

```bash
.venv\Scripts\activate
```

Run:

```bash
pyinstaller --onefile BuySell_updated.py
```

---

# Step 9 — Build GUI.exe

Run:

```bash
pyinstaller --onefile --windowed GUI.py
```

---

# Step 10 — Copy EXE Files

After build:

```text
dist/
```

Copy:

```text
GUI.exe
BuySell_updated.exe
```

into:

```text
TradingBot_Final/
```

---

# Step 11 — Run Application

Double click:

```text
GUI.exe
```

Inside GUI:

1. Enter SuperToken
2. Enter Trading Capital
3. Click START BOT

Application automatically:

- Starts Flask server
- Starts ngrok tunnel
- Generates webhook URL
- Copies webhook URL
- Starts monitoring thread
- Shows live Total PnL

---

# TradingView Webhook URL

GUI generates:

```text
https://xxxxx.ngrok-free.app/webhook
```

Use this URL inside TradingView webhook settings.

---

# Common Errors

## ERROR 1

```text
ModuleNotFoundError: No module named 'pandas'
```

### Fix

Activate venv:

```bash
.venv\Scripts\activate
```

Install modules:

```bash
pip install pandas flask pyyaml pyotp requests openpyxl NorenRestApiPy pyinstaller
```

Rebuild exe files.

---

## ERROR 2

```text
[WinError 2] The system cannot find the file specified
```

### Cause

```text
ngrok.exe missing
```

### Fix

Copy:

```text
ngrok.exe
```

inside:

```text
TradingBot_Final/
```

---

## ERROR 3

```text
Too early to create variable: no default root window
```

### Fix

Create:

```python
pnl_var = tk.StringVar()
```

AFTER:

```python
root = tk.Tk()
```

---

# Portable Setup Benefits

- No D:\\ dependency
- No fixed paths
- Works from pendrive
- Works on another laptop
- No Python installation needed on target PC
- Fully portable deployment

---

# Monitoring Features

- Position monitoring every 5 seconds
- Live Total PnL
- Green PnL when positive
- Red PnL when negative
- Automatic SL/TP exits
- Real-time console logs

---

# Notes

- Keep all files inside same folder
- Do not rename exe files
- Keep internet connection active
- Keep ngrok authenticated
- TradingView webhook must use generated ngrok URL

---

# Recommended Git Structure

```text
TradingBot/
│
├── GUI.py
├── BuySell_updated.py
├── README.md
├── requirements.txt
├── cred.yml
├── NSE_symbols_filtered.xlsx
```

---

# requirements.txt

```text
pandas
flask
pyyaml
pyotp
requests
openpyxl
NorenRestApiPy
pyinstaller
```

---

# Build Commands

```bash
pyinstaller --onefile BuySell_updated.py
```

```bash
pyinstaller --onefile --windowed GUI.py
```

---

# Final Result

You now have:

- Portable Shoonya trading bot
- GUI-based trading control
- TradingView webhook integration
- Portable deployment architecture
- Live PnL monitoring
- Dynamic trading capital control
- Real-time logs

