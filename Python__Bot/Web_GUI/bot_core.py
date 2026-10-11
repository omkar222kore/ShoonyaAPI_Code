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

        import config as cfg
        self.eod_time = cfg.EOD_SQUARE_OFF
        self._eod_done = False
        self._sq_off_requested = False

        self.on_log = on_log or (lambda *a, **k: None)
        self.on_pnl = on_pnl or (lambda *a, **k: None)
        self.on_positions = on_positions or (lambda *a, **k: None)
        self.on_status = on_status or (lambda *a, **k: None)
        self.on_order = on_order or (lambda *a, **k: None)
        self.on_closed_trade = on_closed_trade or (lambda *a, **k: None)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.on_log(f"[{ts}] {msg}")

    def _record_closed(self, row):
        """Keep the last 50 closes in memory, newest first, and notify UI."""
        self.closed_trades.insert(0, row)
        del self.closed_trades[50:]
        try:
            self.on_closed_trade(row)
        except Exception:
            pass

    # ── Market data ──────────────────────────────────────────

    def _quote(self, exchange, token):
        """Read-only LTP fetch. Safe in both virtual and live mode."""
        try:
            q = self.api.get_quotes(exchange=exchange, token=token)
        except Exception as e:
            return None, f"Quote error: {e}"
        if not q or q.get("stat") != "Ok":
            return None, "Quote failed"
        ltp = float(q.get("lp", 0) or 0)
        if ltp <= 0:
            return None, "Invalid price"
        return ltp, None

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

    def _get_ltp(self, symbol, exchange="NSE"):
        """Returns (ltp, scrip, err). scrip is None when resolution fails."""
        sc = self._resolve_scrip(symbol, exchange)
        if not sc:
            return None, None, f"Symbol not found: {symbol}/{exchange}"
        ltp, err = self._quote(sc["exchange"], sc["token"])
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

    def login(self, super_token, trading_cap):
        import config as cfg
        try:
            if not os.path.exists(cfg.BROKER_CRED):
                self._log(f"ERROR: cred.yml not found at {cfg.BROKER_CRED}")
                self.on_status("LOGIN_FAILED")
                return False
            with open(cfg.BROKER_CRED) as f:
                cred = yaml.load(f, Loader=yaml.FullLoader)
            self.userId = cred["user"]
            password = cred["pwd"]
        except Exception as e:
            self._log(f"ERROR loading cred.yml: {e}")
            self.on_status("LOGIN_FAILED")
            return False
        self.super_token = super_token
        self.trading_cap = trading_cap

        try:
            self._log("Logging into Shoonya broker...")
            self.api = ShoonyaApiPy()
            ret = self.api.set_session(self.userId, password, super_token)
        except Exception as e:
            self._log(f"Login ERROR: {e}")
            self.on_status("LOGIN_FAILED")
            return False

        if ret:
            self._log(f"Login successful | User: {self.userId} | Capital: {self.trading_cap}")
            self.on_status("CONNECTED")
            return True
        else:
            self._log("Login FAILED")
            self.on_status("LOGIN_FAILED")
            return False

    def start(self, super_token, trading_cap, virtual=True):
        if self.running:
            self._log("Bot already running")
            return False

        self._eod_done = False
        self._sq_off_requested = False
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
            positions = self.get_positions()
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

        self.on_positions([])
        self.on_pnl(self.get_total_pnl())
        self._log(
            f"SQUARE-OFF ({reason}) complete | Closed {closed}/{len(open_pos)} "
            f"| Realised PnL: {round(self.realized_pnl, 2)}"
        )
        return closed

    def is_time_in_valid_window(self, time_str):
        from config import VALID_TIME_WINDOWS
        check_time = datetime.strptime(time_str, "%H:%M").time()
        for start_str, end_str in VALID_TIME_WINDOWS:
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            if start_time <= check_time <= end_time:
                return True
        return False

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
            if not self.is_time_in_valid_window(time_value):
                self._log(f"Time {time_value} not in valid window")
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
                current_ltp, scrip, err = self._get_ltp(symbol, exchange)
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
            self.place_sell_orders(filtered)
            return {"status": "success"}
        except Exception as e:
            self._log(f"Webhook error: {e}")
            return {"status": "error", "message": str(e)}

    def get_total_pnl(self):
        if self.virtual:
            open_pnl = sum(p["urmtom"] for p in self._virtual_view())
            return round(open_pnl + self.realized_pnl, 2)
        try:
            ret = self.api.get_positions()
            if not ret:
                return 0.0
            mtm = sum(float(i.get("urmtom", 0)) for i in ret)
            pnl = sum(float(i.get("rpnl", 0)) for i in ret)
            return round(mtm + pnl, 2)
        except Exception as e:
            self._log(f"PnL Fetch Error: {e}")
            return 0.0

    def get_positions(self):
        if self.virtual:
            return self._virtual_view()
        try:
            return self.api.get_positions() or []
        except:
            return []

    def _lookup_live_exit(self, sym):
        """Return (entry_price, exit_price, pnl) for a live position.

        Read immediately before the exit order so the journal matches
        what the broker actually reports at that moment.
        """
        try:
            for p in self.get_positions():
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

        response = self.api.place_order(
            buy_or_sell="B",
            product_type="I",
            exchange=exchange,
            tradingsymbol=sym,
            quantity=abs(qty),
            discloseqty=0,
            price_type="MKT",
            retention="DAY",
            remarks="Exit_Order",
        )
        if response and response.get("norenordno"):
            order_id = response["norenordno"]
            self._log(f"EXITED {sym}")
            self.on_order({
                "symbol": sym, "direction": "BUY", "qty": abs(qty),
                "order_id": order_id, "type": "EXIT",
                "exchange": exchange,
            })
            self._log_trades([{
                "symbol": sym, "exchange": exchange, "side": side,
                "qty": abs(qty), "entry": entry, "exit": exit_px,
                "pnl": urmtom,
            }], order_id, reason)
            return True
        self._log(f"EXIT FAILED {sym}")
        return False

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
                            MONITOR_INTERVAL, POSITION_LOG_EVERY)
        cycle = 1
        while not self._stop_event.is_set():
            total_pnl = self.get_total_pnl()
            self.on_pnl(total_pnl)

            try:
                positions = self.get_positions()

                squared = False
                if self._sq_off_requested:
                    self._sq_off_requested = False
                    self.square_off("MANUAL")
                    squared = True

                if self._eod_reached() and not self._eod_done:
                    self._eod_done = True
                    if not squared:
                        self.square_off(f"EOD {self.eod_time}")
                    self._log(f"EOD {self.eod_time} reached - stopping bot")
                    self.stop()
                    break

                if squared:
                    positions = self.get_positions()

                if not positions:
                    self.on_positions([])
                    self._log(
                        f"Cycle #{cycle} | {'VIRTUAL' if self.virtual else 'LIVE'}"
                        f" | Pos: 0 | PnL: {total_pnl}"
                    )
                    self._stop_event.wait(MONITOR_INTERVAL)
                    cycle += 1
                    continue

                detail = (cycle == 1) or (cycle % POSITION_LOG_EVERY == 0)
                pos_list = []
                exited = set()

                for p in positions:
                    sym = str(p.get("tsym", "")).strip().upper()
                    exch = str(p.get("exchange") or p.get("exch") or "NSE")
                    lot = int(p.get("lotsize", 1) or 1)
                    qty = int(float(p.get("netqty", 0)))
                    urmtom = float(p.get("urmtom", 0))
                    pos_list.append({"symbol": sym, "qty": qty, "pnl": urmtom})
                    if detail:
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
                    positions = self.get_positions()
                    pos_list = self._pos_snapshot(positions)
                    total_pnl = self.get_total_pnl()
                    self.on_pnl(total_pnl)

                self.on_positions(pos_list)
                self._log(
                    f"Cycle #{cycle} | {'VIRTUAL' if self.virtual else 'LIVE'}"
                    f" | Pos: {len(pos_list)} | PnL: {total_pnl}"
                )

            except Exception as e:
                self._log(f"MONITOR ERROR: {e}")

            self._stop_event.wait(MONITOR_INTERVAL)
            cycle += 1
