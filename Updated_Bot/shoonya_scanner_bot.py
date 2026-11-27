import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd

import config
import fyers_data
import fyers_stream
import indicators
import state as app_state
from broker import ShoonyaBroker


PAPER_MODE = config.PAPER_TRADE
HISTORY_COLUMNS = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]


def log(message):
    print("[%s] %s" % (config.now_ist().strftime("%H:%M:%S"), message), flush=True)


def safe_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def round_tick(price):
    tick = 0.05 if price >= 250.0 else 0.01
    return round(round(price / tick) * tick, 2)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        return False
    if args.paper:
        return True
    return config.PAPER_TRADE


def load_universe():
    source = config.UNIVERSE_FILE if os.path.exists(config.UNIVERSE_FILE) else config.MASTER_FILE
    if not os.path.exists(source):
        raise FileNotFoundError("Nifty 500 universe file not found: %s" % source)

    def to_records(frame):
        if "Instrument" in frame.columns:
            frame = frame[frame["Instrument"].astype(str).str.upper().str.strip() == "EQ"]
        elif "TradingSymbol" in frame.columns:
            frame = frame[frame["TradingSymbol"].astype(str).str.upper().str.endswith("-EQ")]
        frame = frame.drop_duplicates(subset=["Symbol"])
        found = []
        for _, row in frame.iterrows():
            symbol = str(row.get("Symbol", "")).strip().upper()
            token = str(row.get("Token", "")).strip()
            trading_symbol = str(row.get("TradingSymbol", "")).strip().upper()
            if not symbol or not token or not trading_symbol:
                continue
            found.append({"symbol": symbol, "token": token, "tsym": trading_symbol})
        return found

    records = to_records(pd.read_excel(source))
    additions = []
    if os.path.abspath(source) != os.path.abspath(config.MASTER_FILE) and os.path.exists(config.MASTER_FILE):
        wanted = {str(symbol).strip().upper() for symbol in config.MISSING_82_STOCKS}
        master = pd.read_excel(config.MASTER_FILE)
        master = master[master["Symbol"].astype(str).str.strip().str.upper().isin(wanted)]
        additions = to_records(master)
        by_symbol = {row["symbol"]: row for row in records}
        for row in additions:
            by_symbol[row["symbol"]] = row
        records = list(by_symbol.values())
    if not records:
        raise ValueError("No EQ symbols found in %s" % source)
    log("Universe loaded: %d EQ symbols from %s + %d MISSING_82_STOCKS" % (len(records), os.path.basename(source), len(additions)))
    return records


def normalize_history(rows):
    normalized = []
    if not isinstance(rows, list):
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_time = item.get("time") or item.get("Time")
        timestamp = pd.to_datetime(raw_time, format="%d-%m-%Y %H:%M:%S", errors="coerce")
        if pd.isna(timestamp):
            continue
        clock = timestamp.strftime("%H:%M")
        if not ("09:15" <= clock <= "15:15"):
            continue
        try:
            normalized.append({
                "Timestamp": timestamp,
                "Open": safe_float(item.get("into")),
                "High": safe_float(item.get("inth")),
                "Low": safe_float(item.get("intl")),
                "Close": safe_float(item.get("intc")),
                "Volume": safe_float(item.get("v", item.get("vol", item.get("volume")))),
            })
        except (TypeError, ValueError):
            continue
    frame = pd.DataFrame(normalized, columns=HISTORY_COLUMNS)
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)


def keep_sessions(frame, sessions=None):
    if frame.empty:
        return frame
    sessions = sessions or config.TRADING_SESSIONS
    dates = sorted(set(frame["Timestamp"].dt.date))[-sessions:]
    return frame[frame["Timestamp"].dt.date.isin(dates)].reset_index(drop=True)


