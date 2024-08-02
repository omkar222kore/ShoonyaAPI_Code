import os
import csv
from datetime import datetime as dt_datetime
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
import time

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
PlaceQtyForEachStockArray = []
slArray = []
completed_orders = []
all_orders_completed = False
Stock_Symbols = []
Stock_Tokens = []

def load_global_variables():
    global stocksList, PlaceQtyForEachStockArray, slArray, Stock_Symbols, Stock_Tokens

    file_path = "E:\\Z_algo_Script\\shared_data.csv"
    
    # Clear previous global variables
    stocksList = []
    PlaceQtyForEachStockArray = []
    slArray = []
    Stock_Symbols = []
    Stock_Tokens = []
    
    try:
        with open(file_path, mode='r', newline='', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader)  # Skip header row
            for row in reader:
                if len(row) == 3:
                    stocksList.append(row[0])
                    PlaceQtyForEachStockArray.append(int(row[1]))
                    slArray.append(float(row[2]))
                elif len(row) == 2:
                    Stock_Symbols.append(row[0])
                    Stock_Tokens.append(row[1])
    except FileNotFoundError:
        print(f"Error: The file {file_path} does not exist.")
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")

def book_orders():
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray, Stock_Symbols, Stock_Tokens

    # Load the global variables from the CSV file
    load_global_variables()

    # Print the loaded global variables for debugging
    print(f"stocksList: {stocksList}")
    print(f"PlaceQtyForEachStockArray: {PlaceQtyForEachStockArray}")
    print(f"slArray: {slArray}")

    exchange = 'NSE'
    
    # Retrieve current positions
    try:
        ret = api.get_positions()
        if ret is None:
            print("Error: No positions data retrieved.")
            return

        # Calculate daily MTM and PnL
        mtm = 0
        pnl = 0
        for i in ret:
            mtm += float(i.get('urmtom', 0))
            pnl += float(i.get('rpnl', 0))

        day_m2m = mtm + pnl
        print(f'{day_m2m} is your Daily MTM')

        # Commented out the stop-loss order placement section
        if day_m2m <= -220 and not all_orders_completed:
            print('Executing all stop-loss orders')
            print(f"Value of all_orders_completed: {all_orders_completed}")
            for i, symbol in enumerate(stocksList):
                if i < len(PlaceQtyForEachStockArray):
                    try:
                        api.place_order(
                            buy_or_sell='B',
                            product_type='I',
                            exchange=exchange,
                            tradingsymbol=symbol,
                            quantity=PlaceQtyForEachStockArray[i],
                            discloseqty=0,
                            price_type='MKT',
                            trigger_price=None,
                            retention='DAY',
                            remarks='stop_loss_order'
                        )
                        print(f"Stop-loss order placed for symbol: {symbol}")
                    except ValueError:
                        print(f"Symbol {symbol} not found in the list.")
                    except Exception as e:
                        print(f"Error occurred for symbol {symbol}: {e}")

            all_orders_completed = True  # Indicate all stop-loss orders are placed
            stocksList.clear()  # Clear the stock list after orders are placed

        # Check each stock for hitting stop-loss or target price
        for i, symbol in enumerate(stocksList):
            if i < len(slArray) and i < len(Stock_Tokens):
                try:
                    targetPrice = round(slArray[i] * 0.992, 2)
                    stopLoss = round(slArray[i] * 1.004, 2)
                    stopLossFinal = round(float(stopLoss) * 10) / 10
                    targetPriceFinal = round(float(targetPrice) * 10) / 10
                    
                    # Retrieve quote for the current symbol
                    quote = api.get_quotes(exchange=exchange, token=Stock_Tokens[Stock_Symbols.index(symbol)])
                    LTP = float(quote["lp"])

                    # Print values for debugging
                    print(f"Processing symbol: {symbol}")
                    print(f"LTP: {LTP}, StopLossFinal: {stopLossFinal}, TargetPriceFinal: {targetPriceFinal}")

                    # Check if LTP meets stop-loss or target price criteria
                    if LTP >= stopLossFinal or LTP <= targetPriceFinal and not all_orders_completed:
                        # Debug statement to confirm the block execution
                        print(f"Condition met for symbol: {symbol}. LTP: {LTP}, StopLossFinal: {stopLossFinal}, TargetPriceFinal: {targetPriceFinal}")

                        # Place order if conditions are met
                        api.place_order(
                            buy_or_sell='B',
                            product_type='I',
                            exchange=exchange,
                            tradingsymbol=symbol,
                            quantity=PlaceQtyForEachStockArray[i],
                            discloseqty=0,
                            price_type='MKT',
                            trigger_price=None,
                            retention='DAY',
                            remarks='stop_loss_order'
                        )
                        print(f"Stop loss/target hit for symbol: {symbol} at price: {LTP}")
                        completed_orders.append(symbol)
                        
                except ValueError:
                    print(f"ValueError: Symbol {symbol} not found in the list or error in token retrieval.")
                except Exception as e:
                    print(f"Error occurred for symbol {symbol}: {e}")

    except Exception as e:
        print(f"An error occurred while retrieving positions or placing orders: {e}")

def main_loop():
    while True:
        book_orders()
        time.sleep(10)  # Wait for 10 seconds before next check

if __name__ == "__main__":
    main_loop()
