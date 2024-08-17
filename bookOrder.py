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
completed_orders = []
Stock_Symbols = []
processed_stocks = []  # New global variable to track processed stocks

def load_global_variables():
    global stocksList, slArray, tgtArray, Stock_Symbols, processed_stocks

    json_file_path = "shared_data.json"
    
    # Clear previous global variables
    stocksList = []
    slArray = []
    tgtArray = []
    Stock_Symbols = []
    
    try:
        with open(json_file_path, 'r', encoding='utf-8-sig') as file:
            data = json.load(file)
            for entry in data:
                # Only load stocks that are not in processed_stocks
                if entry["stock"] not in processed_stocks:
                    stocksList.append(entry["stock"])
                    slArray.append(entry["stop_loss"])
                    tgtArray.append(entry["target"])
                    Stock_Symbols.append(entry["stock"])
                
    except FileNotFoundError:
        print(f"Error: The file {json_file_path} does not exist.")
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")

def book_orders():
    global stocksList, completed_orders, slArray, tgtArray, Stock_Symbols, processed_stocks

    # Load the global variables from the JSON file
    load_global_variables()

    # Print the loaded global variables for debugging
    print(f"stocksList: {stocksList}")
    print(f"slArray: {slArray}")
    print(f"tgtArray: {tgtArray}")

    exchange = 'NSE'
    stocks_to_remove = []

    # Retrieve current positions
    try:
        for i, symbol in enumerate(stocksList):
            if symbol in processed_stocks:
                continue  # Skip already processed stocks

            try:
                # Retrieve quote for the current symbol
                quote = api.get_quotes(exchange=exchange, token=stocksList[i])
                LTP = float(quote["lp"])

                # Print values for debugging
                print(f"Processing symbol: {symbol}")
                print(f"LTP: {LTP}, StopLoss (from JSON): {slArray[i]}, Target (from JSON): {tgtArray[i]}")

                # Check if LTP meets stop-loss or target price criteria directly using values from JSON
                if LTP >= slArray[i] or LTP <= tgtArray[i]:
                    # Debug statement to confirm the block execution
                    print(f"Condition met for symbol: {symbol}. LTP: {LTP}, StopLoss: {slArray[i]}, Target: {tgtArray[i]}")

                    # Place order if conditions are met
                    api.place_order(
                        buy_or_sell='B',
                        product_type='I',
                        exchange=exchange,
                        tradingsymbol=symbol,
                        quantity=int(1000),  # Set a fixed quantity for example
                        discloseqty=0,
                        price_type='MKT',
                        trigger_price=None,
                        retention='DAY',
                        remarks='stop_loss_order'
                    )
                    print(f"Stop loss/target hit for symbol: {symbol} at price: {LTP}")
                    completed_orders.append(symbol)
                    
                    # Mark the stock for removal and add to processed_stocks
                    stocks_to_remove.append(i)
                    processed_stocks.append(symbol)
                        
            except ValueError:
                print(f"ValueError: Symbol {symbol} not found in the list or error in token retrieval.")
            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")

    except Exception as e:
        print(f"An error occurred while retrieving positions or placing orders: {e}")

    # Remove stocks that have been processed from the lists
    for index in reversed(stocks_to_remove):
        stocksList.pop(index)
        slArray.pop(index)
        tgtArray.pop(index)

def run_first_function_every_15_minutes():
    start_time = time.time()
    end_time = start_time + (1.5 * 60 * 60)  # 1 hour 30 minutes from start time
    while time.time() < end_time:
        load_global_variables()
        print("First function executed.")
        time.sleep(15 * 60)  # Sleep for 15 minutes

def run_second_function_every_10_seconds():
    while True:
        book_orders()
        time.sleep(10)  # Sleep for 10 seconds

def main_loop():
    # Start the first function in a separate thread
    first_thread = threading.Thread(target=run_first_function_every_15_minutes)
    first_thread.start()

    # Start the second function in a separate thread
    second_thread = threading.Thread(target=run_second_function_every_10_seconds)
    second_thread.start()

    # Wait for both threads to complete
    first_thread.join()
    second_thread.join()

if __name__ == "__main__":
    main_loop()