def fetch_history(broker, token, start=None, end=None, days_back=None, retries=2):
    end = end or config.now_ist()
    if start is None:
        start = end - timedelta(days=days_back or config.HISTORY_LOOKBACK_DAYS)
    last_error = None
    for attempt in range(retries):
        try:
            rows = broker.get_time_price_series(
                "NSE", token, int(start.timestamp()), int(end.timestamp()), 15
            )
            frame = normalize_history(rows)
            if not frame.empty:
                return keep_sessions(frame)
        except Exception as exc:
            last_error = exc
        time.sleep(0.25 * (attempt + 1))
    if last_error is not None:
        raise last_error
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def merge_history_frames(old, fresh):
    if fresh is None or fresh.empty:
        return old
    if old is None or old.empty:
        return keep_sessions(fresh)
    merged = pd.concat([fresh, old], ignore_index=True)
    return keep_sessions(
        merged.drop_duplicates(subset=["Timestamp"])
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )


def warmup_cache(universe):
    cache = fyers_data.refresh_fyers_cache(universe, days_back=config.FYERS_HISTORY_DAYS)
    failures = []
    for item in universe:
        frame = cache.get(item["symbol"])
        if frame is None or frame.empty:
            failures.append(item["symbol"])
    log("Warm-up complete: %d cached, %d failed" % (len(cache), len(failures)))
    return cache, failures


def cache_readiness(universe, cache, bar_timestamp):
    ready = []
    lagging = []
    for item in universe:
        symbol = item["symbol"]
        frame = cache.get(symbol)
        if frame is None or frame.empty or frame["Timestamp"].iloc[-1] < bar_timestamp:
            lagging.append(item)
        else:
            ready.append(symbol)
    return ready, lagging


def update_cache(universe, cache, bar_timestamp=None):
    fresh_map = {}
    if bar_timestamp is not None and fyers_stream.is_active():
        fresh_map = fyers_stream.consume(bar_timestamp)
        if fresh_map:
            log("FYERS stream supplied %d/%d bars for %s" % (
                len(fresh_map), len(universe), bar_timestamp.strftime("%H:%M")
            ))
    if not fresh_map:
        fresh_map = fyers_data.refresh_fyers_cache(universe, days_back=config.FYERS_SCAN_DAYS)
    for symbol, fresh in fresh_map.items():
        cache[symbol] = merge_history_frames(cache.get(symbol), fresh)
    failures = [
        item["symbol"] for item in universe
        if item["symbol"] not in fresh_map or fresh_map[item["symbol"]].empty
    ]
    if failures:
        log("FYERS update failures: %d symbols" % len(failures))
    return cache


def expected_bar_timestamp(scan_hm):
    now = config.now_ist()
    scan_time = datetime.strptime(scan_hm, "%H:%M").time()
    scan_dt = datetime.combine(now.date(), scan_time).replace(tzinfo=config.IST)
    return (scan_dt - timedelta(minutes=15)).replace(tzinfo=None)


def nifty_gate():
    quote = fyers_data.get_nifty_quote()
    if not quote:
        return None
    ltp = safe_float(quote.get("lp"), 0.0)
    previous = safe_float(quote.get("c"), 0.0)
    if ltp <= 0 or previous <= 0:
        return None
    percent = ((ltp - previous) / previous) * 100.0
    return {
        "ltp": ltp,
        "previous": previous,
        "percent": percent,
        "blocked": percent > config.NIFTY_MAX_PCT,
    }


def scan_row(now, scan_hm, nifty, candidates, action, reason, mode, evaluated="", reject_summary="", details="", bar_timestamp=None, ready_pct="", stale_count="", condition_audit=""):
    return {
        "Date": now.strftime("%Y-%m-%d"),
        "Time": now.strftime("%H:%M:%S"),
        "Scan": scan_hm,
        "Nifty_LTP": round(nifty["ltp"], 2) if nifty else "",
        "Nifty_PrevClose": round(nifty["previous"], 2) if nifty else "",
        "Nifty_Pct": round(nifty["percent"], 4) if nifty else "",
        "Evaluated": evaluated,
        "Bar_Timestamp": bar_timestamp.strftime("%Y-%m-%d %H:%M") if bar_timestamp is not None else "",
        "Ready_Pct": ready_pct,
        "Stale_Count": stale_count,
        "Raw_Matches": len(candidates) if candidates is not None else "",
        "Matched": ",".join(candidates) if candidates else "",
        "Reject_Summary": reject_summary,
        "Details": details,
        "Condition_Audit": condition_audit,
        "Action": action,
        "Reason": reason,
        "Mode": mode,
    }


