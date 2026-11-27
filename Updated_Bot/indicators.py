import numpy as np
import pandas as pd


def rsi_wilder_seeded(close, period=14):
    series = pd.Series(close).reset_index(drop=True).astype(float)
    delta = series.diff().values
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.full(len(series), np.nan)
    avg_loss = np.full(len(series), np.nan)
    if len(series) > period:
        avg_gain[period] = np.mean(gain[1:period + 1])
        avg_loss[period] = np.mean(loss[1:period + 1])
        for idx in range(period + 1, len(series)):
            avg_gain[idx] = (avg_gain[idx - 1] * (period - 1) + gain[idx]) / period
            avg_loss[idx] = (avg_loss[idx - 1] * (period - 1) + loss[idx]) / period
    rsi = np.full(len(series), np.nan)
    valid = np.isfinite(avg_gain) & np.isfinite(avg_loss) & (avg_loss > 0)
    rsi[valid] = 100.0 - (100.0 / (1.0 + avg_gain[valid] / avg_loss[valid]))
    rsi[np.isfinite(avg_gain) & (avg_loss == 0) & (avg_gain > 0)] = 100.0
    rsi[np.isfinite(avg_gain) & (avg_loss == 0) & (avg_gain == 0)] = 50.0
    return pd.Series(rsi, index=series.index)


def adx_wilder_seeded(high, low, close, period=14):
    high_series = pd.Series(high).reset_index(drop=True).astype(float)
    low_series = pd.Series(low).reset_index(drop=True).astype(float)
    close_series = pd.Series(close).reset_index(drop=True).astype(float)
    prev_close = close_series.shift(1)
    tr = np.maximum(
        high_series - low_series,
        np.maximum((high_series - prev_close).abs(), (low_series - prev_close).abs()),
    ).values
    up = (high_series - high_series.shift(1)).values
    down = (low_series.shift(1) - low_series).values
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    length = len(close_series)
    tr_smooth = np.full(length, np.nan)
    plus_smooth = np.full(length, np.nan)
    minus_smooth = np.full(length, np.nan)
    if length > period:
        tr_smooth[period] = np.sum(tr[1:period + 1])
        plus_smooth[period] = np.sum(plus_dm[1:period + 1])
        minus_smooth[period] = np.sum(minus_dm[1:period + 1])
        for idx in range(period + 1, length):
            tr_smooth[idx] = tr_smooth[idx - 1] - (tr_smooth[idx - 1] / period) + tr[idx]
            plus_smooth[idx] = plus_smooth[idx - 1] - (plus_smooth[idx - 1] / period) + plus_dm[idx]
            minus_smooth[idx] = minus_smooth[idx - 1] - (minus_smooth[idx - 1] / period) + minus_dm[idx]
    denom = np.where(tr_smooth == 0, np.nan, tr_smooth)
    plus_di = 100.0 * (plus_smooth / denom)
    minus_di = 100.0 * (minus_smooth / denom)
    di_sum = plus_di + minus_di
    dx = 100.0 * (np.abs(plus_di - minus_di) / np.where(di_sum == 0, np.nan, di_sum))
    adx = np.full(length, np.nan)
    if length > 2 * period:
        adx[2 * period] = np.mean(dx[period + 1:2 * period + 1])
        for idx in range(2 * period + 1, length):
            adx[idx] = (adx[idx - 1] * (period - 1) + dx[idx]) / period
    return pd.Series(adx, index=close_series.index)


def compute_features(df):
    out = df.copy().reset_index(drop=True)
    sma20 = out["Close"].rolling(20).mean()
    std20 = out["Close"].rolling(20).std(ddof=0)
    out["UBB"] = (sma20 + 2.0 * std20).round(2)
    out["RSI"] = rsi_wilder_seeded(out["Close"], 14)
    out["ADX"] = adx_wilder_seeded(out["High"], out["Low"], out["Close"], 14)
    session_date = out["Timestamp"].dt.date
    turnover = (out["Close"] * out["Volume"]).groupby(session_date).cumsum()
    volume_sum = out["Volume"].groupby(session_date).cumsum().replace(0, np.nan)
    out["VWAP"] = (turnover / volume_sum).round(2)
    out["VSMA"] = out["Volume"].rolling(21).mean()
    return out


