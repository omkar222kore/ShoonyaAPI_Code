import os
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
IST = timezone(timedelta(hours=5, minutes=30))

PAPER_TRADE = os.environ.get("SHOONYA_MODE", "paper").lower() != "live"
USER_ID = os.environ.get("SHOONYA_USER_ID", "FA74468")

TOKEN_FILE = os.environ.get("SHOONYA_TOKEN_FILE") or os.path.join(BASE_DIR, "super_token.txt")
if not os.path.exists(TOKEN_FILE):
    root_token = os.path.join(ROOT, "super_token.txt")
    if os.path.exists(root_token):
        TOKEN_FILE = root_token

FYERS_CLIENT_ID = os.environ.get("FYERS_CLIENT_ID", "9KFQ6AICZA-100")
FYERS_TOKEN_FILE = os.environ.get("FYERS_TOKEN_FILE") or os.path.join(BASE_DIR, "token.txt")
if not os.path.exists(FYERS_TOKEN_FILE):
    fyers_root_token = os.path.join(ROOT, "token.txt")
    if os.path.exists(fyers_root_token):
        FYERS_TOKEN_FILE = fyers_root_token
FYERS_WORKERS = 12
FYERS_MAX_REQ_PER_SEC = 5
FYERS_HISTORY_DAYS = 7
FYERS_SCAN_DAYS = 2
FYERS_STREAM_ENABLED = True
FYERS_BAR_MINUTES = 15

BASE_WEB_URL = "https://trade.shoonya.com/NorenWClientWeb"
MASTER_ZIP_URL = "https://api.shoonya.com/NSE_symbols.txt.zip"

DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_DIR = os.path.join(BASE_DIR, "state")
TRADE_DIR = os.path.join(BASE_DIR, "trades")
LOG_DIR = os.path.join(BASE_DIR, "logs")

UNIVERSE_FILE = os.path.join(DATA_DIR, "NSE_symbols_filtered.xlsx")
MASTER_FILE = os.path.join(DATA_DIR, "nse_equity_master.xlsx")

MISSING_82_STOCKS = [
    'ACI', 'AETHER', 'AKUMS', 'ALKYLAMINE', 'ALLCARGO', 'ALOKINDS', 'APLLTD',
    'ASTRAZEN', 'AVANTIFEED', 'AZAD', 'BALAMINES', 'BASF', 'BBOX', 'BIRLACORPN',
    'CAMPUS', 'CELLO', 'CENTURYPLY', 'CERA', 'CHEMPLASTS', 'CIEINDIA', 'CLEANMAX',
    'CSBBANK', 'CUPID', 'DBREALTY', 'EASEMYTRIP', 'EQUITASBNK', 'FINEORG',
    'FINPIPE', 'GAEL', 'GNFC', 'GODREJAGRO', 'GPPL', 'GRINDWELL', 'GSFC',
    'HAPPSTMNDS', 'HEGAM', 'INOXINDIA', 'JKLAKSHMI', 'JKPAPER', 'JSWHL',
    'JUSTDIAL', 'JYOTHYLAB', 'KANSAINER', 'KIRLOSBROS', 'KNRCON', 'KRBL', 'KSB',
    'MAHSEAMLES', 'MANYAVAR', 'MASTEK', 'METROBRAND', 'METROPOLIS', 'NETWORK18',
    'PNCINFRA', 'PRAJIND', 'QUESS', 'RATNAMANI', 'RAYMOND', 'RAYMONDLSL', 'RCF',
    'RENUKA', 'ROUTE', 'RTNINDIA', 'RUBICON', 'SANOFI', 'SANOFICONR', 'SANSERA',
    'SCHNEIDER', 'SKFINDIA', 'SPARC', 'SUNDRMFAST', 'SWSOLAR', 'TANLA',
    'TDPOWERSYS', 'TRIVENI', 'UJJIVANSFB', 'VAML', 'VARROC', 'VGUARD',
    'VINATIORGA', 'VIPIND', 'WESTLIFE'
]
STATE_FILE = os.path.join(STATE_DIR, "state.json")
COMMAND_FILE = os.path.join(STATE_DIR, "command.json")
HEARTBEAT_FILE = os.path.join(STATE_DIR, "heartbeat.json")
BOT_PID_FILE = os.path.join(STATE_DIR, "bot.pid")
DASHBOARD_PID_FILE = os.path.join(STATE_DIR, "dashboard.pid")

SCAN_TIMES = ["10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", "12:00"]
WARMUP_TIME = "09:45"
EOD_TIME = "15:05:00"
STOP_TIME = "15:10:00"

CAPITAL_PER_TRADE = 10000.0
MAX_CONCURRENT = 3
MAX_SIGNALS_PER_TS = 2
SL_PCT = 0.014
TP_PCT = 0.028
TICK_SIZE = 0.05
CHARGE_PER_TRADE = 35.0
PAPER_BROKERAGE = 11.80
STATUTORY_RATE = 0.0003555
SL_LMT_TRIGGER_MULTIPLIER = 1.014
SL_LMT_LIMIT_MULTIPLIER = 1.003
SL_ORDER_SYNC_INTERVAL = 2.0
LTP_MAX_AGE_SEC = 2.0
ORDER_STATUS_POLLS = 4
ORDER_STATUS_POLL_SEC = 0.25
NIFTY_TOKEN = "26000"
NIFTY_MAX_PCT = 0.60

MONITOR_INTERVAL = 0.5
HTTP_TIMEOUT = 12
MAX_WORKERS = 20
HISTORY_LOOKBACK_DAYS = 14
TRADING_SESSIONS = 5

DASHBOARD_PORT = 5010
DASHBOARD_HOST = "127.0.0.1"


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().strftime("%Y-%m-%d")


def trade_csv_path(date=None):
    day = date or today_ist()
    return os.path.join(TRADE_DIR, "trades_%s.csv" % day)


def scan_log_path(date=None):
    day = date or today_ist()
    return os.path.join(TRADE_DIR, "scans_%s.csv" % day)


def ensure_dirs():
    for path in (DATA_DIR, STATE_DIR, TRADE_DIR, LOG_DIR):
        os.makedirs(path, exist_ok=True)