def _fmt_value(value):
    try:
        if pd.isna(value):
            return "NA"
        return "%.2f" % float(value)
    except (TypeError, ValueError):
        return "NA"


def _condition_parts(frame):
    if frame is None or len(frame) < 30:
        return []
    features = indicators.compute_features(frame)
    current = features.iloc[-1]
    previous = features.iloc[-2]
    previous_target = previous["UBB"] * 0.9994
    vwap_target = current["VWAP"] * 1.0005
    volume_target = current["VSMA"] * 0.98
    checks = [
        ("PREV_LOW_BB", previous["Low"] >= previous_target, "prevLow %s>=%s" % (_fmt_value(previous["Low"]), _fmt_value(previous_target))),
        ("PREV_HIGH_BB", previous["High"] >= previous["UBB"], "prevHigh %s>=%s" % (_fmt_value(previous["High"]), _fmt_value(previous["UBB"]))),
        ("RSI_60", current["RSI"] >= 60.0, "RSI %s>=60.00" % _fmt_value(current["RSI"])),
        ("CLOSE_BELOW_BB", current["Close"] <= current["UBB"], "close %s<=%s" % (_fmt_value(current["Close"]), _fmt_value(current["UBB"]))),
        ("PRICE_MIN_70", current["Close"] >= 70.0, "close %s>=70.00" % _fmt_value(current["Close"])),
        ("PRICE_MAX_5000", current["Close"] <= 5000.0, "close %s<=5000.00" % _fmt_value(current["Close"])),
        ("RED_CANDLE", current["Close"] <= current["Open"], "close %s<=open %s" % (_fmt_value(current["Close"]), _fmt_value(current["Open"]))),
        ("CLOSE_NEAR_VWAP", current["Close"] <= vwap_target, "close %s<=%s" % (_fmt_value(current["Close"]), _fmt_value(vwap_target))),
        ("ADX_22", current["ADX"] >= 22.0, "ADX %s>=22.00" % _fmt_value(current["ADX"])),
        ("VOLUME_VSMA", current["Volume"] >= volume_target, "volume %s>=%s" % (_fmt_value(current["Volume"]), _fmt_value(volume_target))),
    ]
    result = []
    for label, condition, description in checks:
        passed = bool(condition) if pd.notna(condition) else False
        result.append((label, passed, "%s %s" % (label, description + (" OK" if passed else " FAIL"))))
    return result


def condition_audit(frames, statuses):
    parts = []
    for symbol in sorted(frames):
        if statuses.get(symbol) == "PASS":
            continue
        checks = _condition_parts(frames[symbol])
        if len(checks) < 2:
            continue
        if not checks[0][1] or not checks[1][1]:
            continue
        parts.append("%s[%s]" % (symbol, "|".join(item[2] for item in checks)))
    return " | ".join(parts)


def evaluate_candidates(cache, universe, bar_timestamp):
    by_symbol = {item["symbol"]: item for item in universe}
    frames = {}
    stale_count = 0
    for symbol, frame in cache.items():
        if symbol not in by_symbol or frame is None or frame.empty:
            stale_count += 1
            continue
        completed = frame.loc[frame["Timestamp"] <= bar_timestamp]
        if completed.empty or completed["Timestamp"].iloc[-1] != bar_timestamp:
            stale_count += 1
            continue
        frames[symbol] = completed
    eligible = sorted(frames.items())
    evaluated = len(eligible)
    try:
        features = indicators.compute_features_batch(frames, bar_timestamp)
        statuses = indicators.entry_status_batch(features)
    except Exception:
        statuses = {}
        for symbol, completed in eligible:
            if len(completed) < 30:
                statuses[symbol] = "INSUFFICIENT_HISTORY"
            else:
                statuses[symbol] = indicators.entry_status(indicators.compute_features(completed))
    for symbol in frames:
        statuses.setdefault(symbol, "INSUFFICIENT_HISTORY")
    matched = []
    rejects = {}
    samples = {}
    for symbol in sorted(statuses):
        status = statuses[symbol]
        if status == "PASS":
            matched.append(symbol)
            continue
        rejects[status] = rejects.get(status, 0) + 1
        samples.setdefault(status, []).append(symbol)
    parts = []
    for status in sorted(rejects, key=lambda key: (-rejects[key], key)):
        example = ",".join(samples[status][:3])
        parts.append("%s:%d (%s)" % (status, rejects[status], example))
    if stale_count:
        parts.append("STALE_BAR:%d" % stale_count)
    return sorted(matched), " | ".join(parts), evaluated, stale_count, condition_audit(frames, statuses)


