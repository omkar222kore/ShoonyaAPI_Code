#############################################
#############################################

    #final Working

#############################################
#############################################




# ==================== SIMPLIFIED TRADING SYSTEM ====================

import logging
import os
import threading
import time
from datetime import datetime
import pandas as pd
import pyotp
import yaml
from NorenRestApiPy.NorenApi import NorenApi
from flask import Flask, request


# ==================== LOGIN ====================
class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://trade.shoonya.com/NorenWClientWeb/', 
                        websocket='wss://trade.shoonya.com/NorenWSWeb/')

api = ShoonyaApiPy()

with open('cred.yml') as f:
    cred = yaml.load(f, Loader=yaml.FullLoader)

SuperToken = "5acfc58a589a3623084aca54339906f10ea8c31ae98d6dc4c851f228319ff164"
userId = cred['user']
Passwrd = cred['pwd']

print("=" * 80)
print("🔐 LOGGING INTO SHOONYA BROKER...")
print("=" * 80)

ret = api.set_session(userId, Passwrd, SuperToken)

if ret:
    print("✅ Login Successful!")
    print(f"   User: {userId}")
else:
    print("❌ Login Failed!")
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
TRADING_CAP_PER_STOCK = 20000

# Load token Excel once at startup
excel_file = r"C:\Users\omkar\Downloads\NSE_symbols_filtered.xlsx"
token_df = pd.read_excel(excel_file)
token_df["TradingSymbol"] = token_df["TradingSymbol"].astype(str).str.strip().str.upper()


def is_time_in_valid_window(time_str):
    """Check if time is in valid window"""
    check_time = datetime.strptime(time_str, "%H:%M").time()
    for start_str, end_str in VALID_TIME_WINDOWS:
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        if start_time <= check_time <= end_time:
            return True
    return False


def parse_webhook_payload(data):
    """Parse webhook payload"""
    if not data:
        raise ValueError("Webhook payload is empty")

    stocks_raw = data.get("stocks", "")
    prices_raw = data.get("trigger_prices", "")
    triggered_at = data.get("triggered_at", "")

    if not stocks_raw or not prices_raw or not triggered_at:
        raise ValueError("Missing required fields in webhook")

    symbols = [s.strip() for s in stocks_raw.split(",") if s.strip()]
    prices = [p.strip() for p in prices_raw.split(",") if p.strip()]

    if len(symbols) != len(prices):
        raise ValueError(f"Stocks count and price count mismatch")

    trigger_time = datetime.strptime(triggered_at.strip().upper(), "%I:%M %p").strftime("%H:%M")

    parsed_stocks = []
    for symbol, price in zip(symbols, prices):
        parsed_stocks.append({
            "symbol": symbol,
            "trigger_price": float(price),
            "time": trigger_time,
            "scan_name": data.get("scan_name", ""),
            "scan_url": data.get("scan_url", ""),
            "alert_name": data.get("alert_name", "")
        })

    return parsed_stocks


def filter_stocks(stocks):
    """Filter stocks by time window and count"""
    if not stocks:
        print("⏭️  No stocks received")
        return []

    if len(stocks) > MAX_STOCKS_PER_TIME:
        print(f"⏭️  Received {len(stocks)} stocks (max {MAX_STOCKS_PER_TIME}). Skipping.")
        return []

    for stock in stocks:
        time = stock.get('time', '').strip()
        if not is_time_in_valid_window(time):
            print(f"⏭️  Time {time} not in valid windows. Skipping.")
            return []

    print(f"✅ Filtered {len(stocks)} stocks")
    return stocks


