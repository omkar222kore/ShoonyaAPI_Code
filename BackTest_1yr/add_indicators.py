"""
Add Indicators to 15-min data
Appends BB(20,2), RSI(14), VWAP, ADX(14), vol_SMA21 to each xlsx in Stocks_DATA_15m.
"""
import os
import sys
import time
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "Stocks_DATA_15m")


def compute_bb(close, period=20, num_std=2):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    return rsi


def compute_vwap(high, low, close, volume, time_col):
    tp = (high + low + close) / 3
    date_col = time_col.dt.date
    cum_tp_vol = (tp * volume).groupby(date_col).cumsum()
    cum_vol = volume.groupby(date_col).cumsum()
    return cum_tp_vol / cum_vol


def compute_adx(high, low, close, period=14):
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=high.index)

    alpha = 1 / period
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    smooth_plus = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    smooth_minus = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    plus_di = 100 * smooth_plus / atr
    minus_di = 100 * smooth_minus / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()

    return adx, plus_di, minus_di


def process_file(filepath):
    df = pd.read_excel(filepath)
    if "BB_mid" in df.columns:
        return False

    df["time"] = pd.to_datetime(df["time"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)

    close = df["intc"].astype(float)
    high = df["inth"].astype(float)
    low = df["intl"].astype(float)
    vol = df["intv"].astype(float)

    df["BB_mid"], df["BB_upper"], df["BB_lower"] = compute_bb(close, 20, 2)
    df["RSI"] = compute_rsi(close, 14)
    df["VWAP"] = compute_vwap(high, low, close, vol, df["time"])
    df["ADX"], df["PLUS_DI"], df["MINUS_DI"] = compute_adx(high, low, close, 14)
    df["vol_SMA21"] = vol.rolling(21).mean()

    df.to_excel(filepath, index=False)
    return True


def main():
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".xlsx"))
    print(f"Files: {len(files)}")

    ok, skip = 0, 0
    t0 = time.time()

    for i, fname in enumerate(files, 1):
        fp = os.path.join(DATA_DIR, fname)
        try:
            added = process_file(fp)
            if added:
                ok += 1
                if ok % 25 == 0 or i == len(files):
                    elapsed = time.time() - t0
                    print(f"[{i}/{len(files)}] {fname} — OK | {ok} indicators added | {elapsed:.0f}s elapsed")
            else:
                skip += 1
        except Exception as e:
            print(f"[{i}/{len(files)}] {fname} — ERROR: {str(e)[:80]}")

    elapsed = time.time() - t0
    print(f"\nDone — {ok} processed | {skip} skipped (already had indicators) | {elapsed:.0f}s")


if __name__ == "__main__":
    main()
