# ==================== FULL PORTABLE BuySell_updated.py ====================

import sys
import io

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding='utf-8',
    line_buffering=True
)

import functools
print = functools.partial(print, flush=True)

import logging
import os
import threading
import time
from datetime import datetime
import pandas as pd
import yaml
import requests

from NorenRestApiPy.NorenApi import NorenApi
from flask import Flask, request

# ==================== BASE PATH ====================

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== LOGIN ====================

class ShoonyaApiPy(NorenApi):

    def __init__(self):

        super().__init__(
            host='https://trade.shoonya.com/NorenWClientWeb/',
            websocket='wss://trade.shoonya.com/NorenWSWeb/'
        )


api = ShoonyaApiPy()
shoonya_ready = False
shoonya_super_token = None

cred_path = os.path.join(
    BASE_DIR,
    "cred.yml"
)

with open(cred_path) as f:

    cred = yaml.load(
        f,
        Loader=yaml.FullLoader
    )

SuperToken = os.getenv("SUPER_TOKEN")

TRADING_CAP_PER_STOCK = int(
    os.getenv(
        "TRADING_CAP_PER_STOCK",
        "1000"
    )
)

userId = cred['user']
Passwrd = cred['pwd']

if SuperToken:
    print("=" * 80)
    print("LOGGING INTO SHOONYA BROKER...")
    print("=" * 80)
    ret = api.set_session(userId, Passwrd, SuperToken)
    if ret:
        shoonya_ready = True
        shoonya_super_token = SuperToken
        print("Login Successful!")
        print(f"User: {userId}")
        print(f"Trading Cap: {TRADING_CAP_PER_STOCK}")
    else:
        print("Login Failed — will retry when /configure is called")
else:
    print("SUPER_TOKEN not set — Shoonya login deferred.")
    print("POST /configure with {\"SUPER_TOKEN\": \"...\"} to login.")

# ==================== FLASK APP ====================

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

processed_stocks = set()

# Crypto paper trade position tracking
paper_position = {
    'open':        False,
    'side':        None,
    'entry_price': 0.0,
    'qty':         0.0,
    'entry_time':  None,
}
paper_pnl_total = 0.0

VALID_TIME_WINDOWS = [
    ("09:45", "10:00"),
    ("10:30", "10:45"),
    ("10:45", "11:00"),
    ("13:00", "13:15")
]

MAX_STOCKS_PER_TIME = 3

excel_file = os.path.join(
    BASE_DIR,
    "NSE_symbols_filtered.xlsx"
)

if not os.path.exists(excel_file):

    print(f"ERROR: Excel file not found at {excel_file}")

    exit()

token_df = pd.read_excel(excel_file)

token_df["TradingSymbol"] = (
    token_df["TradingSymbol"]
    .astype(str)
    .str.strip()
    .str.upper()
)

print(f"Loaded {len(token_df)} symbols from Excel")

# ==================== PNL FUNCTION ====================

def get_total_pnl():

    try:

        ret = api.get_positions()

        shoonya_pnl = 0.0

        if ret:

            mtm = 0
            pnl = 0

            for i in ret:

                mtm += float(i.get('urmtom', 0))
                pnl += float(i.get('rpnl', 0))

            shoonya_pnl = round(mtm + pnl, 2)

    except Exception as e:

        print(f"PnL Fetch Error: {e}")

        shoonya_pnl = 0.0

    global paper_pnl_total

    return shoonya_pnl, paper_pnl_total

# ==================== TIME FILTER ====================

def is_time_in_valid_window(time_str):

    check_time = datetime.strptime(
        time_str,
        "%H:%M"
    ).time()

    for start_str, end_str in VALID_TIME_WINDOWS:

        start_time = datetime.strptime(
            start_str,
            "%H:%M"
        ).time()

        end_time = datetime.strptime(
            end_str,
            "%H:%M"
        ).time()

        if start_time <= check_time <= end_time:
            return True

    return False

# ==================== PARSE WEBHOOK ====================

