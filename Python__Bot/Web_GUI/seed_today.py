"""Write seed_today.txt: entries the bot missed today, recorded at START.

Usage:
    python seed_today.py HCLTECH=1448 TCS=2583 WIPRO=193.42
    python seed_today.py --show
    python seed_today.py --clear

On START the bot reads seed_today.txt (VIRTUAL mode only) and opens one short
per line at the given price, so the day's P&L and trade log stay complete.
Every line is validated against the symbol master before the file is written.
No broker orders are placed.
"""
import os
import sys
from datetime import datetime

import config as cfg
from order_builder import OrderBuilder


def _parse(args):
    pairs = []
    for item in args:
        sym, sep, px = item.partition("=")
        sym = sym.strip().upper()
        if not sep or not sym:
            raise SystemExit(f"bad entry {item!r} - expected SYMBOL=PRICE")
        try:
            price = float(px)
        except ValueError:
            raise SystemExit(f"bad price in {item!r}")
        if price <= 0:
            raise SystemExit(f"price must be > 0 in {item!r}")
        pairs.append((sym, price))
    return pairs


def main():
    args = sys.argv[1:]
    path = cfg.SEED_FILE
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if args[0] == "--show":
        if os.path.exists(path):
            print(open(path, encoding="utf-8").read().rstrip())
        else:
            print("(no seed file)")
        return 0
    if args[0] == "--clear":
        today_marker = f"{path}.done_{datetime.now():%Y-%m-%d}"
        for p in (path, today_marker):
            if os.path.exists(p):
                os.remove(p)
        print("seed cleared")
        return 0

    pairs = _parse(args)
    builder = OrderBuilder()
    lines, problems = [], []
    for sym, price in pairs:
        row, error = builder.build_order(
            sym, trading_cap=cfg.DEFAULT_TRADING_CAP, ltp=price,
            action="SELL", remarks="Seeded_Entry",
        )
        if row is None:
            problems.append(f"{sym}: {error['message']}")
            continue
        print(
            f"{sym:<10} -> {row['tradingsymbol']:<12} {row['lots']:>6} x "
            f"{row['lot_size']:<4} = {row['quantity']:>7} shares | "
            f"entry {price:,.2f} | notional {row['notional']:,.0f}"
        )
        lines.append(f"{sym}={price:g}")

    if problems:
        for p in problems:
            print(f"NOT ADDED  {p}", file=sys.stderr)
        print("seed file NOT written - fix the lines above and retry",
              file=sys.stderr)
        return 1

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Missed entries for TODAY, recorded as open VIRTUAL "
                 "positions at START.\n")
        fh.write("# One SYMBOL=PRICE per line. No broker orders are placed.\n")
        fh.write("\n".join(lines) + "\n")

    today_marker = f"{path}.done_{datetime.now():%Y-%m-%d}"
    if os.path.exists(today_marker):
        os.remove(today_marker)

    print(f"\nWrote {len(lines)} entr(ies) to {path}")
    print("Start the bot - it seeds them once, then SL/TP and EOD apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
