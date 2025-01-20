import csv
from datetime import datetime as dt_datetime, timedelta
import time
import threading
import logging
import pandas as pd
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
from datetime import datetime
import yaml
# from api_helper import ShoonyaApiPy , get_time
import datetime
from dateutil.relativedelta import relativedelta


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')
 
 
 ######## LOGGING PART  ###### 
api=ShoonyaApiPy()
with open('cred.yml') as f:
    cred=yaml.load(f, Loader=yaml.FullLoader)
    # print(cred)

TOKEN=cred['factor2']
otp=pyotp.TOTP(TOKEN).now()
print(otp)
ret = api.login(userid=cred['user'], password=cred['pwd'], twoFA=otp, vendor_code=cred['vc'], api_secret=cred['apikey'], imei=cred['imei'])
print(ret)

if ret!= None:
    print("LogIn Completed")
else:
    print("Error")    




CSV_FILE_PATH = "C:\\Users\\omkar\\Downloads\\Backtest BB_Blast_Sell, Technical Analysis Scanner.csv"
REMOVE_STOCKS = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']
processed_stocks = set()
 
# Logging Configuration
logging.basicConfig(
    filename='D:\\newRepo\\UpdatedCodeFiles\\trading_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
# Global Variables
stocksList = []
slArray = []
tgtArray = []
stock_names = []
rpnl_values = []
quantities = []

def parse_datetime(date_str):
    formats = ["%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M"]
    for fmt in formats:
        try:
            return dt_datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Date parsing error: time data '{date_str}' does not match any of the known formats.")
 
def extract_stock_list_from_csv(csv_file_path, target_datetime_str):
    stock_list = []
    try:
        target_datetime = parse_datetime(target_datetime_str)
        target_date = target_datetime.date()
        target_time = target_datetime.time()
 
        with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    row_datetime = parse_datetime(row['date'])
                except ValueError:
                    continue
 
                if row_datetime.date() == target_date and row_datetime.time() == target_time:
                    stock_list.append(f"{row['symbol']}-EQ")
    except Exception as e:
        logging.error(f"An error occurred while extracting stock list: {e}")
    logging.info(f"Extracted stock list: {stock_list}")
    return stock_list
 
def place_orders(target_datetime_str):
    global stocksList, slArray, tgtArray
 
    stocksList = extract_stock_list_from_csv(CSV_FILE_PATH, target_datetime_str)
    stocksList = [symbol for symbol in stocksList if symbol not in REMOVE_STOCKS]
 
    if len(stocksList) > 3:
        stocksList = []
        logging.info("More than 3 stocks found. No orders will be placed.")
    elif not stocksList:
        slArray = []
        tgtArray = []
        logging.info("No stocks found for the given time. Clearing previous stock lists.")
    else:
        slArray = []
        tgtArray = []
 
        for symbol in stocksList:
            try:
                quote = api.get_quotes(exchange='NSE', token=symbol)
                LTP = float(quote["lp"])
 
                stop_loss = round(LTP * 1.0045, 2)
                target = round(LTP * 0.992, 2)
                Qty_Stock = round(20000 / LTP)
                slArray.append(stop_loss)
                tgtArray.append(target)
 
                logging.info(f"LTP: {LTP}, Stop-Loss: {stop_loss}, Target: {target} for symbol: {symbol}")
 
                api.place_order(
                    buy_or_sell='S', product_type='I', exchange='NSE', tradingsymbol=symbol,
                    quantity=Qty_Stock, discloseqty=0, price_type='MKT', trigger_price=None,
                    retention='DAY', remarks='Place_order'
                )
                logging.info(f"Order placed for symbol: {symbol} (Qty: {Qty_Stock}, Stop-Loss: {stop_loss}, Target: {target})")
 
            except Exception as e:
                logging.error(f"Error occurred for symbol {symbol}: {e}")
 
    logging.info("place_orders function completed.")
 

def place_buy_orders_based_on_positions():
    global stock_names, rpnl_values, quantities, processed_stocks
    logging.debug("Running place_buy_orders_based_on_positions")

    stocks_to_buy = []  # List to keep track of stocks meeting conditions
    positions = api.get_positions()
    df = pd.DataFrame(positions)

    if 'tsym' not in df.columns or 'rpnl' not in df.columns or 'daysellqty' not in df.columns:
        logging.error("No positions data found or data is not in the expected format.")
        return

    stock_names = df['tsym'].dropna().tolist()
    rpnl_values = pd.to_numeric(df['urmtom'], errors='coerce').fillna(float('nan')).tolist()
    quantities = pd.to_numeric(df['daysellqty'], errors='coerce').fillna(0).astype(int).tolist()

    mtm = 0
    pnl = 0
    for i in positions:
        mtm += float(i['urmtom'])
        pnl += float(i['rpnl'])
    day_m2m = mtm + pnl
    print(f'{day_m2m} is your Daily MTM')

    # Get the current time
    current_time = datetime.now().time()

    # Set the time for 3:15 PM
    three_fifteen_time = datetime.strptime("15:15", "%H:%M").time()

    # Check if day_m2m is within the critical range or if the current time is >= 3:15 PM
    if day_m2m <= -500 or day_m2m >= 600 or current_time >= three_fifteen_time:
        for i in range(len(stock_names)):
            if stock_names[i] in processed_stocks:
                continue  # Skip stocks that have already been processed

            try:    
                ret = api.place_order(
                    buy_or_sell='B',
                    product_type='I',
                    exchange='NSE',
                    tradingsymbol=stock_names[i],
                    quantity=quantities[i],
                    discloseqty=0,
                    price_type='MKT',
                    retention='DAY',
                    remarks='my_order_001'
                )
                # Add to processed_stocks only if the order is successfully placed
                processed_stocks.add(stock_names[i])
                stocks_to_buy.append(stock_names[i])
                logging.info(f"Buy order placed for {stock_names[i]}. Quantity: {quantities[i]}, PnL: {rpnl_values[i]}")
            except Exception as e:
                logging.error(f"Error placing buy order for {stock_names[i]}: {e}")

    # If day_m2m didn't trigger bulk orders, check individual stock conditions
    else:
        for i in range(len(stock_names)):
            if stock_names[i] in processed_stocks:
                continue  # Skip stocks that have already been processed

            # Check the PnL conditions
            if rpnl_values[i] is not None and (rpnl_values[i] <= -120 or rpnl_values[i] >= 240):
                try:
                    ret = api.place_order(
                        buy_or_sell='B',
                        product_type='I',
                        exchange='NSE',
                        tradingsymbol=stock_names[i],
                        quantity=quantities[i],
                        discloseqty=0,
                        price_type='MKT',
                        retention='DAY',
                        remarks='my_order_001'
                    )
                    processed_stocks.add(stock_names[i])
                    stocks_to_buy.append(stock_names[i])
                    logging.info(f"Buy order placed for {stock_names[i]}. Quantity: {quantities[i]}, PnL: {rpnl_values[i]}")
                except Exception as e:
                    logging.error(f"Error placing buy order for {stock_names[i]}: {e}")

    if not stocks_to_buy:
        logging.info("No stocks met the conditions for buying.")
    else:
        logging.info(f"Stocks meeting buy conditions: {', '.join(stocks_to_buy)}")

    logging.info("place_buy_orders_based_on_positions function completed.")
    
    
def round_down_to_nearest_15_minutes(dt):
    new_minute = (dt.minute // 15) * 15
    return dt.replace(minute=new_minute, second=0, microsecond=0)
 
def get_previous_timestamp():
    now = dt_datetime.now()
    previous_time = now - timedelta(minutes=0)
    rounded_time = round_down_to_nearest_15_minutes(previous_time)
    return rounded_time.strftime('%d-%m-%Y %I:%M %p')
 
def schedule_place_orders(start_time, end_time):
    current_time = dt_datetime.now()
    next_call_time = dt_datetime.combine(current_time.date(), start_time)
 
    while dt_datetime.now().time() <= end_time:
        now_time = dt_datetime.now()
 
        if now_time >= next_call_time:
            target_datetime_str = get_previous_timestamp()
            logging.info(f"Placing orders for {target_datetime_str} at {now_time.time()}")
            place_orders(target_datetime_str)
 
            next_call_time += timedelta(minutes=15)  # Schedule next call after 15 minutes
        else:
            time.sleep(1)  # Wait until the start time is reached
 
def schedule_place_buy_orders_based_on_positions(start_time, end_time):
    current_time = dt_datetime.now()
    next_call_time = dt_datetime.combine(current_time.date(), start_time)
 
    while dt_datetime.now().time() <= end_time:
        now_time = dt_datetime.now()
 
        if now_time >= next_call_time:
            logging.info(f"Checking positions and placing orders at {now_time.time()}")
            place_buy_orders_based_on_positions()
 
            next_call_time += timedelta(seconds=60)  # Schedule next call after 5 seconds
        else:
            time.sleep(1)  # Wait until the start time is reached
 
if __name__ == "__main__":
    shift = timedelta(seconds=35)
    place_orders_start_time = (dt_datetime.strptime("10:00", "%H:%M") + shift).time()
    place_orders_end_time = (dt_datetime.strptime("11:30", "%H:%M") + shift).time()
    check_positions_start_time = (dt_datetime.strptime("10:02", "%H:%M") + shift).time()
    check_positions_end_time = (dt_datetime.strptime("15:15", "%H:%M") + shift).time()
 
    # Start place_orders function on a separate thread
    place_orders_thread = threading.Thread(target=schedule_place_orders, args=(place_orders_start_time, place_orders_end_time))
    place_orders_thread.start()
 
    # Start place_buy_orders_based_on_positions function on another thread
    place_buy_orders_thread = threading.Thread(target=schedule_place_buy_orders_based_on_positions, args=(check_positions_start_time, check_positions_end_time))
    place_buy_orders_thread.start()
 
    place_orders_thread.join()
    place_buy_orders_thread.join()