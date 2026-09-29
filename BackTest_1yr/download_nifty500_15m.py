"""
Nifty 500 — 15-min Data Downloader
Downloads 1 year of 15-min OHLCV data for ~503 NSE symbols via Shoonya API.
"""
import os
import sys
import time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from NorenRestApiPy.NorenApi import NorenApi
import yaml


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(
            host="https://trade.shoonya.com/NorenWClientWeb/",
            websocket="wss://trade.shoonya.com/NorenWSWeb/"
        )


# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR    = os.path.normpath(os.path.join(BASE_DIR, "..", "Testing_Use"))
CRED_FILE     = os.path.join(SHARED_DIR, "cred.yml")
UNIVERSE_FILE = os.path.join(SHARED_DIR, "NSE_symbols_filtered.xlsx")
OUTPUT_DIR    = os.path.join(BASE_DIR, "Stocks_DATA_15m")

# ── Settings ───────────────────────────────────────────────────────────
INTERVAL      = 15
MONTHS_BACK   = 12
SKIP_EXISTING = True
SLEEP_BETWEEN = 2
MAX_RETRIES   = 3
RETRY_DELAY   = 10
BACKOFF_AFTER = 5
BACKOFF_SLEEP = 60

START_EPOCH = (datetime.now() - relativedelta(months=MONTHS_BACK)).replace(
    hour=0, minute=0, second=0, microsecond=0
).timestamp()

os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Output dir : {OUTPUT_DIR}")
print(f"Start date : {datetime.fromtimestamp(START_EPOCH).strftime('%Y-%m-%d')}")
print(f"Interval   : {INTERVAL} min\n")


def login():
    with open(CRED_FILE) as f:
        cred = yaml.load(f, Loader=yaml.FullLoader)
    api = ShoonyaApiPy()

    # Read token: command-line arg > token.txt > prompt
    token_file = os.path.join(BASE_DIR, "token.txt")
    if len(sys.argv) > 1:
        super_token = sys.argv[1].strip()
    elif os.path.exists(token_file):
        super_token = open(token_file).read().strip()
    else:
        super_token = input("Paste your SuperToken: ").strip()

    ret = api.set_session(cred["user"], cred["pwd"], super_token)
    if ret:
        print(f"Login OK | User: {cred['user']}\n")
        return api
    print("Login FAILED")
    sys.exit(1)


def load_universe():
    df = pd.read_excel(UNIVERSE_FILE)
    df["TradingSymbol"] = df["TradingSymbol"].astype(str).str.strip().str.upper()
    df = df[(df["Instrument"] == "EQ") & (df["Exchange"] == "NSE")]
    symbols = list(zip(df["TradingSymbol"].tolist(), df["Token"].astype(str).tolist()))
    print(f"Universe: {len(symbols)} NSE EQ symbols\n")
    return symbols


def download(api, symbols):
    ok, fail, skip = [], [], []
    consecutive_fail = 0

    for i, (sym, token) in enumerate(symbols, 1):
        outfile = os.path.join(OUTPUT_DIR, f"{sym}.xlsx")

        if SKIP_EXISTING and os.path.exists(outfile):
            skip.append(sym)
            continue

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                ret = api.get_time_price_series(
                    exchange="NSE",
                    token=token,
                    starttime=START_EPOCH,
                    interval=INTERVAL
                )
                if ret and len(ret) > 0:
                    df = pd.DataFrame(ret)
                    df.sort_values("time", inplace=True)
                    df.to_excel(outfile, index=False)
                    ok.append(sym)
                    consecutive_fail = 0
                    print(f"[{i}/{len(symbols)}] {sym} — OK ({len(df)} candles)")
                    success = True
                    break
                else:
                    break
            except Exception as e:
                err = str(e)[:80]
                if attempt < MAX_RETRIES:
                    print(f"[{i}/{len(symbols)}] {sym} — retry {attempt}/{MAX_RETRIES}: {err}")
                    time.sleep(RETRY_DELAY * attempt)
                else:
                    print(f"[{i}/{len(symbols)}] {sym} — FAILED after {MAX_RETRIES} attempts: {err}")

        if not success:
            fail.append(sym)
            consecutive_fail += 1
            if consecutive_fail >= BACKOFF_AFTER:
                print(f"  ... pausing {BACKOFF_SLEEP}s after {consecutive_fail} consecutive failures ...")
                time.sleep(BACKOFF_SLEEP)
                consecutive_fail = 0

        time.sleep(SLEEP_BETWEEN)

    print(f"\nDone — OK: {len(ok)} | Fail: {len(fail)} | Skip: {len(skip)}")
    if fail:
        print(f"Failed: {fail}")
    return ok, fail, skip


def summary():
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".xlsx")]
    print(f"\n{'='*60}")
    print(f"Files in output dir: {len(files)}")
    print(f"{'='*60}")

    min_dates, max_dates, row_counts = [], [], []

    for f in sorted(files):
        try:
            df = pd.read_excel(os.path.join(OUTPUT_DIR, f), usecols=["time"])
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
            min_dates.append(df["time"].min())
            max_dates.append(df["time"].max())
            row_counts.append(len(df))
        except Exception:
            pass

    if min_dates:
        print(f"Earliest data : {min(min_dates).strftime('%Y-%m-%d %H:%M')}")
        print(f"Latest data   : {max(max_dates).strftime('%Y-%m-%d %H:%M')}")
        print(f"Total candles : {sum(row_counts):,}")
        print(f"Avg per symbol: {sum(row_counts)//len(row_counts):,}")

        one_yr_cutoff = datetime.now() - relativedelta(months=11)
        good = sum(1 for d in min_dates if d <= one_yr_cutoff)
        print(f"\nSymbols reaching 11+ months back: {good}/{len(row_counts)}")
    else:
        print("No data files found")


if __name__ == "__main__":
    api = login()
    symbols = load_universe()
    download(api, symbols)
    summary()
