"""
Backtest report generator.

Reads a backtest_*.xlsx produced by the Testing_WEBUI backtester and writes a
self-contained HTML report:

  * overview KPIs, month-wise and week-wise P&L
  * a full drawdown-episode breakdown
  * profit give-back analysis (candle 1-minute data): how far each trade ran
    into profit before it closed - catches "peaked +2200, closed -1200" trades
  * a per-day view of the highest combined profit touched vs what it closed at
  * a per-trade table

A flat cost (default Rs.83) is deducted from every trade to give the net P&L;
gross and net are both reported. The give-back / touched-profit sections are
computed from the raw 1-minute candles (entry = close at Entry Time,
qty = int(capital / entry)) so they are internally consistent.

Usage:
    python analyse_results.py                       # newest results\\backtest_*.xlsx
    python analyse_results.py path\\to\\file.xlsx
    python analyse_results.py file.xlsx --tax 100
    python analyse_results.py file.xlsx --capital 200000 --out report.html
    python analyse_results.py file.xlsx --no-candles    # skip give-back (fast)
"""
import argparse
import glob
import html
import os
from datetime import datetime

import pandas as pd

import config as cfg

DEFAULT_TAX = 83
DEFAULT_CAPITAL = 200000
REVERSAL_PEAK = 1000.0

COLUMNS = {
    "Stock Name": "sym",
    "Entry Time": "entry",
    "Hit/Exit Time": "exit",
    "Price": "price",
    "Status": "status",
    "Profit/Loss Amount": "gross",
}

CANDLE_COLS = ["time", "intl", "inth", "intc"]
CANDLE_CACHE_DIR = os.path.join(cfg.RESULTS_DIR, "_candle_cache")

_candle_mem = {}


# ---------------------------------------------------------------- data


def find_default_input():
    files = glob.glob(os.path.join(cfg.RESULTS_DIR, "backtest_*.xlsx"))
    if not files:
        raise SystemExit(f"No backtest_*.xlsx found in {cfg.RESULTS_DIR}")
    return max(files, key=os.path.getmtime)


def load_trades(path, tax):
    if not os.path.exists(path):
        raise SystemExit(f"File not found: {path}")
    df = pd.read_excel(path)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing column(s) in {os.path.basename(path)}: {missing}")
    df = df.rename(columns=COLUMNS)[list(COLUMNS.values())]
    df["entry"] = pd.to_datetime(df["entry"], errors="coerce")
    df["exit"] = pd.to_datetime(df["exit"], errors="coerce")
    df = df.dropna(subset=["entry", "gross"])
    df = df.sort_values(["entry", "exit"]).reset_index(drop=True)
    df["tax"] = float(tax)
    df["net"] = df["gross"] - df["tax"]
    df["cum_net"] = df["net"].cumsum()
    return df


def _candle_path(sym):
    return os.path.join(cfg.STOCKS_DATA_DIR, f"{sym}-EQ.xlsx")


