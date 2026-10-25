"""
Shoonya WebApp - Trading Engine
Extracted from BuySell_updated.py. Pure logic, no Flask imports.
Uses callback hooks so the web layer can push updates.
"""
import os
import time
import threading
import pandas as pd
import yaml
from datetime import datetime
from NorenRestApiPy.NorenApi import NorenApi


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

    def _resolve_scrip(self, symbol, exchange="NSE"):
        """Local Excel master first, then broker searchscrip (nearest expiry)."""
        exch = str(exchange).strip().upper()
        sym = str(symbol).strip().upper()
        key = (exch, sym)
        if key in self._scrip_cache:
            return self._scrip_cache[key]

        if exch == "NSE" and self.token_df is not None:
            want = sym if sym.endswith("-EQ") else f"{sym}-EQ"
            m = self.token_df[self.token_df["TradingSymbol"] == want]
            if not m.empty:
                row = m.iloc[0]
                sc = {
                    "token": str(row["Token"]),
                    "tsym": str(row["TradingSymbol"]),
                    "exchange": "NSE",
                    "ls": int(row.get("LotSize", 1) or 1),
                }
                self._scrip_cache[key] = sc
                return sc

        try:
            r = self.api.searchscrip(exch, sym)
            vals = (r or {}).get("values") or []
            if vals:
                v = vals[0]  # nearest expiry
                sc = {
                    "token": str(v["token"]),
                    "tsym": str(v["tsym"]),
                    "exchange": str(v.get("exch", exch)),
                    "ls": int(float(v.get("ls", 1) or 1)),
                }
                self._scrip_cache[key] = sc
                self._log(
                    f"Resolved {sym} -> {sc['tsym']} ({sc['exchange']})"
                    f" token={sc['token']} lot={sc['ls']}"
                )
                return sc
        except Exception as e:
            self._log(f"RESOLVE ERROR {sym}/{exch}: {e}")

        return None

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
        df = pd.read_excel(path)
        df["TradingSymbol"] = df["TradingSymbol"].astype(str).str.strip().str.upper()
        self.token_df = df
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
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self.on_status("RUNNING" if self.virtual else "LIVE")
        self._log("Monitor thread started")
        return True

    def load_excel_safe(self):
        import config as cfg
        if not os.path.exists(cfg.EXCEL_FILE):
            self._log(f"ERROR: Excel not found at {cfg.EXCEL_FILE}")
            return False
        try:
            self.load_excel(cfg.EXCEL_FILE)
            return True
        except Exception as e:
            self._log(f"ERROR loading Excel: {e}")
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

        from config import MAX_STOCKS_PER_TIME
        if len(symbols) > MAX_STOCKS_PER_TIME:
            self._log(f"Received {len(symbols)} stocks. Max is {MAX_STOCKS_PER_TIME}. Skipping.")
            return []

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
        return parsed

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

        mode = "VIRTUAL" if self.virtual else "LIVE"
        self._log(f"--- PLACING {mode} SELL ORDERS ---")
        for stock in stocks:
            symbol = stock.get("symbol", "UNKNOWN").strip()
            exchange = stock.get("exchange", "NSE")

            try:
                current_ltp, scrip, err = self._get_ltp(symbol, exchange, fresh=True)
                if current_ltp is None:
                    self._log(f"FAILED {symbol}/{exchange}: {err}")
                    continue

                tsym = scrip["tsym"]
                lot = scrip.get("ls", 1)
                notional = current_ltp * lot
                quantity = int(self.trading_cap / notional)
                if quantity <= 0:
                    self._log(
                        f"FAILED {tsym}: 0 lots. Need {notional:,.0f}/lot "
                        f"but cap is {self.trading_cap:,.0f}"
                    )
                    continue

                if self.virtual:
                    order_id = self._open_virtual(scrip, quantity, current_ltp)
                    self._log(
                        f"V-SELL | {scrip['exchange']}:{tsym} | LTP: {current_ltp:.2f} | "
                        f"Lot: {lot} | Lots: {quantity} | Order: {order_id}"
                    )
                else:
                    response = self.api.place_order(
                        buy_or_sell="S",
                        product_type="I",
                        exchange=scrip["exchange"],
                        tradingsymbol=tsym,
                        quantity=quantity,
                        discloseqty=0,
                        price_type="MKT",
                        retention="DAY",
                        remarks="Webhook_Sell",
                    )
                    order_id = response.get("norenordno") if response else None
                    if not order_id:
                        self._log(f"FAILED {tsym}: {response}")
                        continue
                    self._log(
                        f"SELL | {scrip['exchange']}:{tsym} | LTP: {current_ltp:.2f} | "
                        f"Lots: {quantity} | Order: {order_id}"
                    )

                # A freshly opened position must be monitored again even if this
                # symbol was exited earlier today (re-entry support).
                self.processed_stocks.discard(tsym.strip().upper())

                self.on_order({
                    "symbol": tsym,
                    "direction": "SELL",
                    "price": current_ltp,
                    "qty": quantity,
                    "lotsize": lot,
                    "exchange": scrip["exchange"],
                    "order_id": order_id,
                    "virtual": self.virtual,
                })

            except Exception as e:
                self._log(f"ERROR {symbol}: {e}")

    def handle_webhook(self, data):
        self._log("=" * 60)
        self._log(f"WEBHOOK RECEIVED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log("=" * 60)

        try:
            parsed = self.parse_webhook_payload(data)
            filtered = self.filter_stocks(parsed)
            if not filtered:
                self._log("No stocks passed filter")
                return {"status": "no_match"}

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
                    return {"status": "duplicate"}
                self._seen_alerts[key] = datetime.now()

            self.place_sell_orders(filtered)
            return {"status": "success"}
        except Exception as e:
            self._log(f"Webhook error: {e}")
            return {"status": "error", "message": str(e)}

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