def parse_webhook_payload(data):

    if not data:
        raise ValueError("Webhook payload is empty")

    # ── Format 1: Paper trade (action + symbol) ────────
    if "action" in data:

        action = str(data.get("action", "")).upper()

        if action not in ("LONG", "SHORT", "LONG_EXIT", "SHORT_EXIT"):
            raise ValueError(f"Invalid action: {action}")

        symbol = data.get("symbol", "").strip()

        if not symbol:
            raise ValueError("Missing symbol")

        price_val = float(data.get("price", 0) or 0)

        return [{
            "symbol": symbol,
            "trigger_price": price_val,
            "time": datetime.now().strftime("%H:%M"),
            "action": action
        }]

    # ── Format 2: Chartink (stocks + trigger_prices) ───
    if "stocks" in data:

        stocks_raw = data.get("stocks", "")
        prices_raw = data.get("trigger_prices", "")
        triggered_at = data.get("triggered_at", "")

        if not stocks_raw or not prices_raw or not triggered_at:
            raise ValueError("Missing required fields")

        symbols = [
            s.strip()
            for s in stocks_raw.split(",")
            if s.strip()
        ]

        prices = [
            p.strip()
            for p in prices_raw.split(",")
            if p.strip()
        ]

        if len(symbols) != len(prices):
            raise ValueError("Stock and price count mismatch")

        trigger_time = datetime.strptime(
            triggered_at.strip().upper(),
            "%I:%M %p"
        ).strftime("%H:%M")

        action = "SELL"

    else:
        # ── Format 3: TradingView ticker ────────────────
        ticker = data.get("ticker") or data.get("symbol") or ""

        if not ticker:
            raise ValueError("Missing ticker/symbol in webhook")

        price_val = data.get("price") or data.get("close") or 0

        if not price_val:
            raise ValueError("Missing price in webhook")

        symbols = [ticker.strip()]
        prices = [str(price_val)]

        triggered_at = data.get("triggered_at", datetime.now().strftime("%I:%M %p"))
        trigger_time = datetime.strptime(
            triggered_at.strip().upper(),
            "%I:%M %p"
        ).strftime("%H:%M")

        action = "SELL"

    parsed_stocks = []

    for symbol, price in zip(symbols, prices):

        parsed_stocks.append({
            "symbol": symbol,
            "trigger_price": float(price),
            "time": trigger_time,
            "action": action
        })

    return parsed_stocks

# ==================== FILTER STOCKS ====================

def filter_stocks(stocks):

    if not stocks:
        return []

    # Action-based signals (paper trade) — skip time filter
    if stocks[0].get("action"):
        return stocks

    if len(stocks) > MAX_STOCKS_PER_TIME:

        print(
            f"Received {len(stocks)} stocks. "
            f"Skipping."
        )

        return []

    for stock in stocks:

        time_value = stock.get('time', '').strip()

        if not is_time_in_valid_window(time_value):

            print(f"Time {time_value} invalid")

            return []

    return stocks

# ==================== PLACE ORDERS ====================

BUY_SELL_MAP = {
    "LONG":       "B",
    "SHORT":      "S",
    "LONG_EXIT":  "S",
    "SHORT_EXIT": "B",
    "SELL":       "S",
}

DELTA_TICKER_URL = 'https://api.india.delta.exchange/v2/tickers/{symbol}'

def get_crypto_price(symbol):
    try:
        url = DELTA_TICKER_URL.format(symbol=symbol)
        r = requests.get(url, timeout=5)
        data = r.json()
        return float(data['result']['mark_price'])
    except Exception as e:
        print(f"Price fetch error for {symbol}: {e}")
        return None

