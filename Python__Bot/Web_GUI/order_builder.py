"""
Array A  ->  Array B : the one converter.

Array A (source of truth)
    nse_equity_master.xlsx - every NSE equity symbol with its official token,
    exchange, market lot and tick size. Rebuilt from the official NSE list,
    exact-token matched against the broker, live-priced:
    2353 rows, 0 dead, 0 fabricated.

Array B (broker format)
    The dict Shoonya's place_order() expects:
        token, tradingsymbol, exchange, quantity (SHARES), price_type,
        product_type, retention, discloseqty, remarks

Two outcomes only - there is no third:
        row, None   ->  ready to send
        None, why   ->  DO NOT TRADE, and 'why' says what stopped it

Nothing here is fuzzy. A symbol that is not in Array A (after the alias map)
is refused, never turned into "the closest thing". That single rule is what
stops HDFCL from becoming HDFCLOWVOL.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg
from scrip_resolver import AliasMap, ScripResolver, normalize

DEFAULT_OUT = os.path.join(os.path.dirname(cfg.ROOT), "out", "order_rows.jsonl")


def _as_int(value, default=0):
    """int() that survives NaN/None/blank cells in the master sheet."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return int(f)


def load_array_a(path=None):
    """Read Array A (the master) into {SYMBOL: entry}. Equity rows only."""
    import pandas as pd

    path = path or cfg.MASTER_FILE
    df = pd.read_excel(path)
    out = {}
    for _, row in df.iterrows():
        instrument = str(row.get("Instrument", "EQ")).strip().upper()
        if instrument and instrument != "EQ":
            continue
        tsym = str(row.get("TradingSymbol", "")).strip().upper()
        sym = normalize(row.get("Symbol") or tsym)
        if not sym or not tsym:
            continue
        out[sym] = {
            "token": str(row.get("Token", "")).strip(),
            "tsym": tsym,
            "exchange": str(row.get("Exchange", "NSE")).strip().upper() or "NSE",
            "broker_ls": _as_int(row.get("LotSize", 1), 1),
            "nse_lot": _as_int(row.get("NSELot", 0), 0),
            "tick": row.get("TickSize"),
            "company": str(row.get("Company", "")).strip(),
            "source": os.path.basename(path),
        }
    return out


def effective_lot(entry):
    """The exchange's market lot wins over the broker's cached 'ls'.

    Shoonya's ls is stale for a few symbols (MODTHREAD 1 vs 50, TECILCHEM 1 vs
    50, PRUDMOULI 1 vs 100). The exchange rejects any quantity that is not a
    multiple of the real market lot, so the official lot is what we size with.
    """
    nse = _as_int(entry.get("nse_lot"), 0)
    broker = _as_int(entry.get("broker_ls"), 1)
    if nse > 0:
        return nse
    return broker if broker > 0 else 1