def reconcile_positions(broker, universe, bot_state):
    if PAPER_MODE:
        for symbol in list(bot_state["open_positions"]):
            bot_state["traded_today"].append(symbol)
        bot_state["traded_today"] = sorted(set(bot_state["traded_today"]))
        return
    by_trading_symbol = {item["tsym"].upper(): item for item in universe}
    live = {}
    for item in broker.get_positions():
        if not isinstance(item, dict):
            continue
        trading_symbol = str(item.get("tsym", "")).strip().upper()
        try:
            net_qty = int(float(item.get("netqty", 0) or 0))
        except (TypeError, ValueError):
            continue
        if net_qty >= 0 or trading_symbol not in by_trading_symbol:
            continue
        record = by_trading_symbol[trading_symbol]
        entry_price = safe_float(item.get("avgprice"), 0.0)
        if entry_price <= 0:
            continue
        qty = abs(net_qty)
        live[record["symbol"]] = {
            "symbol": record["symbol"],
            "token": record["token"],
            "tsym": record["tsym"],
            "qty": qty,
            "entry_price": entry_price,
            "entry_time": "RECONCILED",
            "sl_price": round_tick(entry_price * (1.0 + config.SL_PCT)),
            "tp_price": round_tick(entry_price * (1.0 - config.TP_PCT)),
            "order_id": "RECONCILED",
        }
    bot_state["open_positions"] = live
    for symbol in live:
        bot_state["traded_today"].append(symbol)
    bot_state["traded_today"] = sorted(set(bot_state["traded_today"]))
    log("Reconciled live positions: %d" % len(live))


