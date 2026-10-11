"""
Shoonya WebApp - Configuration
All thresholds, time windows, ports, and paths.
References parent folder for shared files (cred, xlsx, ngrok.exe).
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)

def _find_cred():
    for p in (
        os.path.join(ROOT, "cred.yml"),
        os.path.join(os.path.dirname(ROOT), "cred.yml"),
        os.path.join(BASE_DIR, "cred.yml"),
    ):
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, "cred.yml")

BROKER_CRED = _find_cred()
EXCEL_FILE = os.path.join(ROOT, "NSE_symbols_filtered.xlsx")
TRADE_LOG_FILE = os.path.join(ROOT, "trade_log.xlsx")
NGROK_EXE = os.path.join(ROOT, "ngrok.exe")
NGROK_CONFIG = os.path.join(ROOT, "ngrok.yml")

PORT = 5000

VALID_TIME_WINDOWS = [
    ("09:45", "10:00"),
    ("10:15", "10:30"),
    ("10:30", "10:45"),
    ("10:45", "11:00"),
    ("13:00", "13:15"),
]

MAX_STOCKS_PER_TIME = 3

DEFAULT_TRADING_CAP = 200000

PNL_STOP_LOSS_PCT = 0.006
PNL_TAKE_PROFIT_PCT = 0.014

MONITOR_INTERVAL = 2
POSITION_LOG_EVERY = 5

EOD_SQUARE_OFF = "15:10"

VIRTUAL_MODE_DEFAULT = True
