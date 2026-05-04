# ==================== SIMPLIFIED TRADING SYSTEM ====================

import csv
import json
import logging
import os
import threading
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import pyotp
import yaml
from NorenRestApiPy.NorenApi import NorenApi
from flask import Flask, request


# ==================== EXECUTION SETUP ====================
execution_folder = r'D:\AlgoRepo\ShoonyaAPI_Code\Testing_Use\Execution'
os.makedirs(execution_folder, exist_ok=True)

class ExecutionLogger:
    """Execution logging class"""
    def __init__(self, folder_path):
        self.folder = folder_path
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_file = os.path.join(folder_path, f'session_{self.session_id}.json')
        self.trades_log = []
        self.webhooks_log = []
        
    def log_webhook(self, webhook_data, filtered_count, parsed_stocks=None):
        """Log incoming webhook"""
        parsed_stocks = parsed_stocks or []
        entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'scan_name': webhook_data.get('scan_name', ''),
            'alert_name': webhook_data.get('alert_name', ''),
            'triggered_at': webhook_data.get('triggered_at', ''),
            'total_stocks': len(parsed_stocks),
            'filtered_stocks': filtered_count,
            'stocks': parsed_stocks,
            'raw_payload': webhook_data
        }
        self.webhooks_log.append(entry)
        self._save()
            
    def log_trade(self, symbol, order_id, entry_price, quantity, sl, tp):
        """Log new trade"""
        entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'order_id': order_id,
            'entry_price': entry_price,
            'quantity': quantity,
            'sl_price': sl,
            'tp_price': tp,
            'status': 'ACTIVE'
        }
        self.trades_log.append(entry)
        self._save()
        
    def log_exit(self, order_id, exit_price, exit_reason):
        """Log trade exit"""
        for trade in self.trades_log:
            if trade['order_id'] == order_id:
                trade['status'] = 'CLOSED'
                trade['exit_price'] = exit_price
                trade['exit_reason'] = exit_reason
                trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                trade['pnl'] = (trade['entry_price'] - exit_price) * trade['quantity']
                self._save()
                break
    
    def _save(self):
        """Save logs to JSON"""
        data = {
            'session_id': self.session_id,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'webhooks': self.webhooks_log,
            'trades': self.trades_log
        }
        with open(self.session_file, 'w') as f:
            json.dump(data, f, indent=2)


# Initialize logger
logger = ExecutionLogger(execution_folder)

# ==================== LOGIN ====================
class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://trade.shoonya.com/NorenWClientWeb/', 
                        websocket='wss://trade.shoonya.com/NorenWSWeb/')

api = ShoonyaApiPy()

with open('cred.yml') as f:
    cred = yaml.load(f, Loader=yaml.FullLoader)

SuperToken = "5ddcb928a35c7f1e240427e652039b2700b5d972759e11827b7cfb88ce88735a"
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

active_trades = {}
lock = threading.Lock()

VALID_TIME_WINDOWS = [
    ("09:45", "10:00"),
    ("10:15", "10:30"),
    ("10:30", "10:45"),
    ("10:45", "11:00"),
    ("13:00", "13:15")
]

