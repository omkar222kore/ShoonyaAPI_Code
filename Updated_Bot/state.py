import csv
import json
import os
import subprocess
import sys
import time

import config

CAPITAL_FILE = os.path.join(config.STATE_DIR, "capital.json")
LOGIN_FILE = os.path.join(config.STATE_DIR, "login.json")
TOKEN_SCRIPT = r"E:\ShoonyaAPI_Code\login_shoonya.py"
TOKEN_FILE = r"E:\ShoonyaAPI_Code\super_token.txt"

TRADE_FIELDS = [
    "Date", "Time", "Symbol", "TradingSymbol", "Token", "Qty",
    "Entry_Time", "Entry_Price", "Exit_Time", "Exit_Price", "Exit_Reason",
    "SL", "TP", "Gross_PnL", "Charges", "Est_Net_PnL", "Order_ID", "Mode",
]

SCAN_FIELDS = [
    "Date", "Time", "Scan", "Nifty_LTP", "Nifty_PrevClose", "Nifty_Pct",
    "Evaluated", "Bar_Timestamp", "Ready_Pct", "Stale_Count", "Raw_Matches",
    "Matched", "Reject_Summary", "Details", "Condition_Audit",
    "Action", "Reason", "Mode",
]


def _write_json(path, payload):
    config.ensure_dirs()
    temporary = path + ".tmp"
    for attempt in range(10):
        try:
            with open(temporary, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(temporary, path)
            return
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def load_state(day=None):
    config.ensure_dirs()
    day = day or config.today_ist()
    fresh = {
        "date": day,
        "open_positions": {},
        "traded_today": [],
        "completed_scans": [],
        "nifty_last": None,
        "paper": config.PAPER_TRADE,
        "updated_at": config.now_ist().isoformat(timespec="seconds"),
    }
    if not os.path.exists(config.STATE_FILE):
        return fresh
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return fresh
    if not isinstance(saved, dict) or saved.get("date") != day:
        return fresh
    for key, default in fresh.items():
        saved.setdefault(key, default)
    return saved


def save_state(state):
    state["updated_at"] = config.now_ist().isoformat(timespec="seconds")
    _write_json(config.STATE_FILE, state)


def _append_csv(path, fields, row):
    config.ensure_dirs()
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    normalized = {key: row.get(key, "") for key in fields}
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(normalized)


def append_trade(row):
    _append_csv(config.trade_csv_path(row.get("Date")), TRADE_FIELDS, row)


def append_scan(row):
    _append_csv(config.scan_log_path(row.get("Date")), SCAN_FIELDS, row)


def read_csv_rows(path, limit=200):
    if not path or not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows[-limit:]


def read_capital():
    if not os.path.exists(CAPITAL_FILE):
        return config.CAPITAL_PER_TRADE
    try:
        with open(CAPITAL_FILE, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        value = float(payload.get("capital", config.CAPITAL_PER_TRADE))
        return value if value > 0 else config.CAPITAL_PER_TRADE
    except (OSError, ValueError, TypeError):
        return config.CAPITAL_PER_TRADE


def write_capital(value):
    amount = float(value)
    if amount <= 0:
        raise ValueError("capital must be positive")
    payload = {"capital": amount, "updated_at": config.now_ist().isoformat(timespec="seconds")}
    _write_json(CAPITAL_FILE, payload)
    return amount


def read_login():
    fresh = {
        "status": "unknown",
        "last_login": None,
        "last_attempt": None,
        "duration_seconds": None,
        "message": "No login attempt recorded",
        "token_file": TOKEN_FILE,
    }
    if not os.path.exists(LOGIN_FILE):
        return fresh
    try:
        with open(LOGIN_FILE, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return fresh
    if not isinstance(payload, dict):
        return fresh
    for key, default in fresh.items():
        payload.setdefault(key, default)
    return payload


def write_login(payload):
    _write_json(LOGIN_FILE, payload)


def refresh_token():
    config.ensure_dirs()
    previous = read_login()
    started = time.monotonic()
    attempted_at = config.now_ist().isoformat(timespec="seconds")
    success = False
    detail = "login failed"
    try:
        completed = subprocess.run(
            [sys.executable, TOKEN_SCRIPT, "--headless", "--timeout", "90", "--save", TOKEN_FILE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=150,
        )
        success = completed.returncode == 0 and os.path.exists(TOKEN_FILE)
        lines = [line.strip() for line in (completed.stderr or "").splitlines() if line.strip()]
        detail = lines[-1] if lines else ("login completed" if success else "login failed")
    except Exception as exc:
        detail = str(exc)
    finished_at = config.now_ist().isoformat(timespec="seconds")
    duration = round(time.monotonic() - started, 1)
    payload = {
        "status": "success" if success else "failed",
        "last_login": finished_at if success else previous.get("last_login"),
        "last_attempt": attempted_at,
        "duration_seconds": duration,
        "message": "Login successful" if success else "Login failed: " + detail,
        "token_file": TOKEN_FILE,
    }
    write_login(payload)
    print("[%s] %s" % (finished_at, payload["message"]), file=sys.stderr, flush=True)
    return 0 if success else 1


def write_heartbeat(payload):
    _write_json(config.HEARTBEAT_FILE, payload)


def write_command(command):
    payload = {"command": command, "at": config.now_ist().isoformat(timespec="seconds")}
    _write_json(config.COMMAND_FILE, payload)


def read_command():
    if not os.path.exists(config.COMMAND_FILE):
        return None
    try:
        with open(config.COMMAND_FILE, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return None
    command = payload.get("command") if isinstance(payload, dict) else None
    return str(command).lower() if command else None


def clear_command():
    try:
        os.remove(config.COMMAND_FILE)
    except OSError:
        pass


def write_pid(path):
    config.ensure_dirs()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()) + "\n")


def read_pid(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def clear_pid(path):
    try:
        os.remove(path)
    except OSError:
        pass
