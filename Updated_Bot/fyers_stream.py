import os
import threading
import time
from collections import defaultdict
from datetime import datetime

import pandas as pd

import config
import fyers_data

_LOCK = threading.RLock()
_SOCKET = None
_STARTED = False
_CONNECTED = False
_TARGETS = set()
_SYMBOLS = []
_SUBSCRIBED = 0
_TICKS = 0
_SYMBOLS_SEEN = set()
_ERRORS = []
_BARS = defaultdict(list)
_PENDING = defaultdict(list)
_STATE = {}
_LTP = {}
_LTP_TS = {}


def log(message):
    print("[%s] %s" % (config.now_ist().strftime("%H:%M:%S"), message), flush=True)


def _fyers_symbol(item):
    symbol = str(item.get("symbol", "")).strip().upper()
    tsym = str(item.get("tsym") or ("%s-EQ" % symbol)).strip().upper()
    if not tsym.startswith("NSE:"):
        tsym = "NSE:%s" % tsym
    return tsym


def _base_symbol(value):
    symbol = str(value or "").strip().upper()
    if symbol.startswith("NSE:"):
        symbol = symbol[4:]
    if symbol.endswith("-EQ"):
        symbol = symbol[:-3]
    return symbol


def _parse_time(message):
    raw = message.get("last_traded_time") or message.get("exch_feed_time")
    if raw:
        try:
            value = float(raw)
            if value > 1e11:
                value /= 1000.0
            return datetime.fromtimestamp(value, config.IST).replace(tzinfo=None)
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    return config.now_ist().replace(tzinfo=None)


