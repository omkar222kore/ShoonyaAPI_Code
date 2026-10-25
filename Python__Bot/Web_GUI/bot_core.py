"""
Shoonya WebApp - Trading Engine
Extracted from BuySell_updated.py. Pure logic, no Flask imports.
Uses callback hooks so the web layer can push updates.
"""
import os
import sys
import json
import time
import threading
import pandas as pd
import yaml
from datetime import datetime
from NorenRestApiPy.NorenApi import NorenApi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from order_builder import OrderBuilder
from scrip_resolver import ScripResolver, normalize

# How a dry run names each refusal coming out of the converter.
DRY_RUN_VERDICT = {
    "price_mismatch": "PRICE MISMATCH",
    "wrong_instrument": "WRONG SYMBOL",
    "not_found": "NOT FOUND",
    "no_ltp": "NO LTP",
    "zero_lots": "SKIP (0 lots)",
    "empty_symbol": "SKIP",
}


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(
            host="https://trade.shoonya.com/NorenWClientWeb/",
            websocket="wss://trade.shoonya.com/NorenWSWeb/"
        )


class TradingBot:
    def __init__(self, on_log=None, on_pnl=None, on_positions=None,
                 on_status=None, on_order=None, on_closed_trade=None):
        self.api = None
        self.token_df = None
        self.super_token = ""
        self.trading_cap = 1000
        self.userId = ""
        self.running = False
        self._thread = None
        self._stop_event = threading.Event()
        self.processed_stocks = set()

        self.virtual = True
        self.virtual_positions = []
        self.realized_pnl = 0.0
        self._order_seq = 0
        self._vlock = threading.Lock()
        self._scrip_cache = {}
        self.closed_trades = []
        self.logged_in = False

        # Symbol resolution: master first, broker search only on an exact
        # match, plus a shorthand alias table.
        self.resolver = ScripResolver()

        # The Array A -> Array B converter. This is what every entry order
        # goes through, so the broker fields are built in exactly one place.
        self.order_builder = OrderBuilder()

        # Cached values the web layer can read without hitting the broker.
        self.last_pnl = 0.0
        self.last_positions = []
        self._last_raw_positions = []
        self._day_pnl_cache = (0.0, 0.0)
        # Webhook idempotency + short-lived broker-data cache.
        self._seen_alerts = {}
        self._alert_lock = threading.Lock()
        self._cache = {}
        self._cache_lock = threading.Lock()

        # Last thing that happened, for the dashboard's health panel.
        self.last_payload = None
        self.last_order = None

        import config as cfg
        self.eod_time = cfg.EOD_SQUARE_OFF
        self._eod_done = False
        self._sq_off_requested = False
        self._eod_retry_at = 0.0
        self._kill_done = False

        self.on_log = on_log or (lambda *a, **k: None)
        self.on_pnl = on_pnl or (lambda *a, **k: None)
        self.on_positions = on_positions or (lambda *a, **k: None)
        self.on_status = on_status or (lambda *a, **k: None)
        self.on_order = on_order or (lambda *a, **k: None)
        self.on_closed_trade = on_closed_trade or (lambda *a, **k: None)

        # Load the symbol master up front so symbol resolution works before
        # the user logs in (the symbol checker, the dry-run replay and the
        # resolver all need it). Never fatal - start() loads it again.
        try:
            self.load_excel_safe()
        except Exception as e:
            self._log(f"Master preload failed: {e}")

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.on_log(f"[{ts}] {msg}")

    def _cache_get(self, key):
        with self._cache_lock:
            item = self._cache.get(key)
        if not item:
            return None
        value, expiry = item
        if time.time() >= expiry:
            return None
        return value

    def _cache_set(self, key, value, ttl=None):
        import config as cfg
        if ttl is None:
            ttl = getattr(cfg, "QUOTE_CACHE_TTL", 1.0)
        with self._cache_lock:
            self._cache[key] = (value, time.time() + ttl)

    def _record_closed(self, row):
        """Keep the last 50 closes in memory, newest first, and notify UI."""
        self.closed_trades.insert(0, row)
        del self.closed_trades[50:]
        self._day_pnl_cache = (0.0, 0.0)
        try:
            self.on_closed_trade(row)
        except Exception:
            pass

    def today_realized_pnl(self):
        """Sum of today's realised trade PnL from the journal.

        Works even when the bot is stopped or after a server restart, so the
        day's profit is still visible once the market is closed. Cached for a
        few seconds to avoid re-reading the Excel on every status poll."""
        now = time.time()
        ts, cached = self._day_pnl_cache
        if ts and (now - ts) < 5.0:
            return cached

        today = datetime.now().strftime("%Y-%m-%d")
        rows = [r for r in self.closed_trades if str(r.get("date", "")) == today]
        if not rows:
            try:
                import trade_log
                rows = [r for r in trade_log.read_trades(500)
                        if str(r.get("date", "")) == today]
            except Exception as e:
                self._log(f"Day PnL journal read failed: {e}")
                rows = []

        total = 0.0
        for r in rows:
            try:
                total += float(r.get("pnl", 0) or 0)
            except (TypeError, ValueError):
                continue
        total = round(total, 2)
        self._day_pnl_cache = (now, total)
        return total

    # ── Market data ──────────────────────────────────────────

    def _quote(self, exchange, token, fresh=False):
        """Read-only LTP fetch. Safe in both virtual and live mode.

        Cached for QUOTE_CACHE_TTL seconds so the fast monitor loop does not
        hammer the broker. Pass fresh=True for exits/sizing that need the
        latest price.
        """
        ckey = ("quote", str(exchange), str(token))
        if not fresh:
            cached = self._cache_get(ckey)
            if cached is not None:
                return cached
        if self.api is None:
            return None, "No broker session - log in first"
        try:
            q = self.api.get_quotes(exchange=exchange, token=token)
        except Exception as e:
            return None, f"Quote error: {e}"
        if not q or q.get("stat") != "Ok":
            return None, "Quote failed"
        ltp = float(q.get("lp", 0) or 0)
        if ltp <= 0:
            return None, "Invalid price"
        result = (ltp, None)
        self._cache_set(ckey, result)
        return result

    def _resolve_with_info(self, symbol, exchange="NSE"):
        """Resolve a symbol to a tradable scrip. Returns (scrip|None, info).

        The broker's searchscrip() is a fuzzy search, so a near miss is NOT
        acceptable: "HDFCL" used to resolve to HDFCLOWVOL-EQ (INR 19) instead
        of HDFCLIFE-EQ. Only an exact symbol match is accepted now, and
        unknown symbols are rejected instead of being traded.
        """
        if self.resolver is None:
            self.resolver = ScripResolver()
        if self.api is not None:
            self.resolver.set_api(self.api)

        scrip, info = self.resolver.resolve(symbol, exchange)
        if not scrip:
            return None, info

        if info.get("alias"):
            self._log(f"ALIAS {info['alias']} -> {info['normalized']}")
        if info.get("source") == "search":
            self._log(
                f"Resolved {symbol} -> {scrip['tsym']} ({scrip['exchange']})"
                f" token={scrip['token']} lot={scrip['ls']} [exact broker match]"
            )
        self._scrip_cache[(str(exchange).upper(), str(symbol).strip().upper())] = scrip
        return scrip, info

    def _order_builder(self):
        """The Array A -> Array B converter, wired to the current session."""
        if self.order_builder is None:
            self.order_builder = OrderBuilder()
        self.order_builder.set_api(self.api)
        return self.order_builder

    def readiness(self):
        """Is the system ready to trade? Returns checks + human blockers.

        The dashboard shows this so "did the alert arrive and trade?" is a
        single glance, not an archaeology exercise through the log.
        """
        checks = {
            "running": bool(self.running),
            "logged_in": bool(self.logged_in and self.api is not None),
            "master_loaded": self.resolver.master_size() > 0,
            "past_eod": bool(self._eod_reached()),
            "mode": "VIRTUAL" if self.virtual else "LIVE",
        }
        blockers = []
        if not checks["running"]:
            blockers.append("bot is not running - press START")
        if not checks["logged_in"]:
            blockers.append("no broker session - log in first")
        if not checks["master_loaded"]:
            blockers.append("symbol master is empty")
        if checks["past_eod"]:
            blockers.append(f"square-off time {self.eod_time} has already passed")
        return {
            "ready": not blockers,
            "blockers": blockers,
            "checks": checks,
            "master_rows": self.resolver.master_size(),
            "master_files": self.resolver.master_files,
        }

    def _resolve_scrip(self, symbol, exchange="NSE"):
        """Local master first, then the broker search (exact match only)."""
        key = (str(exchange).upper(), str(symbol).strip().upper())
        if key in self._scrip_cache:
            return self._scrip_cache[key]
        scrip, _info = self._resolve_with_info(symbol, exchange)
        return scrip

    def _get_ltp(self, symbol, exchange="NSE", fresh=False):
        """Returns (ltp, scrip, err). scrip is None when resolution fails."""
        sc = self._resolve_scrip(symbol, exchange)
        if not sc:
            return None, None, f"Symbol not found: {symbol}/{exchange}"
        ltp, err = self._quote(sc["exchange"], sc["token"], fresh=fresh)
        if err:
            return None, sc, err
        return ltp, sc, None

    # ── Virtual position book ────────────────────────────────

    def _next_order_id(self):
        with self._vlock:
            self._order_seq += 1
            return f"V-{self._order_seq:06d}"

    def _open_virtual(self, scrip, qty_lots, price):
        order_id = self._next_order_id()
        with self._vlock:
            self.virtual_positions.append({
                "symbol": scrip["tsym"],
                "exchange": scrip["exchange"],
                "token": scrip["token"],
                "ls": scrip.get("ls", 1),
                "qty": qty_lots,
                "entry_price": price,
                "order_id": order_id,
                "opened_at": datetime.now().strftime("%H:%M:%S"),
            })
        return order_id

    def _close_virtual(self, symbol_eq, qty, ltp):
        """Flatten a virtual short position and bank realised PnL.

        Returns (order_id, rows) where rows describe each closed chunk
        for the trade log.
        """
        order_id = self._next_order_id()
        remaining = abs(int(qty))
        closed = 0
        rows = []
        with self._vlock:
            for p in list(self.virtual_positions):
                if p["symbol"] != symbol_eq or remaining <= 0:
                    continue
                take = min(p["qty"], remaining)
                pnl = (p["entry_price"] - ltp) * take * p.get("ls", 1)
                self.realized_pnl += pnl
                rows.append({
                    "symbol": symbol_eq,
                    "exchange": p.get("exchange", "NSE"),
                    "side": "SHORT",
                    "qty": take,
                    "entry": round(float(p["entry_price"]), 4),
                    "exit": round(float(ltp), 4),
                    "pnl": round(pnl, 2),
                })
                p["qty"] -= take
                closed += take
                remaining -= take
                if p["qty"] <= 0:
                    self.virtual_positions.remove(p)
            realized = round(self.realized_pnl, 2)
        self._log(
            f"Closed {closed} lot(s) of {symbol_eq} @ {ltp} | Realised PnL: {realized}"
        )
        return order_id, rows

    def seed_position(self, symbol, entry_price, lots=None):
        """Record a missed entry as an open VIRTUAL short at a known price.

        Back-fills entries the bot never saw (an alert rejected while the app
        was down). The position then behaves like any other: PnL is
        (entry - LTP), stop-loss/take-profit watch it, and the EOD square-off
        closes it into the trade log. Never seeds in LIVE mode and never
        places a broker order.
        """
        if not self.virtual:
            self._log(f"SEED SKIP {symbol}: seeding is VIRTUAL only")
            return None
        try:
            price = float(entry_price)
        except (TypeError, ValueError):
            self._log(f"SEED SKIP {symbol}: bad entry price {entry_price!r}")
            return None
        if price <= 0:
            self._log(f"SEED SKIP {symbol}: entry price must be > 0")
            return None
        if self._eod_reached():
            self._log(f"SEED SKIP {symbol}: EOD {self.eod_time} has passed")
            return None

        row, error = self._order_builder().build_order(
            symbol, trading_cap=self.trading_cap, ltp=price,
            action="SELL", remarks="Seeded_Entry",
        )
        if row is None:
            self._log(f"SEED SKIP {symbol}: {error['message']}")
            return None

        tsym = row["tradingsymbol"]
        with self._vlock:
            if any(p["symbol"] == tsym for p in self.virtual_positions):
                self._log(f"SEED SKIP {tsym}: already open")
                return None

        n_lots = int(lots) if lots else int(row["lots"])
        if n_lots < 1:
            self._log(f"SEED SKIP {tsym}: zero lots at {price:.2f}")
            return None

        scrip = {
            "tsym": tsym,
            "exchange": row["exchange"],
            "token": row["token"],
            "ls": row["lot_size"],
        }
        order_id = self._open_virtual(scrip, n_lots, price)
        self._log(
            f"SEEDED {row['exchange']}:{tsym} | Entry: {price:.2f} | "
            f"Lots: {n_lots} | Qty: {n_lots * row['lot_size']} | Order: {order_id}"
        )
        # A seeded position must be watched for SL/TP/EOD like any other.
        self.processed_stocks.discard(tsym.strip().upper())
        return order_id

    def seed_today(self):
        """Seed the day's missed entries from SEED_FILE, once per day.

        Returns the number of positions added. A ".done_<date>" marker is
        written only when every line was seeded, so a typo can be fixed and
        picked up on the next start without double-seeding.
        """
        import config as cfg
        path = getattr(cfg, "SEED_FILE", "")
        if not path or not os.path.exists(path):
            return 0
        if not self.virtual:
            self._log("SEED: skipped (seeding is VIRTUAL only)")
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        marker = f"{path}.done_{today}"
        if os.path.exists(marker):
            self._log(f"SEED: already applied for {today}")
            return 0

        # Read seed file and filter out entries already closed today
        pairs_to_seed = []
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                symbol, sep, price = line.partition("=")
                if not sep:
                    continue
                symbol = symbol.strip().upper()
                try:
                    price_f = float(price.strip())
                except Exception:
                    pairs_to_seed.append((symbol, price.strip()))
                    continue
                pairs_to_seed.append((symbol, price.strip(), price_f))

        # Check if any of these were already closed today in trade log
        try:
            import trade_log
            trades = trade_log.read_trades(limit=200) or []
            closed_today = set()
            for t in trades:
                if str(t.get("date") or "") == today:
                    sym = str(t.get("symbol") or "").strip().upper()
                    # Match by base symbol (HCLTECH matches HCLTECH-EQ)
                    if sym.endswith("-EQ"):
                        sym_base = sym[:-3]
                    else:
                        sym_base = sym
                    closed_today.add(sym_base)
                    closed_today.add(sym)
        except Exception as e:
            self._log(f"SEED: trade log check failed: {e}")
            closed_today = set()

        # Filter out already closed ones
        filtered = []
        for p in pairs_to_seed:
            if len(p) == 3:
                symbol, price_str, price_f = p
            else:
                symbol, price_str = p[0], p[1]
                price_f = None
            sym_base = symbol[:-3] if symbol.endswith("-EQ") else symbol
            if symbol in closed_today or sym_base in closed_today:
                self._log(f"SEED: skipping {symbol} (already closed today)")
                continue
            filtered.append((symbol, price_str))

        if not filtered:
            self._log(f"SEED: all entries already closed today - cleaning up")
            try:
                os.remove(path)
            except Exception:
                pass
            try:
                with open(marker, "w", encoding="utf-8") as fh:
                    fh.write(f"{today}\n")
            except Exception:
                pass
            return 0

        added = 0
        failed = []
        for symbol, price_str in filtered:
            if self.seed_position(symbol, price_str):
                added += 1
            else:
                failed.append(symbol)

        self._log(f"SEED: {added} missed entr(ies) added for {today}")
        if failed:
            self._log(f"SEED: not added -> {', '.join(failed)}")
        else:
            try:
                with open(marker, "w", encoding="utf-8") as fh:
                    fh.write(f"{today}\n")
            except OSError as e:
                self._log(f"SEED: could not write marker: {e}")

        if added:
            try:
                positions = self.get_positions()
                self.last_positions = self._pos_snapshot(positions)
                self.last_pnl = self._pnl_from(positions)
                self.on_positions(self.last_positions)
                self.on_pnl(self.last_pnl)
            except Exception as e:
                self._log(f"SEED: position refresh failed: {e}")
        return added

    def _virtual_view(self):
        """Aggregate the virtual book into broker-shaped positions with live MTM."""
        agg = {}
        with self._vlock:
            for p in self.virtual_positions:
                a = agg.setdefault(p["symbol"], {
                    "qty": 0, "cost": 0.0, "ls": p.get("ls", 1),
                    "exchange": p["exchange"], "token": p["token"],
                    "opened_at": "",
                })
                a["qty"] += p["qty"]
                a["cost"] += p["entry_price"] * p["qty"]
                opened = p.get("opened_at", "")
                if opened and (not a["opened_at"] or opened < a["opened_at"]):
                    a["opened_at"] = opened

        out = []
        for sym, a in agg.items():
            if a["qty"] <= 0:
                continue
            avg = a["cost"] / a["qty"]
            ltp, err = self._quote(a["exchange"], a["token"])
            if ltp is None:
                ltp = avg
            pnl = round((avg - ltp) * a["qty"] * a["ls"], 2)
            out.append({
                "tsym": sym,
                "netqty": -a["qty"],
                "urmtom": pnl,
                "avgprice": round(avg, 2),
                "ltp": round(ltp, 2),
                "lotsize": a["ls"],
                "exchange": a["exchange"],
                "opened_at": a["opened_at"],
            })
        return out

    def load_excel(self, path):
        import config as cfg
        df = pd.read_excel(path)
        df["TradingSymbol"] = df["TradingSymbol"].astype(str).str.strip().str.upper()
        self.token_df = df
        # The resolver keeps its own copy so a master hit always wins over a
        # broker search. Only the first existing file is used - the rebuilt
        # master is complete, and the legacy file only adds dead tokens.
        try:
            self.resolver.load_master([path, cfg.LEGACY_EXCEL_FILE])
        except Exception as e:
            self._log(f"Master load failed: {e}")
        self._log(f"Loaded {len(df)} symbols from Excel")

    def _load_cred(self):
        import config as cfg
        if not os.path.exists(cfg.BROKER_CRED):
            return {}
        try:
            with open(cfg.BROKER_CRED) as f:
                return yaml.load(f, Loader=yaml.FullLoader) or {}
        except Exception as e:
            self._log(f"ERROR loading cred.yml: {e}")
            return {}

    def _totp(self, factor2):
        factor2 = (factor2 or "").strip()
        if not factor2:
            return ""
        if factor2.isdigit() and len(factor2) == 6:
            return factor2
        try:
            import pyotp
            return pyotp.TOTP(factor2.replace(" ", "")).now()
        except Exception as e:
            self._log(f"TOTP error: {e}")
            return ""

    def _auto_login(self, cred, uid, pwd, otp=""):
        vc = cred.get("vc", "")
        apikey = cred.get("apikey") or cred.get("api_secret") or cred.get("appkey") or ""
        imei = cred.get("imei", "")
        factor2 = cred.get("factor2", "")

        if not otp:
            otp = self._totp(factor2)

        if not all([vc, apikey, imei]) or not otp:
            return None

        hosts = [
            ("https://trade.shoonya.com/NorenWClientWeb/", "wss://trade.shoonya.com/NorenWSWeb/"),
            ("https://api.shoonya.com/NorenWClientAPI/", "wss://api.shoonya.com/NorenWSAPI/"),
        ]
        for host, ws in hosts:
            try:
                tmp = NorenApi(host=host, websocket=ws)
                ret = tmp.login(uid, pwd, otp, vc, apikey, imei)
                if ret and ret.get("susertoken"):
                    return ret["susertoken"]
            except Exception:
                pass
        return None

    def fetch_jkey(self, uid="", pwd="", otp="", vc="", appkey="", imei="", source="WEB", apkversion="1.0.0"):
        """Log into the Shoonya web terminal with a headless browser and return
        the susertoken (jkey). If no OTP is supplied we derive one from the
        TOTP secret in cred.yml (factor2)."""
        cred = self._load_cred() or {}
        uid = (uid or cred.get("user", "")).strip()
        pwd_plain = (pwd or cred.get("pwd", ""))
        otp = (otp or "").strip()
        if not otp and cred.get("factor2"):
            try:
                otp = self._totp(cred["factor2"])
            except Exception:
                otp = ""
        if not all([uid, pwd_plain, otp]):
            return False, "uid/pwd/otp required", ""
        try:
            from shoonya_browser import fetch_jkey as browser_fetch
        except Exception as e:
            return False, f"Browser login unavailable: {e}", ""
        try:
            ok, msg, token = browser_fetch(uid, pwd_plain, otp, headless=True)
        except Exception as e:
            return False, str(e), ""
        return ok, msg, token

    def _verify_session(self):
        try:
            limits = self.api.get_limits()
        except Exception as e:
            return False, f"Session verify error: {e}"
        if not limits:
            return False, "Session invalid (token rejected)"
        return True, "ok"

    def save_credentials(self, user_id="", password="", otp="", jkey=""):
        import config as cfg
        cred = self._load_cred() or {}
        if user_id:
            cred["user"] = user_id
        if password:
            cred["pwd"] = password
        if jkey:
            cred["jkey"] = jkey
        if otp:
            cred["last_otp"] = otp
        try:
            with open(cfg.BROKER_CRED, "w") as f:
                yaml.dump(cred, f, default_flow_style=False, sort_keys=False)
            return True, f"Saved to {os.path.basename(cfg.BROKER_CRED)}"
        except Exception as e:
            return False, f"Save error: {e}"

    def login_from_ui(self, user_id="", password="", otp="", jkey=""):
        cred = self._load_cred() or {}
        uid = (user_id or cred.get("user", "")).strip()
        pwd = password or cred.get("pwd", "")
        jkeyv = (jkey or "").strip()

        if not uid or not pwd:
            return False, "User ID and password required (cred.yml not found)", ""

        try:
            self.api = ShoonyaApiPy()
        except Exception as e:
            return False, f"Init error: {e}", uid

        token = jkeyv
        if not token:
            token = self._auto_login(cred, uid, pwd, otp)
            if not token:
                return False, "Auto-login failed. Paste a JKEY from the browser instead.", uid

        try:
            self.api.set_session(uid, pwd, token)
        except Exception as e:
            return False, f"Session error: {e}", uid

        ok, info = self._verify_session()
        if not ok:
            return False, info, uid

        self.super_token = token
        self.userId = uid
        self.logged_in = True
        self.on_status("CONNECTED")
        self._log(f"Login successful | User: {uid}")
        return True, f"Logged in as {uid}", uid

    def login(self, super_token="", trading_cap=None, user_id="", password=""):
        import config as cfg
        cred = self._load_cred() or {}
        self.userId = user_id or cred.get("user", "")
        pwd = password or cred.get("pwd", "")
        if not self.userId or not pwd:
            self._log("ERROR: missing user/password (cred.yml or UI)")
            self.on_status("LOGIN_FAILED")
            return False
        self.super_token = super_token or ""
        if trading_cap is not None:
            self.trading_cap = trading_cap

        try:
            self._log("Logging into Shoonya broker...")
            self.api = ShoonyaApiPy()
            ret = self.api.set_session(self.userId, pwd, self.super_token)
        except Exception as e:
            self._log(f"Login ERROR: {e}")
            self.on_status("LOGIN_FAILED")
            return False

        if ret:
            self.logged_in = True
            self._log(f"Login successful | User: {self.userId} | Capital: {self.trading_cap}")
            self.on_status("CONNECTED")
            return True
        self._log("Login FAILED")
        self.on_status("LOGIN_FAILED")
        return False

    def start(self, super_token, trading_cap, virtual=True):
        if self.running:
            self._log("Bot already running")
            return False

        self._eod_done = False
        self._sq_off_requested = False
        self._eod_retry_at = 0.0
        self._kill_done = False
        if self._eod_reached():
            self._log(
                f"EOD {self.eod_time} already passed - start blocked. "
                "Change the square-off time to start."
            )
            return False

        if not self.load_excel_safe():
            return False

        if not self.login(super_token, trading_cap):
            return False

        self.virtual = bool(virtual)
        with self._vlock:
            self.virtual_positions = []
            self.realized_pnl = 0.0
            self._order_seq = 0

        mode = "VIRTUAL (paper trading - no real orders)" if self.virtual else "LIVE (real broker orders)"
        self._log(f"Mode: {mode}")

        self._stop_event.clear()
        self.running = True
        self.processed_stocks = set()
        self._seen_alerts = {}
        self._cache = {}
        self.last_pnl = 0.0
        self.last_positions = []
        self._day_pnl_cache = (0.0, 0.0)
        # Back-fill entries the bot never saw today (virtual only, once a day).
        self.seed_today()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self.on_status("RUNNING" if self.virtual else "LIVE")
        self._log("Monitor thread started")
        return True

    def load_excel_safe(self):
        import config as cfg
        candidates = [cfg.EXCEL_FILE, cfg.LEGACY_EXCEL_FILE]
        for path in candidates:
            if not path or not os.path.exists(path):
                continue
            try:
                self.load_excel(path)
                return True
            except Exception as e:
                self._log(f"ERROR loading {os.path.basename(path)}: {e}")
        self._log(f"ERROR: no symbol master found ({', '.join(candidates)})")
        return False

    def stop(self):
        if not self.running:
            return
        self._stop_event.set()
        self.running = False
        self.on_status("STOPPED")
        self._log("Bot stopped")

    def _eod_reached(self):
        """True once the clock has reached today's square-off time."""
        if not self.eod_time:
            return False
        return datetime.now().strftime("%H:%M") >= self.eod_time

    def set_eod_time(self, value):
        """Validate HH:MM and store it. Returns (ok, message)."""
        value = (value or "").strip()
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            return False, "Time must be in HH:MM format (e.g. 15:10)"
        self.eod_time = value
        self._eod_done = False
        return True, f"Square-off time set to {value}"

    def request_square_off(self):
        """Flag a manual square-off; the monitor thread performs it."""
        if not self.running:
            return False, "Bot is not running"
        self._sq_off_requested = True
        return True, "Square-off requested"

    def square_off(self, reason):
        """Close every open position. Runs inside the monitor thread only."""
        try:
            positions = self.get_positions(fresh=True)
        except Exception as e:
            self._log(f"SQUARE-OFF ERROR reading positions: {e}")
            positions = []

        open_pos = [p for p in positions if int(float(p.get("netqty", 0))) != 0]
        if not open_pos:
            self._log(f"SQUARE-OFF ({reason}) | No open positions")
            self.on_positions([])
            return 0

        self._log(f"SQUARE-OFF ({reason}) | Closing {len(open_pos)} position(s)")
        closed = 0
        for p in open_pos:
            sym = str(p.get("tsym", "")).strip().upper()
            exch = str(p.get("exchange") or p.get("exch") or "NSE")
            qty = int(float(p.get("netqty", 0)))
            if qty == 0:
                continue
            if self.virtual:
                ltp = float(p.get("ltp", 0)) or float(p.get("avgprice", 0))
            else:
                ltp = 0.0
            if self._exit_position(sym, qty, ltp, exch, reason=reason):
                self.processed_stocks.add(sym)
                closed += 1

        # Re-read the book so the UI and log reflect what is actually left open
        # (never report "flat" when a close failed).
        try:
            remaining = self.get_positions(fresh=True)
        except Exception as e:
            self._log(f"SQUARE-OFF re-read failed: {e}")
            remaining = []
        still_open = [p for p in remaining if int(float(p.get("netqty", 0))) != 0]
        self.last_positions = self._pos_snapshot(remaining)
        self.on_positions(self.last_positions)
        self.on_pnl(self.get_total_pnl(fresh=True))
        if still_open:
            self._log(
                f"SQUARE-OFF ({reason}) INCOMPLETE | {len(still_open)}/"
                f"{len(open_pos)} still open - will retry"
            )
        else:
            self._log(
                f"SQUARE-OFF ({reason}) complete | Closed {closed}/{len(open_pos)} "
                f"| Realised PnL: {round(self.realized_pnl, 2)}"
            )
        return closed

    def is_valid_trigger_time(self, time_str):
        from config import VALID_TRIGGER_TIMES
        return str(time_str).strip() in VALID_TRIGGER_TIMES

    def parse_webhook_payload(self, data):
        stocks, _dropped = self.parse_alert(data)
        return stocks

    def parse_alert(self, data):
        """Parse a Chartink alert. Returns (stocks, dropped).

        `dropped` lists the symbols that were NOT attempted (an alert with
        more symbols than MAX_STOCKS_PER_TIME). They are reported back to the
        caller so nothing is ever dropped silently.
        """
        if not data:
            raise ValueError("Webhook payload is empty")

        stocks_raw = data.get("stocks", "")
        prices_raw = data.get("trigger_prices", "")
        triggered_at = data.get("triggered_at", "")

        if not stocks_raw or not prices_raw or not triggered_at:
            raise ValueError("Missing required fields")

        symbols = [s.strip() for s in stocks_raw.split(",") if s.strip()]
        prices = [p.strip() for p in prices_raw.split(",") if p.strip()]

        if len(symbols) != len(prices):
            raise ValueError("Stock and price count mismatch")

        dropped = []
        from config import MAX_STOCKS_PER_TIME
        if len(symbols) > MAX_STOCKS_PER_TIME:
            # Trade the first N instead of throwing the whole alert away.
            extra = symbols[MAX_STOCKS_PER_TIME:]
            extra_prices = prices[MAX_STOCKS_PER_TIME:]
            symbols = symbols[:MAX_STOCKS_PER_TIME]
            prices = prices[:MAX_STOCKS_PER_TIME]
            dropped = [
                {
                    "symbol": s,
                    "trigger_price": p,
                    "code": "too_many_symbols",
                    "reason": (f"alert had more than {MAX_STOCKS_PER_TIME} symbols - "
                               f"only the first {MAX_STOCKS_PER_TIME} are traded"),
                }
                for s, p in zip(extra, extra_prices)
            ]
            self._log(
                f"Received {len(symbols) + len(dropped)} stocks, trading the first "
                f"{MAX_STOCKS_PER_TIME}. Dropped: {', '.join(extra)}"
            )

        trigger_time = datetime.strptime(
            triggered_at.strip().upper(), "%I:%M %p"
        ).strftime("%H:%M")

        exchange = str(data.get("exchange", "NSE") or "NSE").strip().upper()

        parsed = []
        for symbol, price in zip(symbols, prices):
            parsed.append({
                "symbol": symbol,
                "trigger_price": float(price),
                "time": trigger_time,
                "exchange": exchange,
            })
        return parsed, dropped

    def filter_stocks(self, stocks):
        if not stocks:
            return []
        for stock in stocks:
            time_value = stock.get("time", "").strip()
            if not self.is_valid_trigger_time(time_value):
                self._log(f"Time {time_value} not a valid trigger time")
                return []
        return stocks

    def place_sell_orders(self, stocks):
        if self._eod_reached():
            self._log(f"EOD {self.eod_time} reached - ignoring entry orders")
            return []

        import config as cfg
        mode = "VIRTUAL" if self.virtual else "LIVE"
        self._log(f"--- PLACING {mode} SELL ORDERS ---")
        results = []
        for stock in stocks:
            symbol = stock.get("symbol", "UNKNOWN").strip()
            exchange = stock.get("exchange", "NSE")
            trigger_price = stock.get("trigger_price")
            result = {"symbol": symbol, "status": "skipped", "detail": "", "tsym": None,
                      "code": None}

            try:
                # One converter, one contract: either a complete broker order
                # row (Array B) or a reason why this symbol must not trade.
                builder = self._order_builder()
                row, error = builder.build_order(
                    symbol,
                    exchange=exchange,
                    trading_cap=self.trading_cap,
                    trigger_price=trigger_price,
                    action="SELL",
                    remarks="Webhook_Sell",
                )
                if row is None:
                    self._log(f"SKIP {symbol}/{exchange}: {error['message']}")
                    result["detail"] = error["message"]
                    result["code"] = error["code"]
                    results.append(result)
                    continue

                if row.get("alias"):
                    self._log(f"ALIAS {row['alias']} -> {row['tradingsymbol']}")

                current_ltp = row["ltp"]
                tsym = row["tradingsymbol"]
                lot = row["lot_size"]
                lots = row["lots"]
                quantity = row["quantity"]      # SHARES - the broker counts shares

                if self.virtual:
                    scrip = {
                        "tsym": tsym,
                        "exchange": row["exchange"],
                        "token": row["token"],
                        "ls": lot,
                    }
                    order_id = self._open_virtual(scrip, lots, current_ltp)
                    self._log(
                        f"V-SELL | {row['exchange']}:{tsym} | LTP: {current_ltp:.2f} | "
                        f"Lot: {lot} | Lots: {lots} | Qty: {quantity} | Order: {order_id}"
                    )
                else:
                    try:
                        self._log(f"API_TYPE: {type(self.api)}")
                        self._log(f"PLACE {tsym} qty={row['quantity']} exch={row['exchange']} side={'S'}")
                        try:
                            response = self.api.place_order(
                                buy_or_sell='S',
                                product_type='I',
                                exchange=row['exchange'],
                                tradingsymbol=tsym,
                                quantity=int(row['quantity']),
                                discloseqty=0,
                                price_type='MKT',
                                retention='DAY',
                                remarks='Webhook_Sell',
                            )
                            self._log(f"RESP_OLD {tsym}: {repr(response)}")
                        except Exception as e1:
                            self._log(f"OLD_STYLE_ERR {e1}")
                            kwargs = builder.to_place_order_kwargs(row)
                            response = self.api.place_order(**kwargs)
                            self._log(f"RESP_KW {tsym}: {repr(response)}")
                    except Exception as e:
                        self._log(f"PLACE_EXC {tsym}: {e}")
                        import traceback
                        self._log(traceback.format_exc())
                        detail = f"order error: {e}"
                        result["detail"] = detail
                        result["tsym"] = tsym
                        results.append(result)
                        continue
                    order_id = None
                    if isinstance(response, dict):
                        for k in ['norenordno', 'orderid', 'orderno', 'nestOrderNumber', 'result']:
                            if response.get(k):
                                order_id = response[k]
                                break
                    elif isinstance(response, str) and response.strip().lower() not in ('none', 'null', ''):
                        order_id = response.strip()
                    if not order_id or str(order_id).strip().lower() in ('none', 'null', ''):
                        detail = f"order rejected: {response}"
                        self._log(f"SKIP {tsym}: {detail}")
                        result["detail"] = detail
                        result["tsym"] = tsym
                        results.append(result)
                        continue
                    self._log(
                        f"SELL | {row['exchange']}:{tsym} | LTP: {current_ltp:.2f} | "
                        f"Lots: {lots} | Qty: {quantity} | Order: {order_id}"
                    )

                # A freshly opened position must be monitored again even if this
                # symbol was exited earlier today (re-entry support).
                self.processed_stocks.discard(tsym.strip().upper())

                result["status"] = "traded"
                result["tsym"] = tsym
                result["qty"] = lots
                result["shares"] = quantity
                result["price"] = current_ltp

                self.last_order = {
                    "symbol": tsym,
                    "tsym": tsym,
                    "order_id": order_id,
                    "qty": quantity,
                    "lots": lots,
                    "lot_size": lot,
                    "price": current_ltp,
                    "mode": mode,
                    "at": datetime.now().isoformat(timespec="seconds"),
                }

                self.on_order({
                    "symbol": tsym,
                    "direction": "SELL",
                    "price": current_ltp,
                    "qty": lots,
                    "shares": quantity,
                    "lotsize": lot,
                    "exchange": row["exchange"],
                    "order_id": order_id,
                    "virtual": self.virtual,
                })

            except Exception as e:
                self._log(f"ERROR {symbol}: {e}")
                result["detail"] = str(e)
            results.append(result)

        traded = [r for r in results if r["status"] == "traded"]
        skipped = [r for r in results if r["status"] != "traded"]
        summary = (f"ALERT SUMMARY: {len(stocks)} requested, {len(traded)} traded, "
                   f"{len(skipped)} skipped")
        if skipped:
            summary += " | " + " | ".join(f"{r['symbol']}: {r['detail']}" for r in skipped)
        self._log(summary)
        return results

    def _persist_payload(self, data, result):
        """Append every received payload to disk so we can audit what arrived
        and replay it in dry-run mode later."""
        import config as cfg
        try:
            os.makedirs(cfg.PAYLOAD_DIR, exist_ok=True)
            day = datetime.now().strftime("%Y-%m-%d")
            path = os.path.join(cfg.PAYLOAD_DIR, f"{day}.jsonl")
            rec = {
                "received_at": datetime.now().isoformat(timespec="seconds"),
                "payload": data,
                "result": result,
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        except Exception as e:
            self._log(f"Payload log failed: {e}")

    def dry_run(self, data):
        """Resolve and size a payload WITHOUT placing any order.

        Shows exactly what would have happened for an alert, including the
        symbols that would have been rejected and why.
        """
        import config as cfg
        from datetime import datetime as _dt

        stocks_raw = str(data.get("stocks", ""))
        prices_raw = str(data.get("trigger_prices", ""))
        triggered_at = str(data.get("triggered_at", ""))
        symbols = [s.strip() for s in stocks_raw.split(",") if s.strip()]
        prices = [p.strip() for p in prices_raw.split(",") if p.strip()]
        exchange = str(data.get("exchange", "NSE") or "NSE").strip().upper()

        trigger_time = ""
        try:
            trigger_time = _dt.strptime(triggered_at.strip().upper(), "%I:%M %p").strftime("%H:%M")
        except Exception:
            trigger_time = triggered_at.strip()

        notes = []
        time_ok = self.is_valid_trigger_time(trigger_time)
        if not time_ok:
            notes.append(f"Trigger time '{trigger_time}' is not in VALID_TRIGGER_TIMES - "
                         f"the live bot would reject this alert")
        if len(symbols) > cfg.MAX_STOCKS_PER_TIME:
            notes.append(f"{len(symbols)} symbols > MAX_STOCKS_PER_TIME "
                         f"({cfg.MAX_STOCKS_PER_TIME}) - the live bot trades the first "
                         f"{cfg.MAX_STOCKS_PER_TIME} and drops "
                         f"{', '.join(symbols[cfg.MAX_STOCKS_PER_TIME:])}")
        if len(symbols) != len(prices):
            notes.append("Symbol/price count mismatch")

        rows = []
        for i, symbol in enumerate(symbols):
            trigger = None
            if i < len(prices):
                try:
                    trigger = float(prices[i])
                except ValueError:
                    trigger = None
            row = {
                "symbol": symbol, "trigger_price": trigger, "tsym": None,
                "token": None, "lot": None, "ltp": None, "qty": None,
                "shares": None, "verdict": "SKIP", "reason": "", "alias": None,
                "code": None,
            }
            # Same converter the live path uses, so a dry run is an exact
            # preview of what the real order would be.
            builder = self._order_builder()
            order, error = builder.build_order(
                symbol,
                exchange=exchange,
                trading_cap=self.trading_cap,
                trigger_price=trigger,
                action="SELL",
            )
            row["alias"] = builder.aliases.resolve(symbol)[1]
            if order is None:
                row["verdict"] = DRY_RUN_VERDICT.get(error["code"], "SKIP")
                row["reason"] = error["message"]
                row["code"] = error["code"]
                rows.append(row)
                continue

            row["tsym"] = order["tradingsymbol"]
            row["token"] = order["token"]
            row["lot"] = order["lot_size"]
            row["ltp"] = round(order["ltp"], 2)

            if not time_ok:
                row["verdict"] = "SKIPPED (invalid trigger time)"
                row["reason"] = (f"trigger time '{trigger_time}' is not in "
                                 f"VALID_TRIGGER_TIMES - the live bot drops the "
                                 f"whole alert")
            else:
                row["qty"] = order["lots"]
                row["shares"] = order["quantity"]
                row["verdict"] = "WOULD TRADE"
            rows.append(row)

        return {
            "status": "dry_run",
            "trigger_time": trigger_time,
            "capital": self.trading_cap,
            "notes": notes,
            "rows": rows,
        }

    def handle_webhook(self, data):
        self._log("=" * 60)
        self._log(f"WEBHOOK RECEIVED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log("=" * 60)

        result = None
        try:
            parsed, dropped = self.parse_alert(data)
            filtered = self.filter_stocks(parsed)
            if not filtered:
                reason = "no valid trigger time" if parsed else "nothing to trade"
                self._log(f"REJECTED alert: {reason}")
                result = {"status": "rejected", "reason": reason,
                          "dropped": [d["symbol"] for d in dropped]}
                return result

            # Square-off time reached: no entry orders after this point.
            # Said out loud instead of returning a silent "success".
            if self._eod_reached():
                reason = (f"EOD {self.eod_time} reached - entry orders are not "
                          "sent any more")
                self._log(f"BLOCKED alert: {reason}")
                result = {"status": "blocked", "reason": reason,
                          "mode": "VIRTUAL" if self.virtual else "LIVE",
                          "traded": 0, "skipped": len(filtered),
                          "dropped": [d["symbol"] for d in dropped],
                          "results": []}
                return result

            # Idempotency: the same alert (trigger time + symbol set) must never
            # open positions twice, no matter how many times it is delivered.
            key = (
                filtered[0].get("time", ""),
                tuple(sorted(s.get("symbol", "").strip().upper() for s in filtered)),
            )
            with self._alert_lock:
                if key in self._seen_alerts:
                    self._log(
                        f"DUPLICATE webhook ignored | time={key[0]} "
                        f"| symbols={','.join(key[1])}"
                    )
                    result = {"status": "duplicate", "time": key[0]}
                    return result
                self._seen_alerts[key] = datetime.now()

            outcomes = self.place_sell_orders(filtered)
            for d in dropped:
                outcomes.append({
                    "symbol": d["symbol"],
                    "status": "skipped",
                    "detail": d["reason"],
                    "code": d["code"],
                    "tsym": None,
                    "trigger_price": d.get("trigger_price"),
                })
            traded = [o for o in outcomes if o.get("status") == "traded"]
            skipped = [o for o in outcomes if o.get("status") != "traded"]
            result = {
                # "success" means at least one order was placed. "no_trades"
                # means the alert was understood but nothing was traded -
                # every reason is in results[].
                "status": "success" if traded else "no_trades",
                "mode": "VIRTUAL" if self.virtual else "LIVE",
                "traded": len(traded),
                "skipped": len(skipped),
                "dropped": [d["symbol"] for d in dropped],
                "results": outcomes,
            }
            return result
        except Exception as e:
            self._log(f"Webhook error: {e}")
            result = {"status": "error", "message": str(e)}
            return result
        finally:
            self._persist_payload(data, result)
            self.last_payload = {
                "received_at": datetime.now().isoformat(timespec="seconds"),
                "symbols": [
                    s.strip() for s in str((data or {}).get("stocks", "")).split(",")
                    if s.strip()
                ],
                "status": (result or {}).get("status"),
                "traded": (result or {}).get("traded"),
                "skipped": (result or {}).get("skipped"),
                "reason": (result or {}).get("reason") or (result or {}).get("message"),
            }

    def _pnl_from(self, positions):
        """Total PnL from an already-fetched position snapshot."""
        if self.virtual:
            open_pnl = sum(float(p.get("urmtom", 0) or 0) for p in positions)
            return round(open_pnl + self.realized_pnl, 2)
        mtm = sum(float(i.get("urmtom", 0) or 0) for i in positions)
        pnl = sum(float(i.get("rpnl", 0) or 0) for i in positions)
        return round(mtm + pnl, 2)

    def get_total_pnl(self, fresh=False):
        try:
            return self._pnl_from(self.get_positions(fresh=fresh))
        except Exception as e:
            self._log(f"PnL Fetch Error: {e}")
            return self.last_pnl

    def get_positions(self, fresh=False):
        """Position snapshot. In live mode the broker call is cached for
        POS_CACHE_TTL seconds; pass fresh=True for exits/square-off.

        On a fetch error we return the last known snapshot rather than an empty
        list, so a transient API glitch is never mistaken for "flat"."""
        if self.virtual:
            return self._virtual_view()
        if not fresh:
            cached = self._cache_get(("positions",))
            if cached is not None:
                return cached
        import config as cfg
        try:
            ret = self.api.get_positions() or []
        except Exception as e:
            self._log(f"Position fetch error: {e}")
            return self._last_raw_positions
        self._last_raw_positions = ret
        self._cache_set(("positions",), ret, getattr(cfg, "POS_CACHE_TTL", 1.0))
        return ret

    def _lookup_live_exit(self, sym):
        """Return (entry_price, exit_price, pnl) for a live position.

        Read immediately before the exit order so the journal matches
        what the broker actually reports at that moment.
        """
        try:
            for p in self.get_positions(fresh=True):
                if str(p.get("tsym", "")).strip().upper() != sym:
                    continue
                entry = float(p.get("avgprice", 0) or 0)
                urmtom = float(p.get("urmtom", 0) or 0)
                qty = float(p.get("netqty", 0) or 0)
                exit_px = float(p.get("ltp", 0) or 0)
                if not exit_px and qty:
                    exit_px = entry - (urmtom / qty)
                return entry, round(exit_px, 4), round(urmtom, 2)
        except Exception as e:
            self._log(f"LIVE EXIT LOOKUP FAILED {sym}: {e}")
        return None, None, None

    def _log_trades(self, rows, order_id, reason):
        """Publish closed trades to the UI and the Excel journal.

        One row dict feeds both, so the screen and the file can never
        disagree. Never raises - a failed write must not break trading.
        """
        if not rows:
            return

        mode = "VIRTUAL" if self.virtual else "LIVE"
        now = datetime.now()
        for r in rows:
            row = {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "exchange": r.get("exchange", "NSE"),
                "symbol": r.get("symbol", ""),
                "side": r.get("side", ""),
                "qty": r.get("qty", 0),
                "entry": r.get("entry"),
                "exit": r.get("exit"),
                "pnl": r.get("pnl"),
                "mode": mode,
                "reason": reason or "",
                "order_id": order_id,
            }
            self._record_closed(row)
            try:
                import trade_log
                trade_log.append_trade(row)
            except Exception as e:
                self._log(f"TRADE_LOG write failed: {e}")

    def _order_status(self, order_id):
        """Latest status string for a broker order id, or None if unknown."""
        try:
            book = self.api.get_order_book() or []
        except Exception as e:
            self._log(f"Order book error: {e}")
            return None
        for o in book:
            if str(o.get("norenordno", "")) == str(order_id):
                return str(o.get("status", "")).strip().upper()
        return None

    def _wait_for_fill(self, order_id, sym, timeout=None):
        """Poll until a live exit is confirmed filled (or rejected).

        The position book is the source of truth: an order that was merely
        *accepted* is not a closed position. Returns True only when the symbol
        is flat, False on rejection/timeout so the caller can safely retry.
        """
        import config as cfg
        if timeout is None:
            timeout = getattr(cfg, "EXIT_FILL_TIMEOUT", 8.0)
        deadline = time.time() + timeout
        status = None
        while time.time() < deadline:
            try:
                pos = self.get_positions(fresh=True)
                still_open = any(
                    str(p.get("tsym", "")).strip().upper() == sym
                    and int(float(p.get("netqty", 0) or 0)) != 0
                    for p in pos
                )
                if not still_open:
                    return True
            except Exception as e:
                self._log(f"EXIT VERIFY ERROR {sym}: {e}")

            status = self._order_status(order_id)
            if status in ("REJECTED", "CANCELED", "CANCELLED", "INVALID"):
                self._log(f"EXIT ORDER {order_id} {status} for {sym}")
                return False
            time.sleep(0.4)

        self._log(
            f"EXIT NOT CONFIRMED for {sym} within {timeout:.0f}s "
            f"(order {order_id}, status={status}) - will retry"
        )
        return False

    def _exit_position(self, sym, qty, ltp, exchange="NSE", reason=""):
        """Close a position - virtual book or real broker order."""
        qty = int(qty)
        side = "SHORT" if qty < 0 else "LONG"

        if self.virtual:
            order_id, rows = self._close_virtual(sym, qty, ltp)
            self._log(f"V-EXITED {sym} | Lots: {abs(qty)} @ {ltp:.2f} | Order: {order_id}")
            self.on_order({
                "symbol": sym, "direction": "BUY", "qty": abs(qty),
                "order_id": order_id, "type": "EXIT",
                "exchange": exchange, "virtual": True,
            })
            self._log_trades(rows, order_id, reason)
            return True

        entry, exit_px, urmtom = self._lookup_live_exit(sym)
        close_side = "B" if qty < 0 else "S"

        try:
            response = self.api.place_order(
                buy_or_sell=close_side,
                product_type="I",
                exchange=exchange,
                tradingsymbol=sym,
                quantity=abs(qty),
                discloseqty=0,
                price_type="MKT",
                retention="DAY",
                remarks="Exit_Order",
            )
        except Exception as e:
            self._log(f"EXIT ORDER ERROR {sym}: {e}")
            return False

        order_id = response.get("norenordno") if response else None
        if not order_id:
            self._log(f"EXIT FAILED {sym}: {response}")
            return False

        self._log(f"EXIT PLACED {sym} | Order: {order_id} | awaiting fill...")
        if not self._wait_for_fill(order_id, sym):
            return False

        self._log(f"EXITED {sym} | Order: {order_id}")
        self.on_order({
            "symbol": sym, "direction": "BUY" if qty < 0 else "SELL",
            "qty": abs(qty), "order_id": order_id, "type": "EXIT",
            "exchange": exchange,
        })
        self._log_trades([{
            "symbol": sym, "exchange": exchange, "side": side,
            "qty": abs(qty), "entry": entry, "exit": exit_px,
            "pnl": urmtom,
        }], order_id, reason)
        return True

    @staticmethod
    def _pos_snapshot(positions):
        """Shape positions for the UI: symbol, qty, live P&L, entry, opened-at."""
        out = []
        for p in positions:
            out.append({
                "symbol": str(p.get("tsym", "")).strip().upper(),
                "qty": int(float(p.get("netqty", 0) or 0)),
                "pnl": float(p.get("urmtom", 0) or 0),
                "entry": float(p.get("avgprice", 0) or 0),
                "time": str(p.get("opened_at", "") or ""),
            })
        return out

    def _monitor_loop(self):
        from config import (PNL_STOP_LOSS_PCT, PNL_TAKE_PROFIT_PCT,
                            MONITOR_INTERVAL, CYCLE_LOG_EVERY, MAX_DAILY_LOSS)
        cycle = 1
        last_log = 0.0
        while not self._stop_event.is_set():
            try:
                positions = self.get_positions()
                total_pnl = self._pnl_from(positions)

                self.last_positions = self._pos_snapshot(positions)
                self.last_pnl = total_pnl
                self.on_pnl(total_pnl)

                squared = False
                if self._sq_off_requested:
                    self._sq_off_requested = False
                    self.square_off("MANUAL")
                    squared = True

                # Daily-loss kill switch (disabled when MAX_DAILY_LOSS <= 0).
                if (MAX_DAILY_LOSS > 0 and not self._kill_done
                        and total_pnl <= -MAX_DAILY_LOSS):
                    self._kill_done = True
                    self._log(
                        f"DAILY-LOSS LIMIT HIT | PnL {total_pnl} <= "
                        f"-{MAX_DAILY_LOSS} - squaring off and stopping"
                    )
                    self.square_off("DAILY-LOSS")
                    self.stop()
                    break

                if self._eod_reached() and not self._eod_done:
                    if not squared and time.time() >= self._eod_retry_at:
                        retry = self._eod_retry_at > 0
                        self.square_off(f"EOD {self.eod_time}")
                        squared = True
                        self._eod_retry_at = time.time() + 5.0
                        if retry:
                            self._log(
                                f"EOD {self.eod_time}: retrying square-off"
                            )
                    positions = self.get_positions(fresh=True)
                    total_pnl = self._pnl_from(positions)
                    self.last_pnl = total_pnl
                    self.on_pnl(total_pnl)
                    still_open = [
                        p for p in positions
                        if int(float(p.get("netqty", 0))) != 0
                    ]
                    if not still_open:
                        self._eod_done = True
                        self._log(
                            f"EOD {self.eod_time} reached - flat, stopping bot"
                        )
                        self.stop()
                        break
                elif squared:
                    positions = self.get_positions(fresh=True)
                    total_pnl = self._pnl_from(positions)
                    self.last_pnl = total_pnl
                    self.on_pnl(total_pnl)

                log_now = (cycle == 1) or (time.time() - last_log >= CYCLE_LOG_EVERY)
                pos_list = []

                if not positions:
                    self.last_positions = []
                    self.on_positions([])
                else:
                    exited = set()
                    for p in positions:
                        sym = str(p.get("tsym", "")).strip().upper()
                        exch = str(p.get("exchange") or p.get("exch") or "NSE")
                        lot = int(p.get("lotsize", 1) or 1)
                        qty = int(float(p.get("netqty", 0)))
                        urmtom = float(p.get("urmtom", 0))
                        pos_list.append({"symbol": sym, "qty": qty, "pnl": urmtom})
                        if log_now:
                            self._log(
                                f"{exch}:{sym} | Lots: {abs(qty)} | LotSize: {lot} "
                                f"| PnL: {urmtom}"
                            )

                        if sym in self.processed_stocks or qty == 0:
                            continue

                        lower = -(self.trading_cap * PNL_STOP_LOSS_PCT)
                        upper = self.trading_cap * PNL_TAKE_PROFIT_PCT

                        if urmtom <= lower or urmtom >= upper:
                            hit = "STOP-LOSS" if urmtom <= lower else "TAKE-PROFIT"
                            if self.virtual:
                                ltp = float(p.get("ltp", 0)) or float(p.get("avgprice", 0))
                            else:
                                ltp = 0.0
                            self._log(f"{hit} hit on {exch}:{sym} | PnL: {urmtom}")
                            if self._exit_position(sym, qty, ltp, exch, reason=hit):
                                self.processed_stocks.add(sym)
                                exited.add(sym)

                    if exited:
                        # pos_list was built before the exits - refresh so a just
                        # closed symbol is not shown as still open.
                        positions = self.get_positions(fresh=True)
                        pos_list = self._pos_snapshot(positions)
                        total_pnl = self._pnl_from(positions)
                        self.last_pnl = total_pnl
                        self.on_pnl(total_pnl)

                    self.on_positions(pos_list)

                if log_now:
                    self._log(
                        f"Cycle #{cycle} | {'VIRTUAL' if self.virtual else 'LIVE'}"
                        f" | Pos: {len(pos_list)} | PnL: {total_pnl}"
                    )
                    last_log = time.time()

            except Exception as e:
                self._log(f"MONITOR ERROR: {e}")

            self._stop_event.wait(MONITOR_INTERVAL)
            cycle += 1