class OrderBuilder:
    """Turns a scanner symbol into a complete broker order row."""

    def __init__(self, master_path=None, api=None, alias_file=None):
        self.api = api
        self.aliases = AliasMap(alias_file)
        self.master_path = master_path or cfg.MASTER_FILE
        self.array_a = load_array_a(self.master_path)
        # The resolver is used ONLY for the broker fallback. It is loaded with
        # this master alone, so the old 503-row file can never leak back in.
        self._resolver = ScripResolver(api=api, alias_file=alias_file)
        self._resolver.load_master([self.master_path])

    def set_api(self, api):
        """Point the builder (and its resolver) at the live broker session."""
        self.api = api
        self._resolver.set_api(api)

    # ── Array A -> instrument ────────────────────────────────

    def resolve(self, symbol, exchange="NSE"):
        """Returns (entry, reason). entry is None when it cannot be converted."""
        requested = str(symbol or "").strip()
        if not requested:
            return None, "empty symbol"

        # A real NSE symbol always trades ITSELF. The alias table is only
        # consulted for names that do not exist on the exchange, so a stale
        # alias can never redirect a live company to another one.
        entry = self.array_a.get(normalize(requested))
        if entry:
            entry = dict(entry)
            entry["alias"] = None
            entry["requested"] = requested
            return entry, ""

        target, alias_used = self.aliases.resolve(requested)
        if not target:
            return None, "empty symbol"

        entry = self.array_a.get(target)
        if entry:
            entry = dict(entry)
            entry["alias"] = alias_used
            entry["requested"] = requested
            return entry, ""

        if self.api is None:
            return None, (f"{target} is not in the master and there is no "
                          "broker session to ask")

        scrip, info = self._resolver.resolve(target, exchange)
        if not scrip:
            cands = ", ".join(info.get("candidates") or [])
            detail = info.get("reason") or "no exact match at broker"
            tail = f" (broker returned: {cands})" if cands else ""
            return None, f"{target} not found: {detail}{tail}"

        return {
            "token": scrip["token"],
            "tsym": scrip["tsym"],
            "exchange": scrip.get("exchange", exchange),
            "broker_ls": _as_int(scrip.get("ls", 1), 1),
            "nse_lot": 0,
            "tick": scrip.get("tick"),
            "company": "",
            "alias": alias_used,
            "requested": requested,
            "source": "broker",
        }, ""

    def live_ltp(self, entry):
        """Returns (price, reason)."""
        if self.api is None:
            return None, "no broker session - cannot read LTP"
        try:
            q = self.api.get_quotes(exchange=entry["exchange"], token=entry["token"])
        except Exception as e:
            return None, f"quote error: {e}"
        if not q or q.get("stat") != "Ok":
            return None, f"no quote (stat={(q or {}).get('stat')})"
        try:
            lp = float(q.get("lp") or 0)
        except (TypeError, ValueError):
            lp = 0.0
        if lp <= 0:
            return None, "no LTP for this token"
        return lp, ""

    # ── Array B ──────────────────────────────────────────────

    def build_order(self, symbol, exchange="NSE", trading_cap=None,
                    ltp=None, trigger_price=None, action="SELL",
                    product_type="I", price_type="MKT", retention="DAY",
                    discloseqty=0, remarks="Webhook_Sell"):
        """Returns (row, error).

        row  - the complete broker order row (Array B) on success
        error - None on success, else {"code": ..., "message": ...}:
            not_found        - the symbol is in neither the master nor the broker
            wrong_instrument - it resolved to a different company
            no_ltp           - the token has no live price
            price_mismatch   - the live price is nowhere near the trigger price
            zero_lots        - one lot costs more than the whole cap
            empty_symbol     - nothing to convert
        """
        cap = float(cfg.DEFAULT_TRADING_CAP if trading_cap is None else trading_cap)

        entry, reason = self.resolve(symbol, exchange)
        if entry is None:
            code = "empty_symbol" if reason == "empty symbol" else "not_found"
            return None, {"code": code, "message": reason}

        # The instrument must BE the symbol we were asked for (after the
        # alias). A rename is fine; a different company is not.
        wanted, _alias = self.aliases.resolve(symbol)
        if normalize(entry["tsym"]) != wanted:
            return None, {
                "code": "wrong_instrument",
                "message": (f"resolved to {entry['tsym']} but {wanted} was "
                            "requested - refusing to trade a different instrument"),
            }

        price = ltp
        if price is None:
            price, err = self.live_ltp(entry)
            if price is None:
                return None, {"code": "no_ltp", "message": err}
        price = float(price)
        if price <= 0:
            return None, {
                "code": "no_ltp",
                "message": f"invalid LTP {price} for {entry['tsym']}",
            }

        # A price nowhere near the scanner's trigger price means the wrong
        # instrument or a dead token. Checked before sizing, so the real
        # reason is reported even when the cap is too small.
        if trigger_price:
            try:
                tp = float(trigger_price)
            except (TypeError, ValueError):
                tp = 0.0
            if tp > 0:
                drift = abs(price - tp) / tp
                if drift > cfg.LTP_SANITY_PCT:
                    return None, {
                        "code": "price_mismatch",
                        "message": (f"LTP {price:.2f} is {drift * 100:.0f}% away "
                                    f"from trigger price {tp:.2f} - refusing"),
                    }

        lot = effective_lot(entry)
        per_lot = price * lot
        lots = int(cap / per_lot) if per_lot > 0 else 0
        # Guard against float dust: an order must never cost more than the cap.
        while lots > 0 and lots * per_lot > cap + 0.01:
            lots -= 1
        while (lots + 1) * per_lot <= cap + 0.01:
            lots += 1
        if lots < 1:
            return None, {
                "code": "zero_lots",
                "message": (f"0 lots: one lot costs {per_lot:,.0f} but the cap "
                            f"is {cap:,.0f}"),
            }

        quantity = lots * lot          # SHARES - the broker counts shares
        row = {
            "token": entry["token"],
            "tradingsymbol": entry["tsym"],
            "exchange": entry["exchange"],
            "quantity": quantity,
            "lots": lots,
            "lot_size": lot,
            "price_type": price_type,
            "product_type": product_type,
            "retention": retention,
            "discloseqty": discloseqty,
            "remarks": remarks,
            "side": action,
            "ltp": round(price, 4),
            "notional": round(price * quantity, 2),
            "source": entry.get("source", ""),
            "alias": entry.get("alias"),
        }
        return row, ""

    @staticmethod
    def to_place_order_kwargs(row):
        """The exact kwargs for ShoonyaApiPy.place_order()."""
        return {
            "buy_or_sell": row.get("side", "SELL"),
            "product_type": row["product_type"],
            "exchange": row["exchange"],
            "tradingsymbol": row["tradingsymbol"],
            "quantity": row["quantity"],
            "discloseqty": row["discloseqty"],
            "price_type": row["price_type"],
            "retention": row["retention"],
            "remarks": row["remarks"],
        }

    def static_row(self, sym, entry):
        """Array B without a price - the shape of the order, not its size."""
        return {
            "token": entry["token"],
            "tradingsymbol": entry["tsym"],
            "exchange": entry["exchange"],
            "quantity": None,
            "lots": None,
            "lot_size": effective_lot(entry),
            "price_type": "MKT",
            "product_type": "I",
            "retention": "DAY",
            "discloseqty": 0,
            "remarks": "Webhook_Sell",
            "side": "SELL",
            "ltp": None,
            "notional": None,
            "source": entry.get("source", ""),
            "alias": None,
        }

    # ── Array A -> Array B for the whole list ────────────────

    def convert_all(self, with_ltp=False, out_path=None, min_interval=0.35,
                    log=print, limit=0):
        """Convert every symbol in Array A. Writes Array B as JSONL.

        min_interval keeps us under the broker's rate limit (10 requests a
        second, 200 a minute) while we walk the whole list.
        """
        out_path = out_path or DEFAULT_OUT
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        symbols = sorted(self.array_a)
        if limit:
            symbols = symbols[:limit]
        written = 0
        failed = []
        started = time.time()
        next_slot = time.time()
        with open(out_path, "w", encoding="utf-8") as fh:
            for i, sym in enumerate(symbols, 1):
                if with_ltp:
                    # keep the broker happy
                    delay = next_slot - time.time()
                    if delay > 0:
                        time.sleep(delay)
                    next_slot = max(next_slot, time.time()) + min_interval

                    row, error = self.build_order(sym)
                    if row is None:
                        failed.append({"symbol": sym, "code": error["code"],
                                       "message": error["message"]})
                        log(f"  [{i}/{len(symbols)}] {sym:<14} FAILED "
                            f"[{error['code']}] {error['message']}")
                        continue
                else:
                    row = self.static_row(sym, self.array_a[sym])
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                written += 1
                if i % 50 == 0 or i == len(symbols):
                    log(f"  [{i}/{len(symbols)}] {written} converted, "
                        f"{len(failed)} failed, {time.time() - started:.0f}s")
        return written, failed, out_path


