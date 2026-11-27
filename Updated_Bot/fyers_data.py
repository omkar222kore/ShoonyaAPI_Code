import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import pandas as pd

import config

HISTORY_COLUMNS = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]
_CLIENTS = {}
_CLIENT_LOCK = threading.Lock()
_RATE_LOCK = threading.Lock()
_RATE_TIMES = deque()
_RATE_LIMIT_UNTIL = 0.0
_RATE_LIMIT_WAIT = 62.0


def _token_path():
    path = config.FYERS_TOKEN_FILE
    if os.path.exists(path):
        return path
    root_path = os.path.join(config.ROOT, "token.txt")
    if os.path.exists(root_path):
        return root_path
    return path


def read_token():
    path = _token_path()
    if not os.path.exists(path):
        raise FileNotFoundError("FYERS token.txt not found: %s" % path)
    with open(path, "r", encoding="utf-8") as handle:
        token = handle.read().strip()
    if not token:
        raise ValueError("FYERS token.txt is empty: %s" % path)
    return token


def _client():
    path = _token_path()
    key = (path, config.FYERS_CLIENT_ID)
    with _CLIENT_LOCK:
        if key not in _CLIENTS:
            token = read_token()
            from fyers_apiv3 import fyersModel
            _CLIENTS[key] = fyersModel.FyersModel(
                client_id=config.FYERS_CLIENT_ID,
                token=token,
                is_async=False,
            )
        return _CLIENTS[key]


def _pace():
    global _RATE_LIMIT_UNTIL
    while True:
        with _RATE_LOCK:
            now = time.monotonic()
            if now < _RATE_LIMIT_UNTIL:
                delay = _RATE_LIMIT_UNTIL - now + 0.2
            else:
                while _RATE_TIMES and now - _RATE_TIMES[0] >= 1.0:
                    _RATE_TIMES.popleft()
                if len(_RATE_TIMES) < config.FYERS_MAX_REQ_PER_SEC:
                    _RATE_TIMES.append(now)
                    return
                delay = 1.0 - (now - _RATE_TIMES[0])
        time.sleep(max(delay, 0.01))


def _rate_limited(response):
    if not isinstance(response, dict) or str(response.get("s", "")).lower() == "ok":
        return False
    code = response.get("code")
    message = str(response.get("message", "")).lower()
    return code in (-360, -429, 429) or "rate limit" in message or "api request limit" in message


def _mark_rate_limited():
    global _RATE_LIMIT_UNTIL
    with _RATE_LOCK:
        _RATE_LIMIT_UNTIL = max(_RATE_LIMIT_UNTIL, time.monotonic() + _RATE_LIMIT_WAIT)


def _quote_value(response):
    if not isinstance(response, dict) or str(response.get("s", "")).lower() != "ok":
        return None
    data = response.get("d")
    if isinstance(data, dict):
        value = data.get("v")
        if isinstance(value, dict):
            return value
        for item in data.values():
            if isinstance(item, dict) and isinstance(item.get("v"), dict):
                return item["v"]
            if isinstance(item, dict) and "lp" in item:
                return item
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("symbol") == "NSE:NIFTY50-INDEX":
                nested = item.get("v")
                return nested if isinstance(nested, dict) else item
        if data and isinstance(data[0], dict):
            nested = data[0].get("v")
            return nested if isinstance(nested, dict) else data[0]
    return None


def get_nifty_quote():
    _pace()
    response = _client().quotes({"symbols": "NSE:NIFTY50-INDEX"})
    value = _quote_value(response)
    if value is None:
        return None
    try:
        ltp = float(value["lp"])
        previous = float(value.get("prev_close_price") or value.get("c"))
    except (KeyError, TypeError, ValueError):
        return None
    if ltp <= 0 or previous <= 0:
        return None
    return {"lp": ltp, "c": previous}


def fetch_fyers_15m(symbol, days_back=None):
    symbol = str(symbol).strip().upper()
    if symbol.endswith("-EQ"):
        symbol = symbol[:-3]
    days = int(days_back or config.FYERS_HISTORY_DAYS)
    end_date = config.now_ist().date()
    start_date = end_date - timedelta(days=days)
    payload = {
        "symbol": "NSE:%s-EQ" % symbol,
        "resolution": "15",
        "date_format": "1",
        "range_from": start_date.strftime("%Y-%m-%d"),
        "range_to": end_date.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }
    response = None
    for _ in range(15):
        _pace()
        response = _client().history(data=payload)
        if _rate_limited(response):
            _mark_rate_limited()
            continue
        break
    if not isinstance(response, dict) or str(response.get("s", "")).lower() != "ok":
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    candles = response.get("candles")
    if not isinstance(candles, list) or not candles:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    frame = pd.DataFrame(candles, columns=HISTORY_COLUMNS[:6])
    raw_times = pd.to_numeric(frame["Timestamp"], errors="coerce")
    largest = raw_times.abs().max()
    unit = "ms" if pd.notna(largest) and largest > 1e11 else "s"
    frame["Timestamp"] = pd.to_datetime(raw_times, unit=unit, utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    for column in HISTORY_COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    clock = frame["Timestamp"].dt.strftime("%H:%M")
    frame = frame.loc[(clock >= "09:15") & (clock <= "15:15")]
    frame = frame.dropna(subset=["Timestamp", "Close", "Volume"])
    frame = frame.drop_duplicates(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
    return frame[HISTORY_COLUMNS]


def refresh_fyers_cache(universe, days_back=None, only_symbols=None, max_workers=None):
    if only_symbols is None:
        targets = list(universe)
    else:
        selected = set()
        for item in only_symbols:
            if isinstance(item, dict):
                selected.add(str(item.get("symbol", "")).strip().upper())
            else:
                selected.add(str(item).strip().upper())
        targets = [item for item in universe if str(item.get("symbol", "")).strip().upper() in selected]
    if not targets:
        return {}
    cache = {}
    workers = int(max_workers or config.FYERS_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_fyers_15m, item["symbol"], days_back): item["symbol"]
            for item in targets
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                frame = future.result()
            except Exception:
                continue
            if frame is not None and not frame.empty:
                cache[symbol] = frame
    return cache