def entry_status(df):
    if df is None or len(df) < 2:
        return "INSUFFICIENT_HISTORY"
    current = df.iloc[-1]
    previous = df.iloc[-2]
    required = ("UBB", "RSI", "ADX", "VWAP", "VSMA", "High", "Low", "Close", "Open", "Volume")
    if any(key not in df.columns for key in required):
        return "MISSING_INDICATORS"
    if any(pd.isna(current[key]) or pd.isna(previous[key]) for key in ("UBB", "RSI", "ADX", "VWAP", "VSMA")):
        return "INDICATOR_NA"
    checks = [
        ("PREV_LOW_BB", bool(previous["Low"] >= previous["UBB"] * 0.9994)),
        ("PREV_HIGH_BB", bool(previous["High"] >= previous["UBB"])),
        ("RSI_60", bool(current["RSI"] >= 60.0)),
        ("CLOSE_BELOW_BB", bool(current["Close"] <= current["UBB"])),
        ("PRICE_MIN_70", bool(current["Close"] >= 70.0)),
        ("PRICE_MAX_5000", bool(current["Close"] <= 5000.0)),
        ("RED_CANDLE", bool(current["Close"] <= current["Open"])),
        ("CLOSE_NEAR_VWAP", bool(current["Close"] <= current["VWAP"] * 1.0005)),
        ("ADX_22", bool(current["ADX"] >= 22.0)),
        ("VOLUME_VSMA", bool(current["Volume"] >= current["VSMA"] * 0.98)),
    ]
    for label, passed in checks:
        if not passed:
            return label
    return "PASS"


def entry_passed(df):
    return entry_status(df) == "PASS"


def _grouped_wilder_rsi(frame, period=14):
    if frame is None or frame.empty:
        return np.array([], dtype=float)
    codes, _ = pd.factorize(frame["Symbol"], sort=False)
    groups = int(codes.max()) + 1
    pos = frame.groupby("Symbol", sort=False).cumcount().to_numpy(dtype=int)
    delta = frame.groupby("Symbol", sort=False)["Close"].diff().to_numpy(dtype=float)
    delta = np.nan_to_num(delta, nan=0.0, posinf=0.0, neginf=0.0)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.full(len(frame), np.nan, dtype=float)
    avg_loss = np.full(len(frame), np.nan, dtype=float)
    seed_mask = (pos >= 1) & (pos <= period)
    seed_gain = np.bincount(codes[seed_mask], weights=gain[seed_mask], minlength=groups) / float(period)
    seed_loss = np.bincount(codes[seed_mask], weights=loss[seed_mask], minlength=groups) / float(period)
    seed_idx = np.where(pos == period)[0]
    if seed_idx.size:
        avg_gain[seed_idx] = seed_gain[codes[seed_idx]]
        avg_loss[seed_idx] = seed_loss[codes[seed_idx]]
    prev_gain = np.full(groups, np.nan, dtype=float)
    prev_loss = np.full(groups, np.nan, dtype=float)
    if seed_idx.size:
        prev_gain[codes[seed_idx]] = avg_gain[seed_idx]
        prev_loss[codes[seed_idx]] = avg_loss[seed_idx]
    max_pos = int(pos.max()) if pos.size else 0
    for step in range(period + 1, max_pos + 1):
        candidates = np.where(pos == step)[0]
        if candidates.size == 0:
            continue
        c = codes[candidates]
        ok = np.isfinite(prev_gain[c])
        candidates = candidates[ok]
        c = c[ok]
        if candidates.size == 0:
            continue
        avg_gain[candidates] = (prev_gain[c] * (period - 1) + gain[candidates]) / float(period)
        avg_loss[candidates] = (prev_loss[c] * (period - 1) + loss[candidates]) / float(period)
        prev_gain[c] = avg_gain[candidates]
        prev_loss[c] = avg_loss[candidates]
    rsi = np.full(len(frame), np.nan, dtype=float)
    valid = np.isfinite(avg_gain) & np.isfinite(avg_loss) & (avg_loss > 0)
    rsi[valid] = 100.0 - (100.0 / (1.0 + avg_gain[valid] / avg_loss[valid]))
    flat = np.isfinite(avg_gain) & (avg_loss == 0)
    rsi[flat & (avg_gain > 0)] = 100.0
    rsi[flat & (avg_gain == 0)] = 50.0
    return rsi