def place_sell_orders(stocks):
    """Place SELL orders immediately for filtered stocks"""
    print(f"\n📥 PLACING SELL ORDERS:")
    print("-" * 80)

    for stock in stocks:
        symbol = stock.get('symbol', 'UNKNOWN').strip()
        symbol_eq = f"{symbol}-EQ"

        try:
            match = token_df[token_df["TradingSymbol"] == symbol_eq.upper()]

            if match.empty:
                print(f"❌ {symbol_eq}: Token not found in Excel")
                continue

            token = str(match.iloc[0]["Token"])

            quote = api.get_quotes(exchange='NSE', token=token)

            if not quote or quote.get("stat") != "Ok":
                print(f"❌ {symbol_eq}: Quote failed - {quote}")
                continue

            current_ltp = float(quote.get("lp", 0))

            if current_ltp <= 0:
                print(f"❌ {symbol_eq}: Invalid price")
                continue

            quantity = int(TRADING_CAP_PER_STOCK / current_ltp)

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
                print(f"✅ SELL | {symbol_eq} | Price: {current_ltp:.2f} | Qty: {quantity} | SL: {current_ltp * 1.006:.2f} | TP: {current_ltp * 0.992:.2f} | Order ID: {order_id}")
            else:
                print(f"❌ {symbol_eq}: Order failed - {response.get('emsg', 'Unknown error')}")

        except Exception as e:
            print(f"❌ {symbol}: {str(e)[:80]}")


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Webhook endpoint"""
    try:
        data = request.json
        print(f"\n{'='*80}")
        print(f"📡 WEBHOOK RECEIVED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        parsed_stocks = parse_webhook_payload(data)
        filtered_stocks = filter_stocks(parsed_stocks)

        if not filtered_stocks:
            print("⏭️  No stocks passed filter")
            return {"status": "no_match", "received": len(parsed_stocks), "filtered": 0}, 200

        place_sell_orders(filtered_stocks)

        return {"status": "success", "received": len(parsed_stocks), "placed": len(filtered_stocks)}, 200

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {"status": "error", "message": str(e)}, 400


tradingCap = 20000
PNL_LOWER_THRESHOLD = -(int(tradingCap * 0.006))
PNL_UPPER_THRESHOLD = int(tradingCap * 0.01)

stop_monitor = False


def monitor_trades():
    """Monitor trades every 30 seconds"""
    global processed_stocks
    global stop_monitor

    while not stop_monitor:
        print("its running")

        try:
            positions = api.get_positions()

            if not positions:
                logging.info("No open positions.")
                time.sleep(30)
                continue

            df = pd.DataFrame(positions)

            required_cols = ['tsym', 'netqty', 'urmtom']

            if not all(col in df.columns for col in required_cols):
                logging.error(f"Invalid positions data. Missing columns. Available: {df.columns.tolist()}")
                time.sleep(30)
                continue

            stock_names = df['tsym'].tolist()
            net_quantities = pd.to_numeric(df['netqty'], errors='coerce').fillna(0).astype(int).tolist()
            urmtom_values = pd.to_numeric(df['urmtom'], errors='coerce').fillna(0).tolist()

            for i, stock in enumerate(stock_names):
                stock = str(stock).strip().upper()

                if stock in processed_stocks:
                    continue

                if net_quantities[i] != 0 and (
                    urmtom_values[i] <= PNL_LOWER_THRESHOLD
                    or urmtom_values[i] >= PNL_UPPER_THRESHOLD
                ):
                    try:
                        response = api.place_order(
                            buy_or_sell='B',
                            product_type='I',
                            exchange='NSE',
                            tradingsymbol=stock,
                            quantity=abs(net_quantities[i]),
                            discloseqty=0,
                            price_type='MKT',
                            retention='DAY',
                            remarks='my_order_001'
                        )

                        if response and response.get("norenordno"):
                            print(
                                f"Buy order placed for {stock}. "
                                f"Qty: {abs(net_quantities[i])} "
                                f"with PnL: {urmtom_values[i]}"
                            )

                            processed_stocks.add(stock)

                            logging.info(
                                f"Buy order placed for {stock}. "
                                f"Qty: {net_quantities[i]}, "
                                f"PnL: {urmtom_values[i]}"
                            )
                        else:
                            logging.error(f"Buy order failed for {stock}. Response: {response}")

                    except Exception as e:
                        logging.error(f"Error placing buy order for {stock}: {e}")

        except Exception as e:
            logging.error(f"Error in monitor_trades: {e}")

        time.sleep(30)


# ==================== START SYSTEM ====================
print("\n" + "="*80)
print("🚀 TRADING SYSTEM STARTED - SIMPLIFIED")
print("="*80)
print("="*80 + "\n")

monitor_thread = threading.Thread(target=monitor_trades, daemon=True)
monitor_thread.start()
print("✅ Monitor thread started")

print("⏳ Starting webhook server on port 5000...")
app.run(host='0.0.0.0', port=5000, debug=False)