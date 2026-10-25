"""
Symbol resolution for the Shoonya bot.

The broker's searchscrip() is a FUZZY search: it returns every instrument
whose text loosely matches, in no particular order. The old code took
values[0] blindly, so "HDFCL" resolved to HDFCLOWVOL-EQ (INR 19) instead of
HDFCLIFE-EQ (INR 1400) - a trade in the wrong company. This module only ever
accepts an EXACT symbol match, and never falls back to "the closest thing".

Resolution order:
  1. alias map      - scanner shorthand -> real NSE symbol (HDFCL -> HDFCLIFE)
  2. local master   - full NSE equity master (token + lot size)
  3. broker search  - searchscrip, exact match only, NSE + EQ segment
"""
import os
import threading

import pandas as pd

from config import ALIAS_FILE, LEGACY_EXCEL_FILE, MASTER_FILE


def normalize(symbol):
    """'hdfcl-eq' -> 'HDFCL'. Strips exchange/segment suffixes."""
    s = str(symbol or "").strip().upper()
    for suffix in ("-EQ", "-BE", "-D1", "-N3", "-CE"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s.replace("-", "").replace(" ", "").replace("_", "")


def is_equity(entry):
    """True when the broker entry is a plain equity (not a future/option)."""
    return str(entry.get("instname", "")).strip().upper() == "EQ"


class AliasMap:
    """Plain-text alias table: one "ALIAS = REAL" pair per line."""

    def __init__(self, path=None):
        self.path = path or ALIAS_FILE
        self.map = {}
        self.load()

    def load(self):
        self.map = {}
        if not self.path or not os.path.exists(self.path):
            return self.map
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if not line or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = normalize(key)
                    value = normalize(value)
                    if key and value:
                        self.map[key] = value
        except Exception:
            self.map = {}
        return self.map

    def resolve(self, symbol):
        """Returns (resolved_symbol, alias_used). Alias chains are followed."""
        current = normalize(symbol)
        alias_used = None
        seen = set()
        while current in self.map and current not in seen and len(seen) < 8:
            seen.add(current)
            if alias_used is None:
                alias_used = current
            current = self.map[current]
        return current, alias_used


class ScripResolver:
    """Resolves a scanner symbol to a tradable scrip. Thread safe."""

    def __init__(self, api=None, alias_file=None):
        self.api = api
        self.aliases = AliasMap(alias_file)
        self._master = {}
        self._lock = threading.Lock()
        self._search_cache = {}
        self.master_files = []

    # ── master ───────────────────────────────────────────────

    def load_master(self, paths=None):
        """Load the equity master.

        The first file that exists wins on its own - the rebuilt master is
        complete (2353 of 2354 NSE equities) and verified live, so merging the
        old 500-symbol file back in would only reintroduce dead tokens like
        GSPL, HFCL and JBCHEPHARM.
        """
        paths = paths or [MASTER_FILE, LEGACY_EXCEL_FILE]
        master = {}
        loaded = []
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            try:
                df = pd.read_excel(path)
            except Exception:
                continue
            if "TradingSymbol" not in df.columns:
                continue
            for _, row in df.iterrows():
                tsym = str(row.get("TradingSymbol", "")).strip().upper()
                if not tsym:
                    continue
                instrument = str(row.get("Instrument", "EQ")).strip().upper()
                if instrument and instrument != "EQ":
                    continue
                sym = normalize(row.get("Symbol") or tsym)
                if not sym:
                    continue
                if sym in master:
                    continue
                master[sym] = {
                    "token": str(row.get("Token", "")).strip(),
                    "tsym": tsym,
                    "exchange": str(row.get("Exchange", "NSE")).strip().upper() or "NSE",
                    "ls": int(float(row.get("LotSize", 1) or 1)),
                    "tick": row.get("TickSize"),
                    "source": os.path.basename(path),
                }
            loaded.append((os.path.basename(path), len(df)))
            break
        with self._lock:
            self._master = master
            self.master_files = [name for name, _ in loaded]
        return master

    def master_size(self):
        with self._lock:
            return len(self._master)

    def set_api(self, api):
        with self._lock:
            # Only drop the cache when the session actually changes, otherwise
            # every lookup would re-query the broker.
            if self.api is not api:
                self._search_cache = {}
            self.api = api

    # ── broker search ────────────────────────────────────────

    @staticmethod
    def exact_match(values, target, exchange="NSE"):
        """The only acceptable broker result: same exchange, equity segment
        and an exact symbol name. Returns None instead of a near miss."""
        target = normalize(target)
        for v in values or []:
            if str(v.get("exch", "")).strip().upper() != str(exchange).strip().upper():
                continue
            if not is_equity(v):
                continue
            name = normalize(v.get("symname") or "")
            tsym = normalize(v.get("tsym") or "")
            if name == target or tsym == target:
                return v
        return None

    def _scrip_from_entry(self, v, exchange, source):
        return {
            "token": str(v.get("token", "")).strip(),
            "tsym": str(v.get("tsym", "")).strip().upper(),
            "exchange": str(v.get("exch", exchange)).strip().upper(),
            "ls": int(float(v.get("ls", 1) or 1)),
            "tick": v.get("ti"),
            "source": source,
        }

    # ── public api ───────────────────────────────────────────

    def resolve(self, symbol, exchange="NSE"):
        """Resolve a symbol. Returns (scrip_or_None, info).

        info keys: requested, normalized, alias, source, reason, candidates
        """
        requested = str(symbol or "").strip()
        target, alias_used = self.aliases.resolve(symbol)
        info = {
            "requested": requested,
            "normalized": target,
            "alias": alias_used,
            "source": None,
            "reason": "",
            "candidates": [],
        }

        if not target:
            info["reason"] = "Empty symbol"
            return None, info

        with self._lock:
            scrip = self._master.get(target)
        if scrip:
            info["source"] = f"master:{scrip.get('source', '')}"
            return dict(scrip), info

        api = self.api
        if api is None:
            info["reason"] = "Not in master and no broker session"
            return None, info

        ckey = (str(exchange).upper(), target)
        with self._lock:
            cached = self._search_cache.get(ckey)
        if cached is not None:
            if cached is False:
                info["reason"] = "No exact match at broker"
                return None, info
            info["source"] = "search"
            return dict(cached), info

        try:
            r = api.searchscrip(str(exchange).upper(), target)
        except Exception as e:
            info["reason"] = f"Broker search failed: {e}"
            return None, info

        values = (r or {}).get("values") or []
        info["candidates"] = [
            f"{v.get('tsym')}/{v.get('instname')}" for v in values[:5]
        ]

        hit = self.exact_match(values, target, exchange)
        if not hit:
            with self._lock:
                self._search_cache[ckey] = False
            info["reason"] = "No exact match at broker"
            return None, info

        scrip = self._scrip_from_entry(hit, exchange, "search")
        with self._lock:
            self._search_cache[ckey] = scrip
        info["source"] = "search"
        return scrip, info
