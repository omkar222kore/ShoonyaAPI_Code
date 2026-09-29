"""Shoonya phone bot - configuration (no Windows paths)."""
import os

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PKG_DIR, "assets")

PORT = 5000
HOST = os.environ.get("BOT_HOST", "127.0.0.1")

AUTH_TOKEN = os.environ.get("BOT_AUTH_TOKEN", "GURU123kore@")

SECRET_KEY = os.environ.get("BOT_SECRET", AUTH_TOKEN)

BROKER_CRED = os.path.join(ASSETS_DIR, "cred.yml")
EXCEL_FILE = os.path.join(ASSETS_DIR, "NSE_symbols_filtered.xlsx")
CLOUDFLARED_BIN = os.path.join(ASSETS_DIR, "cloudflared.bin")

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


def app_data_dir():
    d = os.environ.get("ANDROID_PRIVATE")
    if d and os.path.isdir(d):
        return d
    return os.path.abspath(os.path.join(PKG_DIR, ".."))


def status_path():
    return os.path.join(app_data_dir(), "bot_status.json")