MAX_STOCKS_PER_TIME = 3
TRADING_CAP_PER_STOCK = 20000


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
        entry_time = stock.get('time', '')
        symbol_eq = f"{symbol}-EQ"
        
        try:
            # Get current price
            quote = api.get_quotes(exchange='NSE', token=symbol_eq)
            current_ltp = float(quote.get("lp", 0))
            
            if current_ltp <= 0:
                print(f"❌ {symbol_eq}: Invalid price")
                continue
            
            quantity = int(TRADING_CAP_PER_STOCK / current_ltp)
            
            # Place SELL order
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
                sl_price = current_ltp * 1.006
                tp_price = current_ltp * 0.992
                
                with lock:
                    active_trades[order_id] = {
                        'symbol': symbol_eq,
                        'entry_time': entry_time,
                        'entry_price': current_ltp,
                        'quantity': quantity,
                        'status': 'ACTIVE',
                        'order_id': order_id,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'placed_at': datetime.now()
                    }
                
                logger.log_trade(symbol_eq, order_id, current_ltp, quantity, sl_price, tp_price)
                
                print(f"✅ {symbol_eq} | SELL @ {current_ltp:.2f} | Qty: {quantity}")
                print(f"   Order ID: {order_id} | TP: {tp_price:.2f} | SL: {sl_price:.2f}")
            else:
                print(f"❌ {symbol_eq}: Order failed - {response.get('emsg', 'Unknown error')}")
        
        except Exception as e:
            print(f"❌ {symbol}: {str(e)[:50]}")


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Webhook endpoint"""
    try:
        data = request.json
        print(f"\n{'='*80}")
        print(f"📡 WEBHOOK RECEIVED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        parsed_stocks = parse_webhook_payload(data)
        logger.log_webhook(data, 0, parsed_stocks)

        filtered_stocks = filter_stocks(parsed_stocks)
        logger.webhooks_log[-1]['filtered_stocks'] = len(filtered_stocks)
        logger._save()

        if not filtered_stocks:
            print("⏭️  No stocks passed filter")
            return {"status": "no_match", "received": len(parsed_stocks), "filtered": 0}, 200

        place_sell_orders(filtered_stocks)

        return {"status": "success", "received": len(parsed_stocks), "placed": len(filtered_stocks)}, 200

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {"status": "error", "message": str(e)}, 400


def monitor_trades():
    """Monitor trades every 30 seconds"""
    iteration = 0
    
    while True:
        try:
            iteration += 1
            
            with lock:
                if not active_trades:
                    print(f"⏳ [{iteration}] Waiting for trades...")
                    time.sleep(30)
                    continue
                
                print(f"\n{'='*80}")
                print(f"📊 MONITOR CHECK #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Active trades: {len(active_trades)}")
                print('='*80)
                
                closed_orders = []
                
                for order_id, trade in list(active_trades.items()):
                    if trade['status'] != 'ACTIVE':
                        continue
                    
                    symbol = trade['symbol']
                    entry_price = trade['entry_price']
                    quantity = trade['quantity']
                    sl_price = trade['sl_price']
                    tp_price = trade['tp_price']
                    
                    try:
                        quote = api.get_quotes(exchange='NSE', token=symbol)
                        current_ltp = float(quote.get("lp", entry_price))
                        
                        print(f"\n{symbol} | Entry: {entry_price:.2f} | Current: {current_ltp:.2f}")
                        print(f"  TP: {tp_price:.2f} | SL: {sl_price:.2f}")
                        
                        # Check TP hit
                        if current_ltp <= tp_price:
                            print(f"✅ TP HIT! Closing...")
                            close_response = api.place_order(
                                buy_or_sell='B',
                                product_type='I',
                                exchange='NSE',
                                tradingsymbol=symbol,
                                quantity=quantity,
                                discloseqty=0,
                                price_type='MKT',
                                retention='DAY',
                                remarks='Close_TP'
                            )
                            
                            if close_response.get('norenordno'):
                                pnl = (entry_price - current_ltp) * quantity
                                print(f"💰 P&L: {pnl:.2f}")
                                trade['status'] = 'CLOSED_TP'
                                logger.log_exit(order_id, current_ltp, 'TP_HIT')
                                closed_orders.append(order_id)
                        
                        # Check SL hit
                        elif current_ltp >= sl_price:
                            print(f"❌ SL HIT! Closing...")
                            close_response = api.place_order(
                                buy_or_sell='B',
                                product_type='I',
                                exchange='NSE',
                                tradingsymbol=symbol,
                                quantity=quantity,
                                discloseqty=0,
                                price_type='MKT',
                                retention='DAY',
                                remarks='Close_SL'
                            )
                            
                            if close_response.get('norenordno'):
                                pnl = (entry_price - current_ltp) * quantity
                                print(f"💔 P&L: {pnl:.2f}")
                                trade['status'] = 'CLOSED_SL'
                                logger.log_exit(order_id, current_ltp, 'SL_HIT')
                                closed_orders.append(order_id)
                        else:
                            pnl = (entry_price - current_ltp) * quantity
                            print(f"📈 P&L: {pnl:.2f}")
                    
                    except Exception as e:
                        print(f"⚠️  Error checking {symbol}: {str(e)[:50]}")
                
                for order_id in closed_orders:
                    del active_trades[order_id]
            
            time.sleep(30)
        
        except Exception as e:
            print(f"❌ Monitor error: {e}")
            time.sleep(30)


# ==================== START SYSTEM ====================
print("\n" + "="*80)
print("🚀 TRADING SYSTEM STARTED - SIMPLIFIED")
print("="*80)
print(f"📝 Session ID: {logger.session_id}")
print(f"📋 Log file: {logger.session_file}")
print("="*80 + "\n")

monitor_thread = threading.Thread(target=monitor_trades, daemon=True)
monitor_thread.start()
print("✅ Monitor thread started")

print("⏳ Starting webhook server on port 5000...")
app.run(host='0.0.0.0', port=5000, debug=False)