"""
Rebuild the NSE equity master used for symbol resolution.

  Seed   : official NSE equity list (archives.nseindia.com) - symbol, lot,
           company name, ISIN
  Tokens : Shoonya searchscrip, EXACT match only - token, trading lot, tick
  Output : nse_equity_master.xlsx  (sheets: EQ, UNMATCHED, OTHER)

The old master was a 500-symbol file dated 06-10-2026 and already contained
dead tokens (GSPL, HFCL, JBCHEPHARM all quote with lp=None). This rebuilds
the list from the official NSE source and verifies every token.

Usage:
    python tools/build_symbol_master.py                 # full build
    python tools/build_symbol_master.py --limit 20     # quick smoke test
    python tools/build_symbol_master.py --check-ltp     # also live-price every row
"""
import argparse
import csv
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

import config as cfg
from scrip_resolver import ScripResolver, normalize

NSE_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_NAME = "master_build_cache.json"
_print_lock = threading.Lock()


class RateLimiter:
    """Shoonya market data: 10 req/sec, 200 req/min. We cap at ~187/min."""

    def __init__(self, per_minute=187):
        self.min_interval = 60.0 / per_minute
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.time()
            slot = max(now, self._next)
            self._next = slot + self.min_interval
        delay = slot - time.time()
        if delay > 0:
            time.sleep(delay)


_limiter = RateLimiter()


def say(msg):
    with _print_lock:
        print(msg, flush=True)


