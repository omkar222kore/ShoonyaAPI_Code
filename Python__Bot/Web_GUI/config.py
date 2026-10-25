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

# Symbol master. The full NSE equity master is rebuilt by
# tools/build_symbol_master.py; the old 500-symbol filtered file is kept as a
# fallback so the app still starts if the rebuild has not been run yet.
MASTER_FILE = os.path.join(ROOT, "nse_equity_master.xlsx")
LEGACY_EXCEL_FILE = os.path.join(ROOT, "NSE_symbols_filtered.xlsx")
EXCEL_FILE = MASTER_FILE

# Scanner shorthand -> real NSE symbol (one "ALIAS = REAL" per line).
ALIAS_FILE = os.path.join(BASE_DIR, "symbol_aliases.txt")

TRADE_LOG_FILE = os.path.join(ROOT, "trade_log.xlsx")
NGROK_EXE = os.path.join(ROOT, "ngrok.exe")
NGROK_CONFIG = os.path.join(ROOT, "ngrok.yml")

# Every webhook payload is appended here so we can audit what arrived and
# replay it in dry-run mode.
PAYLOAD_DIR = os.path.join(ROOT, "payloads")

# Missed-entry seeding. If this file exists when the bot starts, every
# "SYMBOL=PRICE" line is recorded as an open VIRTUAL short at that price, so
# the dashboard P&L and the trade log still cover entries the bot never saw
# (e.g. an alert rejected while the app was down). It sizes like a normal
# order, is monitored for SL/TP, and closes at EOD exactly like any other
# position. VIRTUAL only - it never places a broker order - and it runs at
# most once per day (a .done_<date> marker is written next to the file).
SEED_FILE = os.path.join(BASE_DIR, "seed_today.txt")

PORT = 5000

UI_PASSWORD = os.environ.get("SHOONYA_UI_PASSWORD", "shoonya")

# Shared secret for the scanner. The webhook is reachable from the internet
# through the ngrok tunnel, so without this anybody who guesses the URL could
# place orders in your account. Send it either as a query parameter
# (?token=...), as the header X-Webhook-Token, or as a "token" field in the
# JSON body.
#
# Order of preference:
#   1. the SHOONYA_WEBHOOK_TOKEN environment variable
#   2. the token saved in webhook_token.txt (generated once, then reused)
#   3. a fresh random token, generated and saved on first run
# Set the env var to an empty string to switch the check off completely.
#
# REQUIRE_WEBHOOK_TOKEN = False means the check is OFF: /webhook accepts any
# POST, exactly as it did before the token was added. Set it to True to
# require the token again - no other change is needed.
REQUIRE_WEBHOOK_TOKEN = False
WEBHOOK_TOKEN_FILE = os.path.join(ROOT, "webhook_token.txt")


def _load_webhook_token():
    env = os.environ.get("SHOONYA_WEBHOOK_TOKEN")
    if env is not None:
        return env.strip()
    try:
        with open(WEBHOOK_TOKEN_FILE, "r", encoding="utf-8") as fh:
            saved = fh.read().strip()
        if saved:
            return saved
    except OSError:
        pass
    import secrets
    token = secrets.token_urlsafe(24)
    try:
        with open(WEBHOOK_TOKEN_FILE, "w", encoding="utf-8") as fh:
            fh.write(token + "\n")
    except OSError:
        pass
    return token


WEBHOOK_TOKEN = _load_webhook_token() if REQUIRE_WEBHOOK_TOKEN else ""

VALID_TRIGGER_TIMES = [
    "09:45", "10:00", "10:15", "10:30", "10:45",
    "11:00", "11:15", "11:30", "13:00", "13:15",
]

MAX_STOCKS_PER_TIME = 3

DEFAULT_TRADING_CAP = 200000

PNL_STOP_LOSS_PCT = 0.006
PNL_TAKE_PROFIT_PCT = 0.014

MONITOR_INTERVAL = 0.5
POSITION_LOG_EVERY = 5

# Broker data caching: the monitor loop wakes up every MONITOR_INTERVAL, but
# live quotes/positions are only re-fetched once per TTL so the faster UI
# refresh never blows through the broker's rate limits.
QUOTE_CACHE_TTL = 1.0          # seconds a per-token LTP stays valid
POS_CACHE_TTL = 1.0            # seconds a broker position snapshot stays valid
CYCLE_LOG_EVERY = 15           # seconds between "Cycle #n" console lines

# Seconds to wait for a live exit order to actually fill before giving up and
# retrying. The position book (not order acceptance) is the source of truth.
EXIT_FILL_TIMEOUT = 8.0

# Kill switch: if the day's total PnL falls to -MAX_DAILY_LOSS or worse, square
# off everything and stop. 0 disables the check.
MAX_DAILY_LOSS = 0.0

# Quote sanity: reject a price that is more than this fraction away from the
# scanner's trigger price. A resolved-but-wrong instrument (HDFCLOWVOL at
# INR 19 for a HDFCLIFE signal at INR 1400) and dead tokens both get caught
# here, before any order is sized.
LTP_SANITY_PCT = 0.30

EOD_SQUARE_OFF = "15:10"

VIRTUAL_MODE_DEFAULT = True