def verify(builder):
    """Static health check of Array A. No broker session needed."""
    rows = builder.array_a
    no_token = [s for s, e in rows.items() if not e["token"]]
    bad_tsym = [s for s, e in rows.items() if not e["tsym"].endswith("-EQ")]
    lot_diff = [
        (s, e["broker_ls"], e["nse_lot"])
        for s, e in sorted(rows.items())
        if e["nse_lot"] and e["broker_ls"] != e["nse_lot"]
    ]
    # An alias whose SOURCE is a real symbol would redirect a live company to
    # another one. The converter ignores such an alias, but it must be fixed.
    shadowing = [
        (a, t) for a, t in sorted(builder.aliases.map.items())
        if a in rows and normalize(t) != a
    ]
    dead_alias = [
        (a, t) for a, t in sorted(builder.aliases.map.items())
        if a not in rows and t not in rows
    ]
    print(f"Array A rows            : {len(rows)}")
    print(f"Rows without a token    : {len(no_token)}")
    print(f"Rows not ending -EQ     : {len(bad_tsym)}")
    print(f"Lot size disagreements  : {len(lot_diff)} "
          f"(broker ls vs official NSE lot)")
    for sym, bl, nl in lot_diff:
        print(f"   {sym:<14} broker ls={bl:<4} official lot={nl}  -> using {nl}")
    print(f"Aliases                 : {len(builder.aliases.map)}")
    print(f"Aliases shadowing a live symbol : {len(shadowing)}")
    for a, t in shadowing:
        print(f"   {a:<14} -> {t:<14} FIX THIS: {a} is a real symbol")
    print(f"Aliases pointing nowhere       : {len(dead_alias)}")
    for a, t in dead_alias:
        print(f"   {a:<14} -> {t:<14} neither side is in the master")
    return len(rows), lot_diff, shadowing