def place_orders(stocks):

    action_label = stocks[0].get("action", "SELL")
    print(f"\nPLACING ORDERS ({action_label})")
    print("-" * 80)

    for stock in stocks:

        action = stock.get("action", "SELL").upper()
        symbol = stock.get('symbol', 'UNKNOWN').strip()

        symbol_eq = f"{symbol}-EQ"

        try:

            match = token_df[
                token_df["TradingSymbol"] ==
                symbol_eq.upper()
            ]

            if match.empty:

                # Crypto / non-NSE symbol → paper trade
                if symbol.upper().endswith("USD"):
                    global paper_position, paper_pnl_total

                    live_price = get_crypto_price(symbol)

                    if action in ("LONG", "SHORT"):
                        if paper_position['open'] and paper_position['side'] == action:
                            print(f"PAPER IGNORED | {action} | {symbol} | already in {action}")
                            continue

                        price = live_price if live_price and live_price > 0 else 0
                        paper_qty = 1
                        if price > 0:
                            paper_qty = max(1, int(TRADING_CAP_PER_STOCK / price))

                        paper_position['open'] = True
                        paper_position['side'] = action
                        paper_position['entry_price'] = price
                        paper_position['qty'] = paper_qty
                        paper_position['entry_time'] = datetime.now().strftime('%H:%M')
                        print(f"PAPER ENTRY | {action} | {symbol} | Price: {price:.2f} | Qty: {paper_qty}")

                    elif action == "LONG_EXIT" and paper_position['open'] and paper_position['side'] == "LONG":
                        price = live_price if live_price and live_price > 0 else 0
                        if price > 0:
                            pnl_change = round((price - paper_position['entry_price']) * paper_position['qty'], 2)
                        else:
                            pnl_change = 0
                        paper_pnl_total += pnl_change
                        paper_position['open'] = False
                        print(f"PAPER EXIT | LONG | {symbol} | Exit: {price:.2f} | PnL: {pnl_change:+0.2f}")

                    elif action == "SHORT_EXIT" and paper_position['open'] and paper_position['side'] == "SHORT":
                        price = live_price if live_price and live_price > 0 else 0
                        if price > 0:
                            pnl_change = round((paper_position['entry_price'] - price) * paper_position['qty'], 2)
                        else:
                            pnl_change = 0
                        paper_pnl_total += pnl_change
                        paper_position['open'] = False
                        print(f"PAPER EXIT | SHORT | {symbol} | Exit: {price:.2f} | PnL: {pnl_change:+0.2f}")

                    else:
                        print(f"PAPER | {action} | {symbol} | (no matching position)")
                else:
                    print(f"FAILED {symbol_eq}: Token not found")

                continue

            token = str(match.iloc[0]["Token"])

            if not shoonya_ready:

                print(f"SKIPPED {symbol_eq}: Shoonya not logged in (POST /configure first)")

                continue

            quote = None
            for retry in range(3):
                try:
                    quote = api.get_quotes(exchange='NSE', token=token)
                    if quote and quote.get("stat") == "Ok":
                        break
                except Exception:
                    pass
                if retry < 2:
                    print(f"Retry {retry+1} for {symbol_eq}...")
                    time.sleep(2)

            if not quote or quote.get("stat") != "Ok":

                print(f"FAILED {symbol_eq}: Quote failed after 3 attempts")

                continue

            current_ltp = float(
                quote.get("lp", 0)
            )

            if current_ltp <= 0:

                print(f"FAILED {symbol_eq}: Invalid price")

                continue

            quantity = int(
                TRADING_CAP_PER_STOCK /
                current_ltp
            )

            buy_or_sell = BUY_SELL_MAP.get(action, "S")
            direction = "BUY" if buy_or_sell == "B" else "SELL"

            response = api.place_order(
                buy_or_sell=buy_or_sell,
                product_type='I',
                exchange='NSE',
                tradingsymbol=symbol_eq,
                quantity=quantity,
                discloseqty=0,
                price_type='MKT',
                retention='DAY',
                remarks=f'Webhook_{action}'
            )

            order_id = response.get('norenordno')

            if order_id:

                print(
                    f"{direction} | {symbol_eq} | "
                    f"Price: {current_ltp:.2f} | "
                    f"Qty: {quantity} | "
                    f"Order ID: {order_id}"
                )

            else:

                print(
                    f"FAILED {symbol_eq}: "
                    f"{response}"
                )

        except Exception as e:

            print(f"ERROR {symbol}: {e}")

# ==================== WEBHOOK ====================

@app.route('/webhook', methods=['POST'])

def webhook_handler():

    try:

        data = request.json

        print("\n" + "=" * 80)

        print(
            f"WEBHOOK RECEIVED - "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print("=" * 80)

        parsed_stocks = parse_webhook_payload(data)

        filtered_stocks = filter_stocks(parsed_stocks)

        if not filtered_stocks:

            print("No stocks passed filter")

            return {
                "status": "no_match"
            }, 200

        place_orders(filtered_stocks)

        return {
            "status": "success"
        }, 200

    except Exception as e:

        print(f"Webhook error: {e}")

        return {
            "status": "error",
            "message": str(e)
        }, 400

# ==================== CONFIGURE ENDPOINT ====================

@app.route('/configure', methods=['POST'])

def configure_handler():

    global shoonya_ready, shoonya_super_token

    try:

        data = request.json

        if not data or not data.get("SUPER_TOKEN"):

            return {
                "status": "error",
                "message": "SUPER_TOKEN required"
            }, 400

        token = data["SUPER_TOKEN"].strip()

        ret = api.set_session(userId, Passwrd, token)

        if ret:

            shoonya_ready = True
            shoonya_super_token = token
            print("Shoonya login via /configure successful!")

            return {
                "status": "success",
                "message": "Shoonya logged in"
            }, 200
        else:

            return {
                "status": "error",
                "message": "Login failed — check SUPER_TOKEN"
            }, 401

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }, 400

# ==================== MONITOR ====================

PNL_LOWER_THRESHOLD = -(
    int(TRADING_CAP_PER_STOCK * 0.006)
)

PNL_UPPER_THRESHOLD = int(
    TRADING_CAP_PER_STOCK * 0.01
)

stop_monitor = False