def _grouped_wilder_adx(frame, period=14):
    if frame is None or frame.empty:
        return np.array([], dtype=float)
    codes, _ = pd.factorize(frame["Symbol"], sort=False)
    groups = int(codes.max()) + 1
    pos = frame.groupby("Symbol", sort=False).cumcount().to_numpy(dtype=int)
    grouped = frame.groupby("Symbol", sort=False)
    high = frame["High"].to_numpy(dtype=float)
    low = frame["Low"].to_numpy(dtype=float)
    close = frame["Close"].to_numpy(dtype=float)
    prev_close = grouped["Close"].shift(1).to_numpy(dtype=float)
    prev_high = grouped["High"].shift(1).to_numpy(dtype=float)
    prev_low = grouped["Low"].shift(1).to_numpy(dtype=float)
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    up = high - prev_high
    down = prev_low - low
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = np.nan_to_num(tr, nan=0.0, posinf=0.0, neginf=0.0)
    plus_dm = np.nan_to_num(plus_dm, nan=0.0, posinf=0.0, neginf=0.0)
    minus_dm = np.nan_to_num(minus_dm, nan=0.0, posinf=0.0, neginf=0.0)
    tr_smooth = np.full(len(frame), np.nan, dtype=float)
    plus_smooth = np.full(len(frame), np.nan, dtype=float)
    minus_smooth = np.full(len(frame), np.nan, dtype=float)
    seed_mask = (pos >= 1) & (pos <= period)
    seed_tr = np.bincount(codes[seed_mask], weights=tr[seed_mask], minlength=groups)
    seed_plus = np.bincount(codes[seed_mask], weights=plus_dm[seed_mask], minlength=groups)
    seed_minus = np.bincount(codes[seed_mask], weights=minus_dm[seed_mask], minlength=groups)
    seed_idx = np.where(pos == period)[0]
    if seed_idx.size:
        tr_smooth[seed_idx] = seed_tr[codes[seed_idx]]
        plus_smooth[seed_idx] = seed_plus[codes[seed_idx]]
        minus_smooth[seed_idx] = seed_minus[codes[seed_idx]]
    prev_tr = np.full(groups, np.nan, dtype=float)
    prev_plus = np.full(groups, np.nan, dtype=float)
    prev_minus = np.full(groups, np.nan, dtype=float)
    if seed_idx.size:
        prev_tr[codes[seed_idx]] = tr_smooth[seed_idx]
        prev_plus[codes[seed_idx]] = plus_smooth[seed_idx]
        prev_minus[codes[seed_idx]] = minus_smooth[seed_idx]
    max_pos = int(pos.max()) if pos.size else 0
    for step in range(period + 1, max_pos + 1):
        candidates = np.where(pos == step)[0]
        if candidates.size == 0:
            continue
        c = codes[candidates]
        ok = np.isfinite(prev_tr[c])
        candidates = candidates[ok]
        c = c[ok]
        if candidates.size == 0:
            continue
        tr_smooth[candidates] = prev_tr[c] - prev_tr[c] / float(period) + tr[candidates]
        plus_smooth[candidates] = prev_plus[c] - prev_plus[c] / float(period) + plus_dm[candidates]
        minus_smooth[candidates] = prev_minus[c] - prev_minus[c] / float(period) + minus_dm[candidates]
        prev_tr[c] = tr_smooth[candidates]
        prev_plus[c] = plus_smooth[candidates]
        prev_minus[c] = minus_smooth[candidates]
    plus_di = np.full(len(frame), np.nan, dtype=float)
    minus_di = np.full(len(frame), np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        np.divide(100.0 * plus_smooth, tr_smooth, out=plus_di, where=tr_smooth > 0)
        np.divide(100.0 * minus_smooth, tr_smooth, out=minus_di, where=tr_smooth > 0)
    di_sum = plus_di + minus_di
    dx = np.full(len(frame), np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        np.divide(100.0 * np.abs(plus_di - minus_di), di_sum, out=dx, where=di_sum > 0)
    adx = np.full(len(frame), np.nan, dtype=float)
    adx_seed_mask = (pos > period) & (pos <= 2 * period) & np.isfinite(dx)
    dx_sum = np.bincount(codes[adx_seed_mask], weights=dx[adx_seed_mask], minlength=groups)
    dx_count = np.bincount(codes[adx_seed_mask], minlength=groups)
    seed_adx = np.full(groups, np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        np.divide(dx_sum, dx_count, out=seed_adx, where=dx_count > 0)
    seed_adx_idx = np.where(pos == 2 * period)[0]
    prev_adx = np.full(groups, np.nan, dtype=float)
    if seed_adx_idx.size:
        adx[seed_adx_idx] = seed_adx[codes[seed_adx_idx]]
        prev_adx[codes[seed_adx_idx]] = adx[seed_adx_idx]
    for step in range(2 * period + 1, max_pos + 1):
        candidates = np.where(pos == step)[0]
        if candidates.size == 0:
            continue
        c = codes[candidates]
        ok = np.isfinite(prev_adx[c]) & np.isfinite(dx[candidates])
        candidates = candidates[ok]
        c = c[ok]
        if candidates.size == 0:
            continue
        adx[candidates] = (prev_adx[c] * (period - 1) + dx[candidates]) / float(period)
        prev_adx[c] = adx[candidates]
    return adx


def compute_features_batch(frames, bar_timestamp=None):
    base_cols = ["Symbol", "Timestamp", "Open", "High", "Low", "Close", "Volume"]
    pieces = []
    for symbol, frame in (frames or {}).items():
        if frame is None or frame.empty:
            continue
        part = frame.copy()
        if bar_timestamp is not None:
            part = part.loc[part["Timestamp"] <= bar_timestamp]
        if len(part) < 30:
            continue
        part = part[["Timestamp", "Open", "High", "Low", "Close", "Volume"]].copy()
        part["Symbol"] = str(symbol).strip().upper()
        pieces.append(part[base_cols])
    if not pieces:
        return pd.DataFrame(columns=base_cols + ["UBB", "RSI", "ADX", "VWAP", "VSMA"])
    out = pd.concat(pieces, ignore_index=True)
    out = out.sort_values(["Symbol", "Timestamp"], kind="mergesort").reset_index(drop=True)
    grouped = out.groupby("Symbol", sort=False)
    close_roll = grouped["Close"].rolling(20)
    mean = close_roll.mean().reset_index(level=0, drop=True)
    std = close_roll.std(ddof=0).reset_index(level=0, drop=True)
    out["UBB"] = (mean + 2.0 * std).round(2).reindex(out.index).to_numpy()
    out["VSMA"] = grouped["Volume"].rolling(21).mean().reset_index(level=0, drop=True).reindex(out.index).to_numpy()
    out["Session"] = out["Timestamp"].dt.date
    session = [out["Symbol"], out["Session"]]
    turnover = (out["Close"] * out["Volume"]).groupby(session, sort=False).cumsum()
    volume_sum = out["Volume"].groupby(session, sort=False).cumsum().replace(0, np.nan)
    out["VWAP"] = (turnover / volume_sum).round(2)
    out["RSI"] = _grouped_wilder_rsi(out)
    out["ADX"] = _grouped_wilder_adx(out)
    return out


def entry_status_batch(features):
    if features is None or features.empty:
        return {}
    ordered = features.sort_values(["Symbol", "Timestamp"], kind="mergesort").reset_index(drop=True)
    codes, symbols = pd.factorize(ordered["Symbol"], sort=False)
    counts = np.bincount(codes)
    valid = counts >= 2
    if not valid.any():
        return {}
    symbols = symbols[valid]
    counts = counts[valid]
    last_pos = np.cumsum(counts) - 1
    prev_pos = last_pos - 1
    current = ordered.iloc[last_pos].copy()
    previous = ordered.iloc[prev_pos].copy()
    current.index = symbols
    previous.index = symbols
    common = current.index.intersection(previous.index)
    if not len(common):
        return {}
    current = current.loc[common]
    previous = previous.loc[common]
    status = pd.Series("PASS", index=common, dtype=object)
    indicator_cols = ["UBB", "RSI", "ADX", "VWAP", "VSMA"]
    missing = current[indicator_cols].isna().any(axis=1) | previous[indicator_cols].isna().any(axis=1)
    status.loc[missing] = "INDICATOR_NA"
    checks = [
        ("PREV_LOW_BB", previous["Low"] >= previous["UBB"] * 0.9994),
        ("PREV_HIGH_BB", previous["High"] >= previous["UBB"]),
        ("RSI_60", current["RSI"] >= 60.0),
        ("CLOSE_BELOW_BB", current["Close"] <= current["UBB"]),
        ("PRICE_MIN_70", current["Close"] >= 70.0),
        ("PRICE_MAX_5000", current["Close"] <= 5000.0),
        ("RED_CANDLE", current["Close"] <= current["Open"]),
        ("CLOSE_NEAR_VWAP", current["Close"] <= current["VWAP"] * 1.0005),
        ("ADX_22", current["ADX"] >= 22.0),
        ("VOLUME_VSMA", current["Volume"] >= current["VSMA"] * 0.98),
    ]
    for label, condition in checks:
        failed = (status == "PASS") & ~condition.fillna(False)
        status.loc[failed] = label
    return status.to_dict()