def load_candles(sym):
    """1-minute OHLC for a symbol (time, intl, inth, intc). None if unavailable."""
    if sym in _candle_mem:
        return _candle_mem[sym]
    path = _candle_path(sym)
    if not os.path.exists(path):
        _candle_mem[sym] = None
        return None

    df = None
    cache = os.path.join(CANDLE_CACHE_DIR, f"{sym}.pkl")
    try:
        mtime, cached = pd.read_pickle(cache)
        if mtime == os.path.getmtime(path):
            df = cached
    except Exception:
        df = None

    if df is None:
        read = {"usecols": CANDLE_COLS}
        try:
            df = pd.read_excel(path, engine="calamine", **read)
        except Exception:
            df = pd.read_excel(path, **read)
        df["time"] = pd.to_datetime(df["time"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
        df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
        try:
            os.makedirs(CANDLE_CACHE_DIR, exist_ok=True)
            pd.to_pickle((os.path.getmtime(path), df), cache)
        except Exception:
            pass

    _candle_mem[sym] = df
    return df


# ---------------------------------------------------------------- analysis


def _block(sub, tax):
    gross = float(sub["gross"].sum())
    n = len(sub)
    return {
        "n": n,
        "gross": gross,
        "tax": float(tax) * n,
        "net": gross - float(tax) * n,
        "wins": int((sub["gross"] > 0).sum()),
        "losses": int((sub["gross"] < 0).sum()),
        "net_wins": int((sub["net"] > 0).sum()),
        "net_losses": int((sub["net"] < 0).sum()),
    }


def compute_excursions(df, capital, log=print):
    """Per-trade peak profit / worst point from 1-minute candles.

    entry price = intc at Entry Time; qty = int(capital / entry); the trade runs
    from Entry Time to Hit/Exit Time. Peak uses the candle low (best case for a
    short), worst uses the candle high. code_pl is the candle-consistent final
    P&L, so give-back = peak - code_pl is internally consistent.
    """
    for c in ("ep", "qty", "code_pl", "peak", "peak_time", "worst", "giveback"):
        if c not in df.columns:
            df[c] = pd.NA

    syms = sorted(set(df["sym"]))
    log(f"Loading candles for {len(syms)} symbols...")
    loaded = 0
    for i, s in enumerate(syms, 1):
        if load_candles(s) is not None:
            loaded += 1
        if i % 20 == 0 or i == len(syms):
            log(f"  candles {i}/{len(syms)}")
    log(f"  candle data for {loaded}/{len(syms)} symbols")

    for idx, r in df.iterrows():
        cand = load_candles(r["sym"])
        if cand is None:
            continue
        at_entry = cand[cand["time"] == r["entry"]]
        if at_entry.empty:
            continue
        ep = float(at_entry.iloc[0]["intc"])
        if ep <= 0:
            continue
        qty = int(capital / ep)
        if qty <= 0:
            continue

        window = cand[(cand["time"] > r["entry"]) & (cand["time"] <= r["exit"])]
        if window.empty:
            window = cand[(cand["time"] >= r["entry"]) & (cand["time"] <= r["exit"])]
        if window.empty:
            continue

        low_i = window["intl"].idxmin()
        high_i = window["inth"].idxmax()
        peak = (ep - float(window.at[low_i, "intl"])) * qty
        worst = (ep - float(window.at[high_i, "inth"])) * qty
        code_pl = (ep - float(r["price"])) * qty

        df.at[idx, "ep"] = ep
        df.at[idx, "qty"] = qty
        df.at[idx, "code_pl"] = code_pl
        df.at[idx, "peak"] = peak
        df.at[idx, "peak_time"] = window.at[low_i, "time"]
        df.at[idx, "worst"] = worst
        df.at[idx, "giveback"] = peak - code_pl
    return df


def daily_breakdown(df):
    """Per trading day: highest combined P&L touched vs what it closed at.

    Builds a minute-by-minute combined P&L curve for the day (open trades valued
    at their candle low - the best case the day "touched", closed trades held at
    their realised P&L) and reports the maximum.
    """
    days = []
    for date, g in df.groupby(df["entry"].dt.date):
        g = g.sort_values("entry")
        first, last = g["entry"].min(), g["exit"].max()
        minutes = pd.date_range(first, last, freq="1min")
        total = pd.Series(0.0, index=minutes)

        closed = 0.0
        best = None
        n_data = 0
        for _, r in g.iterrows():
            code = r["code_pl"]
            if pd.isna(code):
                continue
            code = float(code)
            closed += code
            best = code if best is None else max(best, code)

            cand = load_candles(r["sym"])
            if cand is None or pd.isna(r["ep"]):
                total.loc[minutes >= r["exit"]] += code
                continue
            n_data += 1
            sl = cand[(cand["time"] >= r["entry"]) & (cand["time"] <= r["exit"])]
            if sl.empty:
                total.loc[minutes >= r["exit"]] += code
                continue
            u = (float(r["ep"]) - sl.set_index("time")["intl"]) * float(r["qty"])
            u = u.reindex(minutes).ffill().fillna(0.0)
            u.loc[minutes >= r["exit"]] = code
            total = total.add(u, fill_value=0.0)

        days.append({
            "date": date,
            "n": len(g),
            "n_data": n_data,
            "touched": float(total.max()) if len(total) else 0.0,
            "touch_time": total.idxmax() if len(total) else None,
            "closed": closed,
            "giveback": (float(total.max()) - closed) if len(total) else 0.0,
            "best": best if best is not None else 0.0,
        })
    return days


def drawdown_episodes(df):
    """Peak-to-trough drawdown episodes on the net equity curve.

    Index 0 of the curve is the starting equity of 0 before the first trade.
    """
    times = [df.at[0, "entry"]] + list(df["entry"])
    equity = [0.0] + list(df["cum_net"])

    peak = []
    run = float("-inf")
    for v in equity:
        run = max(run, v)
        peak.append(run)

    episodes = []
    cur = None
    for i in range(1, len(equity)):
        dd = peak[i] - equity[i]
        if dd > 0:
            if cur is None:
                cur = {"i_pk": i - 1, "i0": i, "max": dd, "i_tr": i}
            elif dd > cur["max"]:
                cur["max"] = dd
                cur["i_tr"] = i
        elif cur is not None:
            cur["i1"] = i
            episodes.append(cur)
            cur = None
    if cur is not None:
        cur["i1"] = None
        episodes.append(cur)

    for ep in episodes:
        ep["peak_eq"] = equity[ep["i_pk"]]
        ep["trough_eq"] = equity[ep["i_tr"]]
        ep["peak_date"] = times[ep["i_pk"]]
        ep["trough_date"] = times[ep["i_tr"]]
        ep["recovery_date"] = None if ep["i1"] is None else times[ep["i1"]]
        if ep["i1"] is None:
            ep["days"] = (times[-1] - times[ep["i_pk"]]).days
        else:
            ep["days"] = (times[ep["i1"]] - times[ep["i_pk"]]).days
        ep["trades"] = ep["i_tr"] - ep["i_pk"]
        ep["pct"] = (ep["max"] / ep["peak_eq"] * 100) if ep["peak_eq"] else 0.0
        ep["ongoing"] = ep["i1"] is None

    return times, equity, peak, episodes


def analyse(df, tax, capital, with_candles=True, log=print):
    if with_candles:
        df = compute_excursions(df, capital, log=log)

    times, equity, peak, episodes = drawdown_episodes(df)
    max_dd = max((ep["max"] for ep in episodes), default=0.0)
    peak_eq = max(peak) if peak else 0.0

    overview = _block(df, tax)
    overview["final_equity"] = equity[-1]
    overview["peak_equity"] = peak_eq
    overview["max_dd_gross"] = _gross_max_dd(df)
    overview["max_dd_net"] = max_dd
    overview["max_dd_net_pct"] = (max_dd / peak_eq * 100) if peak_eq else 0.0
    overview["best"] = float(df["gross"].max())
    overview["worst"] = float(df["gross"].min())
    overview["net_best"] = float(df["net"].max())
    overview["net_worst"] = float(df["net"].min())
    overview["start"] = df["entry"].min()
    overview["end"] = df["entry"].max()
    overview["wr"] = 100.0 * overview["wins"] / overview["n"] if overview["n"] else 0.0
    overview["net_wr"] = 100.0 * overview["net_wins"] / overview["n"] if overview["n"] else 0.0

    months = [(_label_period(p, "M"), _block(s, tax))
              for p, s in df.groupby(df["entry"].dt.to_period("M"))]
    weeks = [(_week_label(p), _block(s, tax))
             for p, s in df.groupby(df["entry"].dt.to_period("W"))]

    res = {
        "overview": overview,
        "months": months,
        "weeks": weeks,
        "times": times,
        "equity": equity,
        "peak": peak,
        "episodes": episodes,
        "days": [],
        "excursion": None,
        "with_candles": with_candles,
    }

    if with_candles:
        days = daily_breakdown(df)
        res["days"] = days
        pk = df["peak"].dropna()
        gb = df["giveback"].dropna()
        res["excursion"] = {
            "total_giveback": float(gb[gb > 0].sum()),
            "worst_giveback": float(gb.max()) if len(gb) else 0.0,
            "reversals": int(((df["peak"] >= REVERSAL_PEAK) & (df["code_pl"] <= 0)).sum()),
            "best_peak": float(pk.max()) if len(pk) else 0.0,
            "touched_over_close": int((pd.Series([d["giveback"] for d in days]) > 0).sum()),
        }
    return res, df


def _label_period(p, freq):
    return p.strftime("%Y-%m") if freq == "M" else str(p)


def _week_label(p):
    return f"{p.start_time.strftime('%d %b')} - {p.end_time.strftime('%d %b %Y')}"


def _gross_max_dd(df):
    times = [0.0] + list(df["gross"].cumsum())
    run = float("-inf")
    worst = 0.0
    for v in times:
        run = max(run, v)
        worst = max(worst, run - v)
    return worst


# ---------------------------------------------------------------- rendering


def money(v):
    return f"{v:,.2f}"


def cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "zero")


def esc(s):
    return html.escape(str(s))


def num_val(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return money(float(v))


def svg_equity(times, equity, peak, episodes, width=1040, height=340):
    pad_l, pad_r, pad_t, pad_b = 78, 24, 22, 34
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(equity)
    lo = min(min(equity), 0.0)
    hi = max(max(equity), 0.0)
    if hi == lo:
        hi = lo + 1.0
    span = hi - lo

    def x(i):
        return pad_l + (i / (n - 1)) * plot_w

    def y(v):
        return pad_t + (hi - v) / span * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" '
             f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">']
    parts.append(f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" '
                 f'fill="none" stroke="#2a3245"/>')

    ticks = 5
    for k in range(ticks + 1):
        v = lo + span * k / ticks
        yy = y(v)
        parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l + plot_w}" y2="{yy:.1f}" '
                     f'stroke="#1e2433"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" class="ax" text-anchor="end">'
                     f'{money(v)}</text>')

    for ep in episodes:
        x0 = x(ep["i_pk"])
        x1 = x(n - 1 if ep["i1"] is None else ep["i1"])
        parts.append(f'<rect x="{x0:.1f}" y="{pad_t}" width="{max(x1 - x0, 1):.1f}" '
                     f'height="{plot_h}" fill="#ff4d5e" opacity="0.14"/>')
        parts.append(f'<circle cx="{x(ep["i_tr"]):.1f}" cy="{y(ep["trough_eq"]):.1f}" '
                     f'r="3" fill="#ff4d5e"/>')

    peak_pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(peak))
    parts.append(f'<polyline points="{peak_pts}" fill="none" stroke="#5b6b8c" '
                 f'stroke-width="1.2" stroke-dasharray="5 4"/>')

    eq_pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(equity))
    parts.append(f'<polyline points="{eq_pts}" fill="none" stroke="#33d69f" stroke-width="2"/>')

    parts.append(f'<text x="{pad_l}" y="{height - 10}" class="ax">'
                 f'{times[0].strftime("%d %b %Y")}</text>')
    parts.append(f'<text x="{pad_l + plot_w}" y="{height - 10}" class="ax" '
                 f'text-anchor="end">{times[-1].strftime("%d %b %Y")}</text>')
    parts.append('</svg>')
    return "".join(parts)


