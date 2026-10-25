"""
One-by-one symbol + LTP checker (read-only, places no orders).

    python check_symbols.py INFY TCS HDFCL
    python check_symbols.py --file symbols.txt
    python check_symbols.py --file symbols.txt --price 1420,2529,1400
    python check_symbols.py --from-payload payloads/2026-10-21.jsonl
    python check_symbols.py --all          # every symbol in the master

Shows, for each symbol you asked for: what it actually resolved to, the
broker token, the lot size, the live LTP and a verdict.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg
from scrip_resolver import ScripResolver, normalize


def build_session():
    from bot_core import ShoonyaApiPy, TradingBot

    bot = TradingBot()
    cred = bot._load_cred() or {}
    uid = str(cred.get("user", "")).strip()
    pwd = str(cred.get("pwd", ""))
    token = str(cred.get("jkey", "")).strip()
    if not token:
        token = bot._auto_login(cred, uid, pwd) or ""
    if not token:
        ok, msg, token = bot.fetch_jkey()
        if not ok:
            raise SystemExit(f"Login failed: {msg}")
    api = ShoonyaApiPy()
    api.set_session(uid, pwd, token)
    return api


def read_symbols(args):
    symbols = []
    prices = []
    for s in args.symbols or []:
        symbols.append(s)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.replace(";", ",").split(",") if p.strip()]
                symbols.append(parts[0])
                if len(parts) > 1:
                    try:
                        prices.append(float(parts[1]))
                    except ValueError:
                        prices.append(None)
                else:
                    prices.append(None)
    if args.from_payload:
        with open(args.from_payload, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                data = rec.get("payload", rec)
                raw = str(data.get("stocks", ""))
                prc = str(data.get("trigger_prices", ""))
                p_list = [p.strip() for p in prc.split(",") if p.strip()]
                for i, s in enumerate(raw.split(",")):
                    s = s.strip()
                    if not s:
                        continue
                    symbols.append(s)
                    try:
                        prices.append(float(p_list[i]))
                    except (IndexError, ValueError):
                        prices.append(None)
    if args.price:
        for p in args.price.split(","):
            p = p.strip()
            if p:
                try:
                    prices.append(float(p))
                except ValueError:
                    prices.append(None)
    return symbols, prices


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--from-payload")
    ap.add_argument("--price", help="comma separated trigger prices")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    api = build_session()
    resolver = ScripResolver(api=api)
    master = resolver.load_master()

    symbols, prices = read_symbols(args)
    if args.all:
        symbols = sorted(resolver._master.keys())
        prices = [None] * len(symbols)
    if not symbols:
        raise SystemExit("No symbols given. Use INFY TCS HDFCL | --file | --from-payload | --all")

    print(f"Master loaded: {len(master)} symbols from {resolver.master_files}\n")
    header = f"{'REQUESTED':<14} {'RESOLVED':<16} {'TOKEN':>8} {'LOT':>5} {'LTP':>12}  VERDICT"
    print(header)
    print("-" * len(header))

    bad = 0
    for i, sym in enumerate(symbols):
        trigger = prices[i] if i < len(prices) else None
        scrip, info = resolver.resolve(sym)
        if not scrip:
            bad += 1
            extra = f" | candidates: {', '.join(info.get('candidates') or [])}" \
                if info.get("candidates") else f" | {info.get('reason', '')}"
            alias = f" [alias {info['alias']}->{info['normalized']}]" if info.get("alias") else ""
            print(f"{sym:<14} {'-':<16} {'-':>8} {'-':>5} {'-':>12}  NOT FOUND{alias}{extra}")
            continue

        try:
            q = api.get_quotes(exchange=scrip["exchange"], token=scrip["token"])
        except Exception as e:
            bad += 1
            print(f"{sym:<14} {scrip['tsym']:<16} {scrip['token']:>8} {scrip['ls']:>5} "
                  f"{'-':>12}  QUOTE ERROR {e}")
            continue

        lp = (q or {}).get("lp")
        try:
            lp = float(lp)
        except (TypeError, ValueError):
            lp = None

        if not q or q.get("stat") != "Ok" or not lp or lp <= 0:
            bad += 1
            print(f"{sym:<14} {scrip['tsym']:<16} {scrip['token']:>8} {scrip['ls']:>5} "
                  f"{'-':>12}  NO LTP (stat={(q or {}).get('stat')}, lp={lp})")
            continue

        resolved_sym = normalize(scrip["tsym"])
        wanted = info["normalized"]
        if resolved_sym != wanted:
            bad += 1
            print(f"{sym:<14} {scrip['tsym']:<16} {scrip['token']:>8} {scrip['ls']:>5} "
                  f"{lp:>12.2f}  WRONG SYMBOL (wanted {wanted})")
            continue

        verdict = "OK"
        if trigger:
            drift = abs(lp - trigger) / trigger if trigger else 0
            if drift > cfg.LTP_SANITY_PCT:
                bad += 1
                verdict = f"PRICE MISMATCH vs trigger {trigger} ({drift * 100:.0f}% off)"

        alias = f" [alias {info['alias']}]" if info.get("alias") else ""
        print(f"{sym:<14} {scrip['tsym']:<16} {scrip['token']:>8} {scrip['ls']:>5} "
              f"{lp:>12.2f}  {verdict} [{info['source']}]{alias}")

    print("-" * len(header))
    print(f"{len(symbols)} checked, {bad} problem(s)")


if __name__ == "__main__":
    main()