def fetch_nse_list():
    """Official NSE equity list. Returns (eq_rows, other_rows)."""
    r = requests.get(NSE_LIST_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8", "ignore"))))
    rows = [{k.strip(): (v or "").strip() for k, v in row.items()} for row in rows]
    eq = [r for r in rows if r.get("SERIES", "").upper() == "EQ"]
    other = [r for r in rows if r.get("SERIES", "").upper() != "EQ"]
    return eq, other


def load_cache(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(path, cache):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    os.replace(tmp, path)


def build_session():
    """Log into Shoonya so searchscrip works. Fast API login first."""
    from bot_core import ShoonyaApiPy, TradingBot

    bot = TradingBot()
    bot.load_excel(cfg.LEGACY_EXCEL_FILE)
    cred = bot._load_cred() or {}
    uid = str(cred.get("user", "")).strip()
    pwd = str(cred.get("pwd", ""))

    token = str(cred.get("jkey", "")).strip()
    if not token:
        token = bot._auto_login(cred, uid, pwd) or ""
    if not token:
        say("API login unavailable, using browser login...")
        ok, msg, token = bot.fetch_jkey()
        if not ok:
            raise SystemExit(f"Login failed: {msg}")
    api = ShoonyaApiPy()
    api.set_session(uid, pwd, token)
    say(f"Session ready (user={uid})")
    return api


def search_one(api, symbol, resolver):
    """Exact-match search for one symbol. Returns a record dict."""
    _limiter.wait()
    try:
        r = api.searchscrip("NSE", symbol)
    except Exception as e:
        return {"symbol": symbol, "status": "error", "error": str(e)}
    values = (r or {}).get("values") or []
    hit = resolver.exact_match(values, symbol, "NSE")
    if not hit:
        return {
            "symbol": symbol,
            "status": "no_exact",
            "candidates": [f"{v.get('tsym')}/{v.get('instname')}" for v in values[:4]],
        }
    return {
        "symbol": symbol,
        "status": "ok",
        "token": str(hit.get("token", "")).strip(),
        "tsym": str(hit.get("tsym", "")).strip().upper(),
        "exchange": str(hit.get("exch", "NSE")).strip().upper(),
        "ls": int(float(hit.get("ls", 1) or 1)),
        "tick": hit.get("ti"),
        "cname": str(hit.get("cname", "")).strip(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=cfg.MASTER_FILE)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="only build N symbols")
    ap.add_argument("--check-ltp", action="store_true", help="live-price every symbol")
    ap.add_argument("--skip-cache", action="store_true")
    args = ap.parse_args()

    cache_path = os.path.join(os.path.dirname(args.out), CACHE_NAME)
    report_path = os.path.join(os.path.dirname(os.path.dirname(args.out)), "out",
                               "master_build_report.txt")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    say("Fetching official NSE equity list...")
    eq_rows, other_rows = fetch_nse_list()
    say(f"  {len(eq_rows)} EQ symbols, {len(other_rows)} non-EQ series")

    symbols = [r["SYMBOL"] for r in eq_rows if r.get("SYMBOL")]
    if args.limit:
        symbols = symbols[: args.limit]

    cache = {} if args.skip_cache else load_cache(cache_path)
    todo = [s for s in symbols if s not in cache]
    say(f"  {len(symbols)} to build, {len(cache)} cached, {len(todo)} to fetch")

    api = build_session()
    resolver = ScripResolver(api=api)

    started = time.time()
    done = 0
    if todo:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(search_one, api, s, resolver): s for s in todo}
            for fut in as_completed(futures):
                rec = fut.result()
                cache[rec["symbol"]] = rec
                done += 1
                if done % 50 == 0:
                    rate = done / max(time.time() - started, 0.001)
                    say(f"  {done}/{len(todo)} fetched ({rate:.1f}/s) eta="
                        f"{int((len(todo) - done) / max(rate, 0.01) / 60)} min")
                    save_cache(cache_path, cache)
    save_cache(cache_path, cache)
    say(f"Search done in {time.time() - started:.0f}s")

    # ── assemble the master ──────────────────────────────────
    by_symbol = {r["SYMBOL"]: r for r in eq_rows}
    rows, unmatched = [], []
    lot_mismatch = []
    for sym in symbols:
        rec = cache.get(sym)
        if not rec or rec.get("status") != "ok":
            unmatched.append({
                "Symbol": sym,
                "Company": by_symbol.get(sym, {}).get("NAME OF COMPANY", ""),
                "Status": (rec or {}).get("status", "missing"),
                "Candidates": ", ".join((rec or {}).get("candidates", []) or []),
            })
            continue
        src = by_symbol.get(sym, {})
        nse_lot = src.get("MARKET LOT", "")
        try:
            nse_lot_i = int(float(nse_lot))
        except (TypeError, ValueError):
            nse_lot_i = 0
        if nse_lot_i and nse_lot_i != rec["ls"]:
            lot_mismatch.append((sym, nse_lot_i, rec["ls"]))
        rows.append({
            "Exchange": rec["exchange"],
            "Token": rec["token"],
            "LotSize": rec["ls"],
            "Symbol": sym,
            "TradingSymbol": rec["tsym"],
            "Instrument": "EQ",
            "TickSize": rec.get("tick"),
            "Company": rec.get("cname") or src.get("NAME OF COMPANY", ""),
            "NSELot": nse_lot_i or None,
        })

    master = pd.DataFrame(rows)
    if not master.empty:
        master = master.sort_values("Symbol").reset_index(drop=True)

    # ── live price verification ─────────────────────────────
    dead = []
    if args.check_ltp and not master.empty:
        say("Live-checking every token (lp must be a number > 0)...")
        import contextlib
        import NorenRestApiPy.NorenApi as na
        na.reportmsg = lambda *a, **k: None
        sink = io.StringIO()
        for i, row in master.iterrows():
            with contextlib.redirect_stdout(sink):
                _limiter.wait()
                try:
                    q = api.get_quotes(exchange=row["Exchange"], token=str(row["Token"]))
                except Exception as e:
                    dead.append((row["Symbol"], str(row["Token"]), f"error {e}"))
                    continue
            lp = (q or {}).get("lp")
            try:
                lp = float(lp)
            except (TypeError, ValueError):
                lp = None
            if not q or q.get("stat") != "Ok" or not lp or lp <= 0:
                dead.append((row["Symbol"], str(row["Token"]),
                             f"stat={(q or {}).get('stat')} lp={lp}"))
            if (i + 1) % 250 == 0:
                say(f"  priced {i + 1}/{len(master)}  dead={len(dead)}")

    with pd.ExcelWriter(args.out, engine="openpyxl") as xl:
        master.to_excel(xl, sheet_name="EQ", index=False)
        pd.DataFrame(unmatched).to_excel(xl, sheet_name="UNMATCHED", index=False)
        other_df = pd.DataFrame([{
            "Symbol": r.get("SYMBOL", ""),
            "Company": r.get("NAME OF COMPANY", ""),
            "Series": r.get("SERIES", ""),
            "MarketLot": r.get("MARKET LOT", ""),
        } for r in other_rows])
        other_df.to_excel(xl, sheet_name="OTHER", index=False)

    # ── report ──────────────────────────────────────────────
    lines = []
    lines.append("NSE EQUITY MASTER BUILD REPORT")
    lines.append("=" * 60)
    lines.append(f"Official NSE EQ symbols : {len(eq_rows)}")
    lines.append(f"Master rows written     : {len(master)}")
    lines.append(f"Unmatched (no exact)    : {len(unmatched)}")
    lines.append(f"Lot size mismatches     : {len(lot_mismatch)}")
    lines.append(f"Dead tokens (no LTP)    : {len(dead)}")
    lines.append(f"Output                  : {args.out}")
    lines.append("")
    if unmatched:
        lines.append("UNMATCHED SYMBOLS (broker has no exact equity match)")
        lines.append("-" * 60)
        for u in unmatched[:80]:
            lines.append(f"  {u['Symbol']:14s} {u['Status']:10s} "
                         f"{u['Company'][:34]:34s} {u['Candidates']}")
    if lot_mismatch:
        lines.append("")
        lines.append("LOT SIZE MISMATCH (nse_lot vs broker_ls)")
        lines.append("-" * 60)
        for sym, nse, br in lot_mismatch[:40]:
            lines.append(f"  {sym:14s} nse={nse} broker={br}")
    if dead:
        lines.append("")
        lines.append("DEAD TOKENS (stat Ok but no usable LTP)")
        lines.append("-" * 60)
        for sym, tok, why in dead[:80]:
            lines.append(f"  {sym:14s} token={tok:>8s} {why}")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    say("\n".join(lines[:12]))
    say(f"Full report: {report_path}")


if __name__ == "__main__":
    main()