def bars_table(rows, label_head, cols):
    """rows: list of (label, block). cols: which of gross/tax/net to show."""
    values = []
    for _, b in rows:
        values += [abs(b[c]) for c in cols]
    top = max(values) if values else 1.0

    head = "".join(f'<th class="num">{c.upper()}</th>' for c in cols)
    body = []
    for label, b in rows:
        cells = []
        for c in cols:
            v = b[c]
            w = (abs(v) / top * 100) if top else 0
            cells.append(
                f'<td class="num {cls(v)}"><span class="bar-wrap">'
                f'<span class="bar {cls(v)}" style="width:{w:.1f}%"></span>'
                f'<span class="bar-val">{money(v)}</span></span></td>')
        body.append(
            f'<tr><td>{esc(label)}</td><td class="num">{b["n"]}</td>'
            f'<td class="num">{b["wins"]}/{b["losses"]}</td>' + "".join(cells) + '</tr>')
    return (f'<table class="grid"><thead><tr><th>{esc(label_head)}</th>'
            f'<th class="num">TRADES</th><th class="num">W/L</th>{head}</tr></thead>'
            f'<tbody>' + "".join(body) + '</tbody></table>')


def daily_table(days):
    if not days:
        return '<p class="dim">No daily data.</p>'
    rows = []
    for d in sorted(days, key=lambda x: x["date"]):
        gb = d["giveback"]
        touch = d["touch_time"]
        tstr = touch.strftime("%H:%M") if touch is not None else "-"
        rows.append(
            f'<tr><td>{d["date"].strftime("%d %b %Y")}</td>'
            f'<td class="num">{d["n"]}</td>'
            f'<td class="num pos">{money(d["touched"])}</td>'
            f'<td class="dim num">{tstr}</td>'
            f'<td class="num {cls(d["closed"])}">{money(d["closed"])}</td>'
            f'<td class="num {cls(-gb) if gb > 0 else "zero"}">'
            f'{"-" if gb <= 0 else money(gb)}</td>'
            f'<td class="num {cls(d["best"])}">{money(d["best"])}</td></tr>')
    return ('<table class="grid"><thead><tr><th>DATE</th><th class="num">TRADES</th>'
            '<th class="num">HIGHEST TOUCHED</th><th class="num">AT</th>'
            '<th class="num">CLOSED</th><th class="num">GIVEN BACK</th>'
            '<th class="num">BEST TRADE</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table>')