def enter_position(broker, record, ltp, bot_state, available_margin):
    qty = int(config.CAPITAL_PER_TRADE // ltp)
    if qty <= 0:
        return False, "zero quantity"
    if available_margin is not None:
        required_margin = qty * ltp * 0.20
        if available_margin < required_margin:
            return False, "insufficient margin"
    if not PAPER_MODE:
        order_id = broker.place_order(record["tsym"], qty, "S", "BB_BLAST_SHORT")
        fill = broker.wait_for_fill(order_id)
        if fill is None:
            return False, "entry fill failed"
        entry_price = fill.get("avgprc") or ltp
        filled_qty = fill.get("fillshares") or qty
    else:
        order_id = broker.place_order(record["tsym"], qty, "S", "BB_BLAST_SHORT")
        entry_price = ltp
        filled_qty = qty
    entry_price = safe_float(entry_price, ltp)
    filled_qty = int(filled_qty)
    if entry_price <= 0 or filled_qty <= 0:
        return False, "invalid fill"
    position = {
        "symbol": record["symbol"],
        "token": record["token"],
        "tsym": record["tsym"],
        "qty": filled_qty,
        "entry_price": entry_price,
        "entry_time": config.now_ist().strftime("%H:%M:%S"),
        "sl_price": round_tick(entry_price * (1.0 + config.SL_PCT)),
        "tp_price": round_tick(entry_price * (1.0 - config.TP_PCT)),
        "order_id": order_id,
    }
    bot_state["open_positions"][record["symbol"]] = position
    if record["symbol"] not in bot_state["traded_today"]:
        bot_state["traded_today"].append(record["symbol"])
    log("SHORT %s %s qty=%d entry=%.2f sl=%.2f tp=%.2f" % (
        record["symbol"], record["tsym"], filled_qty, entry_price,
        position["sl_price"], position["tp_price"],
    ))
    return True, "entered"


def close_position(broker, bot_state, symbol, reason, fallback_price=None):
    position = bot_state["open_positions"].get(symbol)
    if not position:
        return True
    tsym = position["tsym"]
    if not PAPER_MODE:
        remaining = broker.position_qty(tsym)
        if remaining >= 0:
            del bot_state["open_positions"][symbol]
            app_state.save_state(bot_state)
            return True
        close_qty = abs(remaining)
        order_id = broker.place_order(tsym, close_qty, "B", "BB_BLAST_EXIT")
        fill = broker.wait_for_fill(order_id)
        if fill is None:
            log("EXIT FAILED %s order=%s" % (symbol, order_id))
            return False
        exit_price = safe_float(fill.get("avgprc"), fallback_price or position["entry_price"])
        leftover = broker.position_qty(tsym)
        if leftover < 0:
            position["qty"] = abs(leftover)
            app_state.save_state(bot_state)
            return False
    else:
        exit_price = safe_float(fallback_price, position["entry_price"])
    gross = (position["entry_price"] - exit_price) * position["qty"]
    net = gross - config.CHARGE_PER_TRADE
    now = config.now_ist()
    app_state.append_trade({
        "Date": now.strftime("%Y-%m-%d"),
        "Time": now.strftime("%H:%M:%S"),
        "Symbol": symbol,
        "TradingSymbol": tsym,
        "Token": position["token"],
        "Qty": position["qty"],
        "Entry_Time": position["entry_time"],
        "Entry_Price": round(position["entry_price"], 2),
        "Exit_Time": now.strftime("%H:%M:%S"),
        "Exit_Price": round(exit_price, 2),
        "Exit_Reason": reason,
        "SL": round(position["sl_price"], 2),
        "TP": round(position["tp_price"], 2),
        "Gross_PnL": round(gross, 2),
        "Charges": config.CHARGE_PER_TRADE,
        "Est_Net_PnL": round(net, 2),
        "Order_ID": position.get("order_id", ""),
        "Mode": "PAPER" if PAPER_MODE else "LIVE",
    })
    del bot_state["open_positions"][symbol]
    app_state.save_state(bot_state)
    log("%s %s entry=%.2f exit=%.2f net=%.2f" % (
        reason, symbol, position["entry_price"], exit_price, net
    ))
    return True


def monitor_positions(broker, bot_state):
    for symbol, position in list(bot_state["open_positions"].items()):
        quote = broker.get_quote("NSE", position["token"])
        if not quote:
            continue
        ltp = safe_float(quote.get("lp"), 0.0)
        if ltp <= 0:
            continue
        reason = None
        if ltp >= position["sl_price"]:
            reason = "SL_HIT"
        elif ltp <= position["tp_price"]:
            reason = "TP_HIT"
        if reason:
            close_position(broker, bot_state, symbol, reason, ltp)


def square_off_all(broker, bot_state):
    for symbol in list(bot_state["open_positions"]):
        position = bot_state["open_positions"][symbol]
        quote = broker.get_quote("NSE", position["token"])
        ltp = safe_float(quote.get("lp"), 0.0) if quote else position["entry_price"]
        close_position(broker, bot_state, symbol, "EOD_305PM", ltp)


def run_scan(broker, bot_state, universe, cache, scan_hm, heartbeat):
    now = config.now_ist()
    mode = "PAPER" if PAPER_MODE else "LIVE"
    bar_timestamp = expected_bar_timestamp(scan_hm)
    ready_pct = ""
    stale_count = ""
    evaluated = ""
    reject_summary = ""
    audit = ""
    nifty = nifty_gate()
    heartbeat["nifty"] = nifty
    heartbeat["last_scan"] = scan_hm

    def add_row(candidates, action, reason, details=""):
        full_details = details
        if audit:
            full_details = (full_details + " | " if full_details else "") + "AUDIT " + audit
        app_state.append_scan(scan_row(
            now, scan_hm, nifty, candidates, action, reason, mode,
            evaluated=evaluated, reject_summary=reject_summary, details=full_details,
            bar_timestamp=bar_timestamp,
            ready_pct=round(ready_pct, 1) if isinstance(ready_pct, (int, float)) else ready_pct,
            stale_count=stale_count,
            condition_audit=audit,
        ))

    if nifty is None:
        add_row(None, "SKIPPED", "NIFTY_QUOTE_FAILED", "Nifty quote failed; scan not evaluated")
        log("Scan %s skipped: Nifty quote failed" % scan_hm)
        return
    log("Scan %s Nifty %.2f (%.2f%%)" % (scan_hm, nifty["ltp"], nifty["percent"]))
    if nifty["blocked"]:
        details = "Nifty %.2f (%+.2f%%) above +%.2f%%; scan not evaluated" % (
            nifty["ltp"], nifty["percent"], config.NIFTY_MAX_PCT
        )
        add_row(None, "SKIPPED", "NIFTY_GATE", details)
        log("Scan %s skipped: Nifty above +%.2f%%" % (scan_hm, config.NIFTY_MAX_PCT))
        return
    if fyers_stream.is_active():
        flushed = fyers_stream.flush_completed_bars(bar_timestamp)
        if flushed:
            log("FYERS stream flushed %d quiet bars for %s" % (
                flushed, bar_timestamp.strftime("%H:%M")
            ))
    update_cache(universe, cache, bar_timestamp)
    ready, lagging = cache_readiness(universe, cache, bar_timestamp)
    total = len(universe) or 1
    ready_pct = 100.0 * len(ready) / total
    if ready_pct < 90.0:
        for attempt in range(1, 9):
            log("Scan %s waiting for %s bar attempt %d/8 ready=%d/%d" % (
                scan_hm, bar_timestamp.strftime("%H:%M"), attempt, len(ready), total
            ))
            time.sleep(1.5)
            fresh = {}
            if fyers_stream.is_active():
                fresh = fyers_stream.consume(bar_timestamp)
            if not fresh:
                fresh = fyers_data.refresh_fyers_cache(
                    universe, days_back=config.FYERS_SCAN_DAYS, only_symbols=lagging
                )
            for symbol, frame in fresh.items():
                cache[symbol] = merge_history_frames(cache.get(symbol), frame)
            ready, lagging = cache_readiness(universe, cache, bar_timestamp)
            ready_pct = 100.0 * len(ready) / total
            if ready_pct >= 90.0:
                break
    log("Scan %s bar readiness %.1f%% ready=%d/%d expected=%s" % (
        scan_hm, ready_pct, len(ready), total, bar_timestamp.strftime("%Y-%m-%d %H:%M")
    ))
    if ready_pct < 90.0:
        details = "Expected bar %s missing for %d symbols; refusing stale evaluation" % (
            bar_timestamp.strftime("%H:%M"), len(lagging)
        )
        stale_count = len(lagging)
        add_row([], "SKIPPED", "STALE_BAR", details)
        return
    candidates, reject_summary, evaluated, stale_count, audit = evaluate_candidates(
        cache, universe, bar_timestamp
    )
    log("Scan %s raw matches: %d %s" % (scan_hm, len(candidates), candidates))
    if len(candidates) > config.MAX_SIGNALS_PER_TS:
        add_row(candidates, "SKIPPED", "CROWD_FILTER", ",".join(candidates))
        log("Scan %s skipped: more than %d signals" % (scan_hm, config.MAX_SIGNALS_PER_TS))
        return
    if not candidates:
        add_row(candidates, "NO_TRADE", "NO_SIGNAL", "No stock passed all 10 checks")
        return
    available_margin = broker.available_margin() if not PAPER_MODE else None
    by_symbol = {item["symbol"]: item for item in universe}
    for symbol in candidates:
        if symbol in bot_state["open_positions"]:
            add_row(candidates, "SKIPPED", "ALREADY_OPEN", symbol + ":ALREADY_OPEN")
            continue
        if symbol in bot_state["traded_today"]:
            add_row(candidates, "SKIPPED", "ALREADY_TRADED", symbol + ":ALREADY_TRADED")
            continue
        if len(bot_state["open_positions"]) >= config.MAX_CONCURRENT:
            add_row(candidates, "SKIPPED", "MAX_POSITIONS", symbol + ":MAX_POSITIONS")
            continue
        record = by_symbol[symbol]
        quote = broker.get_quote("NSE", record["token"])
        ltp = safe_float(quote.get("lp"), 0.0) if quote else 0.0
        if ltp <= 0:
            add_row(candidates, "SKIPPED", "LTP_UNAVAILABLE", symbol + ":LTP_UNAVAILABLE")
            continue
        entered, reason = enter_position(broker, record, ltp, bot_state, available_margin)
        add_row(candidates, "TRADED" if entered else "SKIPPED", reason, symbol + ":" + reason)
    app_state.save_state(bot_state)


def write_heartbeat(bot_state, heartbeat):
    payload = {
        "pid": os.getpid(),
        "running": True,
        "mode": "PAPER" if PAPER_MODE else "LIVE",
        "capital": config.CAPITAL_PER_TRADE,
        "time": config.now_ist().isoformat(timespec="seconds"),
        "date": config.today_ist(),
        "open_positions": len(bot_state["open_positions"]),
        "traded_today": len(bot_state["traded_today"]),
        "completed_scans": len(bot_state["completed_scans"]),
        "last_scan": heartbeat.get("last_scan"),
        "nifty": heartbeat.get("nifty"),
    }
    app_state.write_heartbeat(payload)


def run():
    global PAPER_MODE
    PAPER_MODE = parse_args()
    config.CAPITAL_PER_TRADE = app_state.read_capital()
    config.ensure_dirs()
    app_state.write_pid(config.BOT_PID_FILE)
    app_state.clear_command()
    mode = "PAPER" if PAPER_MODE else "LIVE"
    log("Starting Updated_Bot in %s mode | capital %.2f per trade" % (mode, config.CAPITAL_PER_TRADE))
    broker = ShoonyaBroker(config.USER_ID, config.TOKEN_FILE, PAPER_MODE, config.HTTP_TIMEOUT)
    universe = load_universe()
    if fyers_stream.start(universe):
        log("FYERS stream started: %s" % fyers_stream.snapshot())
    else:
        log("FYERS stream unavailable; using REST cache refresh")
    bot_state = app_state.load_state()
    bot_state["paper"] = PAPER_MODE
    reconcile_positions(broker, universe, bot_state)
    app_state.save_state(bot_state)
    cache = {}
    warmup_done = False
    heartbeat = {"last_scan": None, "nifty": None}
    while True:
        now = config.now_ist()
        hm = now.strftime("%H:%M")
        hms = now.strftime("%H:%M:%S")
        command = app_state.read_command()
        if command == "stop":
            log("Stop command received")
            app_state.clear_command()
            break
        if hms >= config.EOD_TIME:
            log("EOD square-off triggered")
            square_off_all(broker, bot_state)
            app_state.save_state(bot_state)
            write_heartbeat(bot_state, heartbeat)
            break
        if hms >= config.WARMUP_TIME and not warmup_done:
            log("Warm-up started")
            cache, _ = warmup_cache(universe)
            warmup_done = True
            app_state.save_state(bot_state)
        if warmup_done and bot_state["open_positions"]:
            monitor_positions(broker, bot_state)
        if warmup_done and hm in config.SCAN_TIMES and now.second >= 3:
            if hm not in bot_state["completed_scans"]:
                run_scan(broker, bot_state, universe, cache, hm, heartbeat)
                bot_state["completed_scans"].append(hm)
                bot_state["completed_scans"] = sorted(set(bot_state["completed_scans"]))
                app_state.save_state(bot_state)
        write_heartbeat(bot_state, heartbeat)
        time.sleep(config.MONITOR_INTERVAL)
    app_state.write_heartbeat({
        "pid": os.getpid(),
        "running": False,
        "mode": mode,
        "capital": config.CAPITAL_PER_TRADE,
        "time": config.now_ist().isoformat(timespec="seconds"),
        "date": config.today_ist(),
        "open_positions": len(bot_state["open_positions"]),
        "traded_today": len(bot_state["traded_today"]),
        "completed_scans": len(bot_state["completed_scans"]),
        "last_scan": heartbeat.get("last_scan"),
        "nifty": heartbeat.get("nifty"),
    })
    app_state.clear_pid(config.BOT_PID_FILE)
    log("Bot stopped cleanly")


if __name__ == "__main__":
    run()
