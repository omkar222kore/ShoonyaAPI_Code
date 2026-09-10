"""
Shoonya WebApp - Configuration
All thresholds, time windows, ports, and paths.
References parent D:\Python__Bot for shared files (cred, xlsx, ngrok.exe).
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)

BROKER_CRED = os.path.join(ROOT, "cred.yml")
EXCEL_FILE = os.path.join(ROOT, "NSE_symbols_filtered.xlsx")
NGROK_EXE = os.path.join(ROOT, "ngrok.exe")
NGROK_CONFIG = os.path.join(BASE_DIR, "ngrok.yml")

PORT = 5000

VALID_TIME_WINDOWS = [
    ("09:45", "10:00"),
    ("10:15", "10:30"),
    ("10:30", "10:45"),
    ("10:45", "11:00"),
    ("13:00", "13:15"),
]

MAX_STOCKS_PER_TIME = 3

DEFAULT_TRADING_CAP = 1000

PNL_STOP_LOSS_PCT = 0.006
PNL_TAKE_PROFIT_PCT = 0.01

MONITOR_INTERVAL = 5