def _dt(v):
    if v is None or pd.isna(v):
        return ""
    return pd.Timestamp(v).strftime("%d-%b-%Y %H:%M")


def write_excel(path, df, res, tax, capital):
    """Write the trade / daily / summary analysis to a new workbook."""
    try:
        from openpyxl.styles import Font
    except Exception:
        Font = None

    trades = pd.DataFrame({
        "#": range(1, len(df) + 1),
        "Stock Name": df["sym"].values,
        "Entry Time": df["entry"].dt.strftime("%d-%b-%Y %H:%M").values,
        "Exit Time": df["exit"].dt.strftime("%d-%b-%Y %H:%M").values,
        "Status": df["status"].values,
        "Exit Price": df["price"].values,
        "P&L (file)": df["gross"].values,
        "Entry Price": df["ep"].values,
        "Qty": df["qty"].values,
        "Max Gain (peak)": df["peak"].values,
        "Peak Time": [_dt(v) for v in df["peak_time"]],
        "Worst": df["worst"].values,
        "Given Back": df["giveback"].values,
        "Candle P&L": df["code_pl"].values,
        "Cost": df["tax"].values,
        "Net (file)": df["net"].values,
    })

    days = pd.DataFrame([{
        "Date": d["date"].strftime("%d-%b-%Y"),
        "Trades": d["n"],
        "Highest Touched": round(d["touched"], 2),
        "At": "" if d["touch_time"] is None else pd.Timestamp(d["touch_time"]).strftime("%H:%M"),
        "Closed": round(d["closed"], 2),
        "Given Back": round(d["giveback"], 2) if d["giveback"] > 0 else 0.0,
        "Best Trade": round(d["best"], 2),
    } for d in sorted(res["days"], key=lambda x: x["date"])])

    ov = res["overview"]
    exc = res.get("excursion") or {}
    summary = pd.DataFrame([
        ("Source", os.path.basename(res.get("src", ""))),
        ("Trades", ov["n"]),
        ("Gross P&L (file)", round(ov["gross"], 2)),
        ("Cost per trade", tax),
        ("Total cost", round(ov["tax"], 2)),
        ("Net P&L (file)", round(ov["net"], 2)),
        ("Win rate net %", round(ov["net_wr"], 1)),
        ("Max drawdown net", round(ov["max_dd_net"], 2)),
        ("Max drawdown net %", round(ov["max_dd_net_pct"], 1)),
        ("Best trade (file)", round(ov["net_best"], 2)),
        ("Worst trade (file)", round(ov["net_worst"], 2)),
        ("Capital per trade", capital),
        ("Max gain reached (peak)", round(exc.get("best_peak", 0.0), 2)),
        ("Total given back", round(exc.get("total_giveback", 0.0), 2)),
        ("Worst give-back", round(exc.get("worst_giveback", 0.0), 2)),
        ("Reversals (peak>=1000, closed<=0)", exc.get("reversals", 0)),
    ], columns=["Metric", "Value"])

    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        trades.to_excel(xl, sheet_name="Trades", index=False)
        days.to_excel(xl, sheet_name="Daily", index=False)
        summary.to_excel(xl, sheet_name="Summary", index=False)

        if Font:
            for sheet in xl.sheets.values():
                for cell in sheet[1]:
                    cell.font = Font(bold=True)
            money_fmt = "#,##0.00"
            trade_ws = xl.sheets["Trades"]
            for col in ("G", "H", "J", "L", "M", "N", "O", "P"):
                for c in range(2, len(trades) + 2):
                    trade_ws[f"{col}{c}"].number_format = money_fmt
            day_ws = xl.sheets["Daily"]
            for col in ("C", "E", "F", "G"):
                for c in range(2, len(days) + 2):
                    day_ws[f"{col}{c}"].number_format = money_fmt
            widths = {"A": 5, "B": 14, "C": 18, "D": 18, "E": 22, "F": 11,
                      "G": 12, "H": 11, "I": 8, "J": 15, "K": 18, "L": 11,
                      "M": 12, "N": 12, "O": 9, "P": 12}
            for col, w in widths.items():
                trade_ws.column_dimensions[col].width = w
            for col, w in {"A": 14, "B": 9, "C": 16, "D": 8, "E": 12,
                           "F": 12, "G": 12}.items():
                day_ws.column_dimensions[col].width = w
            for col, w in {"A": 34, "B": 16}.items():
                xl.sheets["Summary"].column_dimensions[col].width = w
    return path


