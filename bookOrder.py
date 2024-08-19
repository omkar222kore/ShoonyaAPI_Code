import os
import json
from datetime import datetime as dt_datetime
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
import time
import threading

class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')

api = ShoonyaApiPy()
user = 'FA74468'
pwd = 'GURU222kore$'
token = 'XT2L66VT73Q22P33BNCHKN6WA2Q37KK6'
factor2 = pyotp.TOTP(token).now()
vc = 'FA74468_U'
app_key = 'c98e82a190da8181c80fb94cf0a31144'
imei = 'abc1234'

api.login(userid=user, password=pwd, twoFA=factor2, vendor_code=vc, api_secret=app_key, imei=imei)

# Global variables
stocksList = []
slArray = []
tgtArray = []
qtyArray = []
completed_orders = []
Stock_Symbols = []
processed_stocks = []
exit_flag = threading.Event()  # Flag to signal graceful shutdown

def load_global_variables():
    global stocksList, slArray, tgtArray, qtyArray, Stock_Symbols, processed_stocks

    json_file_path = "D:\\AA_trading_Algos\\ShoonyaAPI_Code\\shared_data.json"
   
    # Clear previous global variables
    stocksList = []
    slArray = []
    tgtArray = []
    qtyArray = []
    Stock_Symbols = []

    try:
        with open(json_file_path, 'r', encoding='utf-8-sig') as file:
            data = json.load(file)
            for entry in data:
                required_keys = ['stock', 'stop_loss', 'target', 'quantity']
                if all(key in entry for key in required_keys):
                    if entry['stock'] not in processed_stocks:
                        stocksList.append(entry['stock'])
                        slArray.append(entry['stop_loss'])
                        tgtArray.append(entry['target'])
                        qtyArray.append(entry['quantity'])  # Quantity is taken from the JSON file
                        Stock_Symbols.append(entry['stock'])
                else:
                    missing_keys = [key for key in required_keys if key not in entry]
                    print(f"Error: Missing keys {missing_keys} in one of the entries.")
    except FileNotFoundError:
        print(f"Error: The file {json_file_path} does not exist.")
    except json.JSONDecodeError:
        print("Error: JSON file is not correctly formatted.")
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")

def book_orders():
    global stocksList, completed_orders, slArray, tgtArray, qtyArray, Stock_Symbols, processed_stocks, exit_flag

    load_global_variables()

    print(f"stocksList: {stocksList}")
    print(f"slArray: {slArray}")
    print(f"tgtArray: {tgtArray}")
    print(f"qtyArray: {qtyArray}")

    exchange = 'NSE'

    try:
        for i, symbol in enumerate(stocksList):
            if symbol in processed_stocks:
                continue

            try:
                quote = api.get_quotes(exchange=exchange, token=symbol)
                LTP = float(quote["lp"])

                print(f"Processing symbol: {symbol}")
                print(f"LTP: {LTP}, StopLoss: {slArray[i]}, Target: {tgtArray[i]}")

                if LTP >= slArray[i] or LTP <= tgtArray[i]:
                    print(f"Condition met for symbol: {symbol}. LTP: {LTP}, StopLoss: {slArray[i]}, Target: {tgtArray[i]}")

                    api.place_order(
                        buy_or_sell='B',
                        product_type='I',
                        exchange=exchange,
                        tradingsymbol=symbol,
                        quantity=qtyArray[i],
                        discloseqty=0,
                        price_type='MKT',
                        trigger_price=None,
                        retention='DAY',
                        remarks='stop_loss_order'
                    )
                    print(f"Stop loss/target hit for symbol: {symbol} at price: {LTP}")
                    completed_orders.append(symbol)
                    processed_stocks.append(symbol)
                       
            except ValueError:
                print(f"ValueError: Symbol {symbol} not found in the list or error in token retrieval.")
            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")

    except Exception as e:
        print(f"An error occurred while retrieving positions or placing orders: {e}")

    # Check if all orders are completed
    if not stocksList:
        print("All orders are completed. Exiting the script.")
        exit_flag.set()  # Signal the threads to exit

def run_first_function_every_15_minutes():
    start_time = time.time()
    end_time = start_time + (1.5 * 60 * 60)
    while time.time() < end_time:
        load_global_variables()
        print("First function executed.")
        time.sleep(15 * 60)
        if exit_flag.is_set():
            break  # Exit if shutdown is signaled

def run_second_function_every_10_seconds():
    while True:
        book_orders()
        time.sleep(10)
        if exit_flag.is_set():
            break  # Exit if shutdown is signaled

def main_loop():
    first_thread = threading.Thread(target=run_first_function_every_15_minutes)
    second_thread = threading.Thread(target=run_second_function_every_10_seconds)
   
    first_thread.start()
    second_thread.start()
   
    first_thread.join()
    second_thread.join()

if __name__ == "__main__":
    main_loop()
