import csv
from datetime import datetime as dt_datetime, timedelta
import time
import threading
import logging
import pandas as pd
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
import yaml


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')


# Initialize API
api = ShoonyaApiPy()
with open('cred.yml') as f:
    cred = yaml.load(f, Loader=yaml.FullLoader)

TOKEN = cred['factor2']
otp = pyotp.TOTP(TOKEN).now()
ret = api.login(
    userid=cred['user'],
    password=cred['pwd'],
    twoFA=otp,
    vendor_code=cred['vc'],
    api_secret=cred['apikey'],
    imei=cred['imei']
)

if ret:
    print("Login Successful")
else:
    print("Login Failed")
    exit()

# File and Logging Configuration
CSV_FILE_PATH = "C:\\Users\\omkar\\Downloads\\Backtest BB_Blast_Sell, Technical Analysis Scanner.csv"
REMOVE_STOCKS = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']
PNL_LOWER_THRESHOLD = -50
PNL_UPPER_THRESHOLD = 50

logging.basicConfig(
    filename='D:\\AlgoRepo\\ShoonyaAPI_Code\\trading_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)

# Global Variables
stocksList = []
slArray = []
tgtArray = []
processed_stocks = set()  # Track processed stocks


# Helper Functions
def parse_datetime(date_str):
    formats = ["%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M"]
    for fmt in formats:
        try:
            return dt_datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Date parsing error: time data '{date_str}' does not match any of the known formats.")


def round_down_to_nearest_15_minutes(dt):
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)


def get_previous_timestamp():
    now = dt_datetime.now() - timedelta(minutes=0)
    return round_down_to_nearest_15_minutes(now).strftime('%d-%m-%Y %I:%M %p')


# Core Functions
def extract_stock_list_from_csv(csv_file_path, target_datetime_str):
    stock_list = []
    try:
        target_datetime = parse_datetime(target_datetime_str)
        with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    row_datetime = parse_datetime(row['date'])
                except ValueError:
                    continue
                if row_datetime == target_datetime:
                    stock_list.append(f"{row['symbol']}-EQ")
    except Exception as e:
        logging.error(f"Error extracting stock list: {e}")
    logging.info(f"Extracted stock list: {stock_list}")
    return stock_list


def place_orders(target_datetime_str):
    global stocksList, slArray, tgtArray

    stocksList = extract_stock_list_from_csv(CSV_FILE_PATH, target_datetime_str)
    stocksList = [symbol for symbol in stocksList if symbol not in REMOVE_STOCKS]

    if len(stocksList) > 2:
        stocksList = []
        slArray = []
        tgtArray = []
        logging.info("More than 3 stocks found. Clearing stock list.")
    elif not stocksList:
        slArray = []
        tgtArray = []
        logging.info("No stocks found. Clearing stock list.")
    else:
        slArray = []
        tgtArray = []
        for symbol in stocksList:
            try:
                quote = api.get_quotes(exchange='NSE', token=symbol)
                LTP = float(quote["lp"])

                stop_loss = round(LTP * 1.0045, 2)
                target = round(LTP * 0.992, 2)
                quantity = round(20000 / LTP)

                slArray.append(stop_loss)
                tgtArray.append(target)

                api.place_order(
                    buy_or_sell='S',
                    product_type='I',
                    exchange='NSE',
                    tradingsymbol=symbol,
                    quantity=quantity,
                    discloseqty=0,
                    price_type='MKT',
                    retention='DAY',
                    remarks='Place_order'
                )
                logging.info(f"Order placed for {symbol}. Qty: {quantity}, Stop-Loss: {stop_loss}, Target: {target}")
            except Exception as e:
                logging.error(f"Error placing order for {symbol}: {e}")


def place_buy_orders_based_on_positions():
    global processed_stocks

    try:
        positions = api.get_positions()
        if not positions:
            logging.info("No open positions.")
            return

        df = pd.DataFrame(positions)
        if 'tsym' not in df.columns or 'rpnl' not in df.columns or 'daysellqty' not in df.columns:
            logging.error("Invalid positions data.")
            return

        stock_names = df['tsym'].tolist()
        net_quantities = pd.to_numeric(df['netqty'], errors='coerce').fillna(0).astype(int).tolist()
        urmtom_values = pd.to_numeric(df['urmtom'], errors='coerce').fillna(0).tolist()
        
        
        for i, stock in enumerate(stock_names):
            if urmtom_values[i] <= PNL_LOWER_THRESHOLD or urmtom_values[i] >= PNL_UPPER_THRESHOLD and net_quantities[i]!=0:
                try:
                    api.place_order(
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
                    processed_stocks.add(stock)
                    logging.info(f"Buy order placed for {stock}. Qty: {net_quantities[i]}, PnL: {rpnl_values[i]}")
                except Exception as e:
                    logging.error(f"Error placing buy order for {stock}: {e}")
    except Exception as e:
        logging.error(f"Error in place_buy_orders_based_on_positions: {e}")


# Scheduling Functions
def schedule_place_orders():
    specific_times = ["09:46:55", "10:01:55", "10:46:55"]
    end_time = dt_datetime.combine(dt_datetime.now().date(), dt_datetime.strptime("15:15:00", "%H:%M:%S").time())

    while True:
        now = dt_datetime.now()
        if now >= end_time:
            logging.info("Stopping schedule_place_orders as it is past 3:15 PM.")
            break

        for target_time in specific_times:
            target_datetime = dt_datetime.combine(now.date(), dt_datetime.strptime(target_time, "%H:%M:%S").time())
            if now < target_datetime:
                sleep_duration = (target_datetime - now).total_seconds()
                time.sleep(sleep_duration)
                place_orders(get_previous_timestamp())


def schedule_place_buy_orders_based_on_positions():
    start_time = dt_datetime.combine(dt_datetime.now().date(), dt_datetime.strptime("09:50:00", "%H:%M:%S").time())
    end_time = dt_datetime.combine(dt_datetime.now().date(), dt_datetime.strptime("15:15:00", "%H:%M:%S").time())

    now = dt_datetime.now()
    if now < start_time:
        sleep_duration = (start_time - now).total_seconds()
        time.sleep(sleep_duration)

    while True:
        now = dt_datetime.now()
        if now >= end_time:
            logging.info("Stopping schedule_place_buy_orders_based_on_positions as it is past 3:15 PM.")
            break

        place_buy_orders_based_on_positions()
        time.sleep(30)  # Run every minute


# Main Execution
if __name__ == "__main__":
    threading.Thread(target=schedule_place_orders).start()
    threading.Thread(target=schedule_place_buy_orders_based_on_positions).start()