def render_html(path, df, res, tax, capital):
    ov = res["overview"]
    gen = datetime.now().strftime("%d %b %Y %H:%M:%S")
    src = os.path.basename(path)
    exc = res.get("excursion")

    cards = [
        ("NET P&L", money(ov["net"]), cls(ov["net"]), f'gross {money(ov["gross"])}'),
        ("TOTAL COST", money(-ov["tax"]), "neg", f'{ov["n"]} trades x {money(tax)}'),
        ("GROSS P&L", money(ov["gross"]), cls(ov["gross"]), "before costs"),
        ("TRADES", str(ov["n"]), "neutral", f'{ov["wins"]}W / {ov["losses"]}L'),
        ("WIN RATE", f'{ov["net_wr"]:.1f}%', "neutral", f'gross {ov["wr"]:.1f}%'),
        ("MAX DRAWDOWN", money(ov["max_dd_net"]), "neg",
         f'{ov["max_dd_net_pct"]:.1f}% of peak | gross {money(ov["max_dd_gross"])}'),
        ("FINAL EQUITY", money(ov["final_equity"]), cls(ov["final_equity"]),
         f'peak {money(ov["peak_equity"])}'),
        ("BEST / WORST", f'{money(ov["net_best"])} / {money(ov["net_worst"])}', "neutral",
         "net per trade"),
    ]
    if exc:
        cards += [
            ("PROFIT GIVEN BACK", money(exc["total_giveback"]), "neg",
             "unrealised peaks that slipped away"),
            ("REVERSALS", str(exc["reversals"]), "neg",
             f'peaked >= {money(REVERSAL_PEAK)} then closed <= 0'),
            ("WORST GIVE-BACK", money(exc["worst_giveback"]), "neg",
             f'best peak reached {money(exc["best_peak"])}'),
        ]
    cards_html = "".join(
        f'<div class="kpi"><div class="kpi-l">{esc(t)}</div>'
        f'<div class="kpi-v {c}">{esc(v)}</div><div class="kpi-s">{esc(s)}</div></div>'
        for t, v, c, s in cards)

    chart = svg_equity(res["times"], res["equity"], res["peak"], res["episodes"])

    months = bars_table(res["months"], "Month", ["gross", "tax", "net"])
    weeks = bars_table(res["weeks"], "Week", ["net"])
    daily = daily_table(res["days"]) if exc else '<p class="dim">Candle analysis disabled.</p>'

    dd_rows = []
    for k, ep in enumerate(res["episodes"], 1):
        rec = ("<span class='ongoing'>ONGOING</span>" if ep["ongoing"]
               else ep["recovery_date"].strftime("%d %b %Y"))
        dd_rows.append(
            f'<tr><td class="num">{k}</td>'
            f'<td>{ep["peak_date"].strftime("%d %b %Y")}</td>'
            f'<td class="num">{money(ep["peak_eq"])}</td>'
            f'<td>{ep["trough_date"].strftime("%d %b %Y")}</td>'
            f'<td class="num neg">{money(ep["max"])}</td>'
            f'<td class="num">{ep["pct"]:.1f}%</td>'
            f'<td>{rec}</td>'
            f'<td class="num">{ep["trades"]}</td>'
            f'<td class="num">{ep["days"]}</td></tr>')
    dd_table = (
        '<table class="grid"><thead><tr><th class="num">#</th><th>PEAK DATE</th>'
        '<th class="num">PEAK EQUITY</th><th>TROUGH DATE</th><th class="num">DEPTH</th>'
        '<th class="num">% OF PEAK</th><th>RECOVERY</th><th class="num">TRADES</th>'
        '<th class="num">DAYS</th></tr></thead><tbody>'
        + "".join(dd_rows) + '</tbody></table>')

    tr_rows = []
    for i, r in enumerate(df.itertuples(index=False), 1):
        peak = getattr(r, "peak", None)
        worst = getattr(r, "worst", None)
        gb = getattr(r, "giveback", None)
        pt = getattr(r, "peak_time", None)
        peak_time = "-" if pt is None or pd.isna(pt) else pt.strftime("%H:%M")
        if gb is None or pd.isna(gb):
            gb_cell = '<td class="num dim">-</td>'
        else:
            gb_cell = (f'<td class="num {"neg" if gb > 0 else "zero"}">'
                       f'{money(gb) if gb > 0 else "-"}</td>')
        tr_rows.append(
            f'<tr><td class="num">{i}</td>'
            f'<td>{r.entry.strftime("%d %b %Y %H:%M")}</td>'
            f'<td>{esc(r.sym)}</td>'
            f'<td>{r.exit.strftime("%d %b %Y %H:%M")}</td>'
            f'<td>{esc(r.status)}</td>'
            f'<td class="num {cls(r.gross)}">{money(r.gross)}</td>'
            f'<td class="num"><span class="peak">{num_val(peak)}</span></td>'
            f'<td class="num dim">{peak_time}</td>'
            f'<td class="num {"" if worst is None or pd.isna(worst) else cls(worst)}">'
            f'{num_val(worst)}</td>'
            + gb_cell +
            f'<td class="num {cls(r.net)}">{money(r.net)}</td>'
            f'<td class="num {cls(r.cum_net)}">{money(r.cum_net)}</td></tr>')
    tr_table = (
        '<table class="grid"><thead><tr><th class="num">#</th><th>ENTRY</th>'
        '<th>SYMBOL</th><th>EXIT</th><th>STATUS</th><th class="num">P&L (file)</th>'
        '<th class="num">PEAK +</th><th class="num">AT</th><th class="num">WORST</th>'
        '<th class="num">GIVEN BACK</th><th class="num">NET</th>'
        '<th class="num">RUNNING NET</th></tr></thead><tbody>'
        + "".join(tr_rows) + '</tbody></table>')

    exc_note = ""
    if exc:
        exc_note = (
            f" Give-back uses raw 1-minute candles: entry = close at Entry Time, "
            f"qty = int({money(capital)} / entry), peak = candle low, worst = candle high. "
            f"The 'Highest touched' per day is the peak of the combined intraday P&L curve "
            f"(open trades at their candle low, closed trades at their realised value); it is a "
            f"best-case figure.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest Report - {esc(src)}</title>
<style>
:root {{
  --bg:#0d1119; --panel:#151b26; --line:#242c3d; --txt:#e6ecf7;
  --dim:#8b98b0; --pos:#33d69f; --neg:#ff5c72; --acc:#5aa9ff;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--txt);
  font-family:'Segoe UI',system-ui,-apple-system,sans-serif; font-size:14px; }}
.wrap {{ max-width:1280px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:22px; margin:0 0 4px; letter-spacing:.5px; }}
h1 span {{ color:var(--acc); }}
.sub {{ color:var(--dim); font-size:12.5px; margin-bottom:22px; }}
h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:1.4px; color:var(--dim);
  margin:34px 0 12px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
.kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; }}
.kpi-l {{ font-size:10.5px; letter-spacing:1.2px; color:var(--dim); }}
.kpi-v {{ font-size:21px; font-weight:600; margin:7px 0 4px;
  font-family:Consolas,'JetBrains Mono',monospace; }}
