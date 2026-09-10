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

if not SuperToken:
    raise Exception("SuperToken missing")

TRADING_CAP_PER_STOCK = int(
    os.getenv(
        "TRADING_CAP_PER_STOCK",
        "1000"
    )
)

userId = cred['user']
Passwrd = cred['pwd']

print("=" * 80)
print("LOGGING INTO SHOONYA BROKER...")
print("=" * 80)

ret = api.set_session(
    userId,
    Passwrd,
    SuperToken
)

if ret:

    print("Login Successful!")
    print(f"User: {userId}")
    print(f"Trading Cap: {TRADING_CAP_PER_STOCK}")

else:

    print("Login Failed!")
    exit()

# ==================== FLASK APP ====================

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

processed_stocks = set()

VALID_TIME_WINDOWS = [
    ("09:45", "10:00"),
    ("10:15", "10:30"),
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

        if not ret:
            return 0.0

        mtm = 0
        pnl = 0

        for i in ret:

            mtm += float(i.get('urmtom', 0))
            pnl += float(i.get('rpnl', 0))

        day_m2m = mtm + pnl

        return round(day_m2m, 2)

    except Exception as e:

        print(f"PnL Fetch Error: {e}")

        return 0.0

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

    parsed_stocks = []

    for symbol, price in zip(symbols, prices):

        parsed_stocks.append({
            "symbol": symbol,
            "trigger_price": float(price),
            "time": trigger_time
        })

    return parsed_stocks

# ==================== FILTER STOCKS ====================

def filter_stocks(stocks):

    if not stocks:
        return []

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

# ==================== PLACE SELL ORDERS ====================

def place_sell_orders(stocks):

    print("\nPLACING SELL ORDERS")
    print("-" * 80)

    for stock in stocks:

        symbol = stock.get('symbol', 'UNKNOWN').strip()

        symbol_eq = f"{symbol}-EQ"

        try:

            match = token_df[
                token_df["TradingSymbol"] ==
                symbol_eq.upper()
            ]

            if match.empty:

                print(f"FAILED {symbol_eq}: Token not found")

                continue

            token = str(match.iloc[0]["Token"])

            quote = api.get_quotes(
                exchange='NSE',
                token=token
            )

            if not quote or quote.get("stat") != "Ok":

                print(f"FAILED {symbol_eq}: Quote failed")

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

            response = api.place_order(
                buy_or_sell='S',
                product_type='I',
                exchange='NSE',
                tradingsymbol=symbol_eq,
                quantity=quantity,
                discloseqty=0,
                price_type='MKT',
                retention='DAY',
                remarks='Webhook_Sell'
            )

            order_id = response.get('norenordno')

            if order_id:

                print(
                    f"SELL | {symbol_eq} | "
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

        place_sell_orders(filtered_stocks)

        return {
            "status": "success"
        }, 200

    except Exception as e:

        print(f"Webhook error: {e}")

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

    cycle = 1

    while not stop_monitor:

        print("\n" + "=" * 100)

        print(
            f"MONITOR CYCLE #{cycle} | "
            f"TIME: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print("=" * 100)

        total_pnl = get_total_pnl()

        print(f"TOTAL_PNL: {total_pnl}")

        try:

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

print("Starting webhook server on port 5000")

app.run(
    host='0.0.0.0',
    port=5000,
    debug=False
)