def _bar_time(timestamp):
    minutes = int(config.FYERS_BAR_MINUTES)
    bucket = (timestamp.minute // minutes) * minutes
    return timestamp.replace(minute=bucket, second=0, microsecond=0)


def _record_error(error):
    text = str(error)[:300]
    with _LOCK:
        _ERRORS.append(text)
        _ERRORS[:] = _ERRORS[-5:]
    log("FYERS stream error: %s" % text)


def _finalize(state):
    row = {
        "Timestamp": state["bucket"],
        "Open": float(state["open"]),
        "High": float(max(state["open"], state["high"])),
        "Low": float(min(state["open"], state["low"])),
        "Close": float(state["close"]),
        "Volume": int(max(state["volume"], 0)),
    }
    symbol = state["symbol"]
    for store in (_BARS, _PENDING):
        for index in range(len(store[symbol]) - 1, -1, -1):
            if store[symbol][index]["Timestamp"] == row["Timestamp"]:
                store[symbol][index] = row
                break
        else:
            store[symbol].append(row)
    if len(_BARS[symbol]) > 500:
        _BARS[symbol] = _BARS[symbol][-500:]
    if len(_PENDING[symbol]) > 100:
        _PENDING[symbol] = _PENDING[symbol][-100:]


def _handle_tick(message):
    global _TICKS, _SYMBOLS_SEEN
    symbol = _base_symbol(message.get("symbol"))
    if not symbol or symbol not in _TARGETS:
        return
    try:
        ltp = float(message.get("ltp"))
    except (TypeError, ValueError):
        return
    if ltp <= 0:
        return
    try:
        cumulative_volume = int(float(message.get("vol_traded_today") or 0))
    except (TypeError, ValueError):
        cumulative_volume = 0
    bucket = _bar_time(_parse_time(message))
    with _LOCK:
        _TICKS += 1
        _SYMBOLS_SEEN.add(symbol)
        _LTP[symbol] = ltp
        _LTP_TS[symbol] = time.time()
        state = _STATE.get(symbol)
        if state is None:
            _STATE[symbol] = {
                "symbol": symbol,
                "bucket": bucket,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "base_volume": cumulative_volume,
                "last_volume": cumulative_volume,
                "volume": 0,
                "valid": False,
                "flushed": False,
            }
            return
        if bucket < state["bucket"]:
            return
        if bucket > state["bucket"]:
            if state["valid"] and not state["flushed"]:
                _finalize(state)
            _STATE[symbol] = {
                "symbol": symbol,
                "bucket": bucket,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "base_volume": state["last_volume"],
                "last_volume": cumulative_volume,
                "volume": max(cumulative_volume - state["last_volume"], 0),
                "valid": True,
                "flushed": False,
            }
            return
        state["high"] = max(state["high"], ltp)
        state["low"] = min(state["low"], ltp)
        state["close"] = ltp
        state["last_volume"] = cumulative_volume
        state["volume"] = max(cumulative_volume - state["base_volume"], 0)
        state["valid"] = True
        if state["flushed"]:
            _finalize(state)


def _on_message(message):
    global _SUBSCRIBED
    if not isinstance(message, dict):
        return
    kind = str(message.get("type", "")).lower()
    if kind == "sub":
        code = message.get("code")
        if code in (200, "200"):
            with _LOCK:
                _SUBSCRIBED += 1
        else:
            _record_error(message)
        return
    if kind in ("cn", "unsub", "ful", "pull"):
        return
    if kind == "sf":
        _handle_tick(message)


def start(universe):
    global _STARTED, _SOCKET, _CONNECTED, _TARGETS, _SYMBOLS
    if not config.FYERS_STREAM_ENABLED:
        return False
    with _LOCK:
        if _STARTED:
            return True
        _TARGETS = {
            str(item.get("symbol", "")).strip().upper()
            for item in universe
            if str(item.get("symbol", "")).strip()
        }
        _SYMBOLS = list(dict.fromkeys(_fyers_symbol(item) for item in universe))
        _CONNECTED = False
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        token = fyers_data.read_token()
        from fyers_apiv3.FyersWebsocket import data_ws

        def on_connect():
            global _CONNECTED
            with _LOCK:
                _CONNECTED = True
            try:
                _SOCKET.subscribe(symbols=list(_SYMBOLS), data_type="SymbolUpdate", channel=11)
            except Exception as exc:
                _record_error(exc)

        def on_close(message):
            global _CONNECTED
            with _LOCK:
                _CONNECTED = False
            log("FYERS stream closed: %s" % str(message)[:200])

        socket = data_ws.FyersDataSocket(
            access_token="%s:%s" % (config.FYERS_CLIENT_ID, token),
            log_path=config.LOG_DIR + os.sep,
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=on_connect,
            on_message=_on_message,
            on_error=_record_error,
            on_close=on_close,
            reconnect_retry=50,
        )
        with _LOCK:
            _SOCKET = socket
        socket.connect()
        with _LOCK:
            _STARTED = True
        log("FYERS stream requested for %d symbols" % len(_SYMBOLS))
        return True
    except Exception as exc:
        _record_error(exc)
        return False


def flush_completed_bars(bar_timestamp):
    flushed = 0
    with _LOCK:
        for state in _STATE.values():
            if state["bucket"] <= bar_timestamp and state["valid"] and not state["flushed"]:
                _finalize(state)
                state["flushed"] = True
                flushed += 1
    return flushed


def is_active():
    with _LOCK:
        return _STARTED and _CONNECTED and bool(_SYMBOLS_SEEN)


def consume(bar_timestamp):
    if bar_timestamp is None:
        return {}
    result = {}
    with _LOCK:
        for symbol, rows in list(_PENDING.items()):
            keep = []
            matched = None
            for row in rows:
                if row["Timestamp"] == bar_timestamp:
                    matched = row
                elif row["Timestamp"] > bar_timestamp:
                    keep.append(row)
            if matched is not None:
                result[symbol] = pd.DataFrame([matched], columns=fyers_data.HISTORY_COLUMNS)
            if keep:
                _PENDING[symbol] = keep
            else:
                _PENDING.pop(symbol, None)
    return result


def get_ltp(symbol, max_age_sec=1.0):
    key = _base_symbol(symbol)
    with _LOCK:
        price = _LTP.get(key)
        stamp = _LTP_TS.get(key)
    if price is None or stamp is None:
        return None
    if max_age_sec is not None and (time.time() - stamp) > max_age_sec:
        return None
    return float(price)


def ltp_snapshot():
    with _LOCK:
        now = time.time()
        return {
            symbol: {"ltp": price, "age": now - _LTP_TS.get(symbol, now)}
            for symbol, price in _LTP.items()
        }


def snapshot():
    with _LOCK:
        return {
            "started": _STARTED,
            "connected": _CONNECTED,
            "requested_symbols": len(_SYMBOLS),
            "subscribe_acks": _SUBSCRIBED,
            "ticks": _TICKS,
            "symbols_seen": len(_SYMBOLS_SEEN),
            "pending_bars": sum(len(rows) for rows in _PENDING.values()),
            "errors": list(_ERRORS),
        }