.kpi-s {{ font-size:11px; color:var(--dim); }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:8px; overflow-x:auto; }}
.chart {{ width:100%; height:340px; display:block; }}
.ax {{ fill:var(--dim); font-size:11px; font-family:Consolas,monospace; }}
table.grid {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
table.grid th {{ text-align:left; color:var(--dim); font-weight:600; font-size:10.5px;
  letter-spacing:.9px; padding:9px 10px; border-bottom:1px solid var(--line);
  position:sticky; top:0; background:var(--panel); }}
table.grid td {{ padding:8px 10px; border-bottom:1px solid #1b2231; white-space:nowrap; }}
table.grid tbody tr:hover {{ background:#1a2130; }}
.num {{ text-align:right; font-family:Consolas,'JetBrains Mono',monospace; }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .zero,.neutral {{ color:var(--txt); }}
.dim {{ color:var(--dim); }}
.bar-wrap {{ position:relative; display:block; min-width:120px; }}
.bar {{ position:absolute; right:0; top:0; height:100%; opacity:.16; border-radius:3px; }}
.bar.pos {{ background:var(--pos); }} .bar.neg {{ background:var(--neg); }}
.bar-val {{ position:relative; }}
.peak {{ color:#ffd479; }}
.ongoing {{ color:var(--neg); font-weight:600; }}
.legend {{ color:var(--dim); font-size:11.5px; margin:8px 2px 0; }}
.legend b {{ color:var(--txt); font-weight:600; }}
.trades {{ max-height:680px; overflow:auto; }}
footer {{ margin-top:34px; color:var(--dim); font-size:11.5px; line-height:1.7;
  border-top:1px solid var(--line); padding-top:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>BACKTEST <span>REPORT</span></h1>
  <div class="sub">Source: {esc(src)} &nbsp;&middot;&nbsp; Generated {esc(gen)}
    &nbsp;&middot;&nbsp; Period {ov["start"].strftime("%d %b %Y")} - {ov["end"].strftime("%d %b %Y")}</div>

  <h2>Overview</h2>
  <div class="kpis">{cards_html}</div>

  <h2>Equity Curve (net)</h2>
  <div class="panel">{chart}</div>
  <div class="legend"><b>Solid</b> = net equity &nbsp; <b>Dashed</b> = running peak
    &nbsp; <b>Shaded</b> = drawdown episodes &nbsp; <b>Dots</b> = troughs</div>

  <h2>Daily &mdash; highest profit touched</h2>
  <div class="panel">{daily}</div>

  <h2>Month-wise</h2>
  <div class="panel">{months}</div>

  <h2>Week-wise (net)</h2>
  <div class="panel">{weeks}</div>

  <h2>Drawdowns &mdash; {len(res["episodes"])} episodes</h2>
  <div class="panel">{dd_table}</div>

  <h2>Trades &mdash; {ov["n"]}</h2>
  <div class="panel trades">{tr_table}</div>

  <footer>
    Cost model: flat <b>{money(tax)}</b> deducted per trade ({ov["n"]} trades =
    <b>{money(ov["tax"])}</b> total). Trades are ordered by entry time; the equity
    curve starts at 0 before the first trade.<br>
    Gross {money(ov["gross"])} &minus; cost {money(ov["tax"])} =
    <b>net {money(ov["net"])}</b>. Max drawdown: gross {money(ov["max_dd_gross"])},
    net <b>{money(ov["max_dd_net"])}</b> ({ov["max_dd_net_pct"]:.1f}% of peak).{exc_note}
  </footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Generate an HTML backtest report.")
    ap.add_argument("xlsx", nargs="?", help="backtest_*.xlsx (default: newest in results\\)")
    ap.add_argument("--tax", type=float, default=DEFAULT_TAX,
                    help=f"cost per trade (default {DEFAULT_TAX})")
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL,
                    help=f"capital per trade used for qty (default {DEFAULT_CAPITAL})")
    ap.add_argument("--no-candles", action="store_true",
                    help="skip the give-back / daily-touched analysis")
    ap.add_argument("--out", help="output HTML path (default: results\\report_<ts>.html)")
    ap.add_argument("--excel", help="also write the analysis to this .xlsx")
    args = ap.parse_args()

    path = args.xlsx or find_default_input()
    df = load_trades(path, args.tax)
    res, df = analyse(df, args.tax, args.capital, with_candles=not args.no_candles)
    res["src"] = path

    if args.out:
        out = args.out
    else:
        os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(cfg.RESULTS_DIR, f"report_{ts}.html")

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_html(path, df, res, args.tax, args.capital))

    if args.excel:
        write_excel(args.excel, df, res, args.tax, args.capital)

    ov = res["overview"]
    print(f"Trades            {ov['n']}")
    print(f"Gross P&L         {money(ov['gross'])}")
    print(f"Cost ({money(args.tax)}/trade)  {money(ov['tax'])}")
    print(f"NET P&L           {money(ov['net'])}")
    print(f"Win rate          {ov['net_wr']:.1f}% net / {ov['wr']:.1f}% gross")
    print(f"Max drawdown      {money(ov['max_dd_net'])} net ({ov['max_dd_net_pct']:.1f}%)"
          f" / {money(ov['max_dd_gross'])} gross")
    print(f"Drawdown episodes {len(res['episodes'])}")
    if res.get("excursion"):
        e = res["excursion"]
        print(f"Profit given back {money(e['total_giveback'])}")
        print(f"Reversals         {e['reversals']}")
        print(f"Worst give-back   {money(e['worst_giveback'])}")
        print(f"Daily rows        {len(res['days'])}")
    print(f"Report written    {out}")
    if args.excel:
        print(f"Excel written     {args.excel}")


if __name__ == "__main__":
    main()
