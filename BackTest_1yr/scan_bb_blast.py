"""
Chartink bb_blast_sell scan — exact logic reproduction
Evaluates after each 15-min bar closes and emits SELL signals.

[-2] = bar two steps before the current bar (alert bar)
[-1] = bar immediately before the current bar (alert bar)
"""
import os
import time
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "Stocks_DATA_15m")
OUTPUT   = os.path.join(BASE_DIR, "signals.csv")


def scan_symbol(filepath):
    sym = os.path.basename(filepath).replace(".xlsx", "")
    df = pd.read_excel(filepath, usecols=["time", "into", "inth", "intl", "intc", "intv",
                                           "BB_upper", "BB_mid", "BB_lower",
                                           "RSI", "VWAP", "ADX", "PLUS_DI", "MINUS_DI",
                                           "vol_SMA21"])
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)

    signals = []
    for i in range(2, len(df)):
        prev1 = df.iloc[i - 1]   # [-1]
        prev2 = df.iloc[i - 2]   # [-2]
        alert_time = df.iloc[i]["time"]

        try:
            p2_low  = float(prev2["intl"])
            p2_high = float(prev2["inth"])
            p2_bbup = float(prev2["BB_upper"])
            p2_vol  = float(prev2["intv"])

            p1_close = float(prev1["intc"])
            p1_open  = float(prev1["into"])
            p1_rsi   = float(prev1["RSI"])
            p1_bbup  = float(prev1["BB_upper"])
            p1_vwap  = float(prev1["VWAP"])
            p1_adx   = float(prev1["ADX"])
            p1_vol   = float(prev1["intv"])
            p1_sma   = float(prev1["vol_SMA21"])
        except (ValueError, TypeError):
            continue

        ok = (
            p2_low  >= p2_bbup and
            p2_high >= p2_bbup and
            p1_rsi  >= 60 and
            p1_close <= p1_bbup and
            p1_close >= 70 and
            p1_close <= 5000 and
            p1_close <= p1_open and
            p1_close <= p1_vwap and
            p1_adx  >= 22 and
            p1_vol  >= p1_sma and
            p2_vol  >= p1_sma
        )

        if ok:
            signals.append({
                "symbol": sym,
                "alert_time": alert_time.strftime("%Y-%m-%d %H:%M:%S"),
                "entry_price": p1_close,
                "RSI": round(p1_rsi, 2),
                "ADX": round(p1_adx, 2),
                "BB_upper": round(p2_bbup, 2),
            })

    return signals


def main():
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx"))
    print(f"Scanning {len(files)} symbols...")

    all_signals = []
    t0 = time.time()

    for i, fname in enumerate(files, 1):
        fp = os.path.join(DATA_DIR, fname)
        try:
            sigs = scan_symbol(fp)
            all_signals.extend(sigs)
            if i % 50 == 0 or i == len(files):
                elapsed = time.time() - t0
                print(f"[{i}/{len(files)}] — {len(all_signals)} signals so far | {elapsed:.0f}s")
        except Exception as e:
            print(f"[{i}/{len(files)}] {fname} — ERROR: {str(e)[:80]}")

    df = pd.DataFrame(all_signals)
    if not df.empty:
        df.sort_values("alert_time", inplace=True)
        df.to_csv(OUTPUT, index=False)

    elapsed = time.time() - t0
    print(f"\nDone — {len(all_signals)} signals | {elapsed:.0f}s")
    print(f"Saved: {OUTPUT}")

    if not df.empty:
        print(f"\nDate range: {df['alert_time'].min()} -> {df['alert_time'].max()}")
        print(f"Unique symbols: {df['symbol'].nunique()}")
        print(f"\nSignals per month:")
        df["month"] = pd.to_datetime(df["alert_time"]).dt.to_period("M")
        print(df.groupby("month").size().to_string())


if __name__ == "__main__":
    main()