def monitor_trades():

    global processed_stocks
    global stop_monitor
    global paper_position
    global shoonya_ready

    cycle = 1

    while not stop_monitor:

        print("\n" + "=" * 100)

        print(
            f"MONITOR CYCLE #{cycle} | "
            f"TIME: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print("=" * 100)

        shoonya_pnl, paper_pnl = get_total_pnl()

        print(f"SHOONYA PnL: {shoonya_pnl:>8.2f}  |  PAPER PnL: {paper_pnl:>8.2f}")

        if shoonya_ready:
            print(f"SHOONYA: CONNECTED")
        else:
            print(f"SHOONYA: NOT CONNECTED — POST /configure with SUPER_TOKEN")

        if paper_position['open']:
            print(f"PAPER POSITION: {paper_position['side']} @ {paper_position['entry_price']:.2f} | Qty: {paper_position['qty']} | Since: {paper_position['entry_time']}")
        else:
            print(f"PAPER POSITION: NONE")

        try:

            if not shoonya_ready:

                print("Shoonya not connected — skipping positions fetch")

                time.sleep(5)

                cycle += 1

                continue

            positions = api.get_positions()

            if not positions:

                print("No open positions")

                time.sleep(5)

                cycle += 1

                continue

            df = pd.DataFrame(positions)

            required_cols = [
                'tsym',
                'netqty',
                'urmtom'
            ]

            if not all(
                col in df.columns
                for col in required_cols
            ):

                print("Required columns missing")

                time.sleep(5)

                cycle += 1

                continue

            stock_names = df['tsym'].tolist()

            net_quantities = pd.to_numeric(
                df['netqty'],
                errors='coerce'
            ).fillna(0).astype(int).tolist()

            urmtom_values = pd.to_numeric(
                df['urmtom'],
                errors='coerce'
            ).fillna(0).tolist()

            for i, stock in enumerate(stock_names):

                stock = str(stock).strip().upper()

                qty = net_quantities[i]

                pnl = urmtom_values[i]

                print(
                    f"{stock} | Qty: {qty} | "
                    f"PnL: {pnl}"
                )

                if stock in processed_stocks:
                    continue

                if qty == 0:
                    continue

                if (
                    pnl <= PNL_LOWER_THRESHOLD
                    or pnl >= PNL_UPPER_THRESHOLD
                ):

                    try:

                        response = api.place_order(
                            buy_or_sell='B',
                            product_type='I',
                            exchange='NSE',
                            tradingsymbol=stock,
                            quantity=abs(qty),
                            discloseqty=0,
                            price_type='MKT',
                            retention='DAY',
                            remarks='Exit_Order'
                        )

                        if (
                            response and
                            response.get("norenordno")
                        ):

                            processed_stocks.add(stock)

                            print(
                                f"EXITED {stock}"
                            )

                        else:

                            print(
                                f"EXIT FAILED {stock}"
                            )

                    except Exception as e:

                        print(
                            f"EXIT ERROR {stock}: {e}"
                        )

            print("Cycle Completed")

        except Exception as e:

            print(f"MONITOR ERROR: {e}")

        print("Sleeping 5 sec...")

        time.sleep(5)

        cycle += 1

# ==================== CRYPTO PNL MONITOR (2s) ====================

def crypto_pnl_monitor():

    global paper_position, paper_pnl_total

    while not stop_monitor:

        try:

            if paper_position['open']:

                price = get_crypto_price("SOLUSD")

                if price and price > 0:

                    if paper_position['side'] == "LONG":
                        upnl = round((price - paper_position['entry_price']) * paper_position['qty'], 2)
                    else:
                        upnl = round((paper_position['entry_price'] - price) * paper_position['qty'], 2)

                    total = paper_pnl_total + upnl

                    print(f"CRYPTO_PNL: {total:.2f}")
                    print(f"CRYPTO_POSITION: {paper_position['side']}|{paper_position['entry_price']:.2f}|{paper_position['qty']}")
                else:
                    print(f"CRYPTO_PNL: {paper_pnl_total:.2f}")
            else:
                print(f"CRYPTO_PNL: {paper_pnl_total:.2f}")

        except Exception as e:

            print(f"CRYPTO_PNL_ERROR: {e}")

        time.sleep(2)

# ==================== START ====================

print("\n" + "=" * 80)

print("TRADING SYSTEM STARTED")

print("=" * 80)

monitor_thread = threading.Thread(
    target=monitor_trades,
    daemon=True
)

monitor_thread.start()

print("Monitor thread started")

crypto_thread = threading.Thread(
    target=crypto_pnl_monitor,
    daemon=True
)

crypto_thread.start()

print("Crypto PnL monitor started (2s)")

print("Starting webhook server on port 5000")

app.run(
    host='0.0.0.0',
    port=5000,
    debug=False
)