def main():
    ap = argparse.ArgumentParser(description="Array A -> Array B converter")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--cap", type=float, default=cfg.DEFAULT_TRADING_CAP)
    ap.add_argument("--ltp", type=float, default=None,
                    help="use this price instead of a live quote")
    ap.add_argument("--verify", action="store_true",
                    help="static health check of Array A")
    ap.add_argument("--all", action="store_true",
                    help="convert every symbol in Array A -> out/order_rows.jsonl")
    ap.add_argument("--live", action="store_true",
                    help="with --all, also fetch live LTPs (slow)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min-interval", type=float, default=0.35,
                    help="seconds between broker calls when walking the list")
    ap.add_argument("--limit", type=int, default=0,
                    help="only convert the first N symbols (smoke test)")
    args = ap.parse_args()

    api = None
    if args.symbols or args.live:
        from check_symbols import build_session
        api = build_session()

    builder = OrderBuilder(api=api)

    if args.verify:
        verify(builder)
        return

    if args.all:
        written, failed, path = builder.convert_all(
            with_ltp=args.live, out_path=args.out, min_interval=args.min_interval,
            limit=args.limit)
        print(f"Array B written: {written} rows -> {path}")
        if failed:
            print(f"Failed: {len(failed)}")
            for f in failed[:20]:
                print(f"   {f['symbol']:<14} [{f['code']}] {f['message']}")
        return

    if not args.symbols:
        ap.print_help()
        return

    for sym in args.symbols:
        row, error = builder.build_order(sym, trading_cap=args.cap, ltp=args.ltp)
        if row is None:
            print(f"{sym:<14} NOT TRADED  [{error['code']}] {error['message']}")
            continue
        print(f"{sym:<14} {row['tradingsymbol']:<16} token={row['token']:<8} "
              f"lot={row['lot_size']:<4} lots={row['lots']:<6} qty={row['quantity']:<8} "
              f"@ {row['ltp']:,.2f}  = {row['notional']:,.0f}")
        print("   place_order kwargs: " + json.dumps(
            builder.to_place_order_kwargs(row)))


if __name__ == "__main__":
    main()
