

import logging
from threading import Timer
import pandas as pd
import concurrent.futures
import pyotp
from NorenRestApiPy.NorenApi import NorenApi
import requests
from bs4 import BeautifulSoup
import json
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
import time
import sys
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging
import datetime
from pyotp import TOTP
import os
import logging
import csv
from pyotp import TOTP
import schedule
import threading



class ShoonyaApiPy(NorenApi):
    def __init__(self):
        NorenApi.__init__(self, host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')
        global api
        api = self
        # Enable debug to see request and responses
        logging.basicConfig(level=logging.DEBUG)

# Start of our program
api = ShoonyaApiPy()

# Credentials
user = 'FA74468'
pwd = 'GURU222kore$'
token = 'XT2L66VT73Q22P33BNCHKN6WA2Q37KK6'
factor2 = pyotp.TOTP(token).now()
vc = 'FA74468_U'
app_key = 'c98e82a190da8181c80fb94cf0a31144'
imei = 'abc1234'

# Make the opt call

ret = api.login(userid=user, password=pwd, twoFA=factor2, vendor_code=vc, api_secret=app_key, imei=imei)
print(ret)
pd.DataFrame([ret])


# Global variables for strategy execution
stocksList = []
completed_orders = []
all_orders_completed = False
slArray = []
PlaceQtyForEachStockArray = []
Stock_Symbols = []  # Define Stock Symbols as needed
Stock_Tokens = []   # Define Stock Tokens as needed
remove_stocks = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']

# Function to execute the main strategy
def execute_strategy():
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray, Stock_Symbols, Stock_Tokens
    
    exchange = 'NSE'
    
    # Define the path to the CSV file in the Downloads folder
    downloads_folder = os.path.expanduser('~/Downloads')
    csv_file_path = os.path.join(downloads_folder, 'Backtest BB Blast_Omk, Technical Analysis Scanner.csv')
    
    # Define the target datetime
    target_datetime_str = '28-06-2024 10:15 am'
    target_datetime = datetime.datetime.strptime(target_datetime_str, '%d-%m-%Y %I:%M %p')
    
    # Function to parse datetime with error handling
    def parse_datetime(date_str):
        try:
            return datetime.datetime.strptime(date_str.strip(), '%d-%m-%Y %I:%M %p')
        except ValueError:
            return None
    
    # Initialize list to store symbols matching the target datetime
    stockList = []
    
    # Open the CSV file and read its content
    with open(csv_file_path, mode='r', newline='') as file:
        reader = csv.reader(file)
        header = next(reader)  # Read the header row
        
        # Iterate through each row in the CSV
        for row in reader:
            cell_value = row[0].strip()
            cell_datetime = parse_datetime(cell_value)
            
            # Check if the cell datetime matches the target datetime exactly
            if cell_datetime and cell_datetime == target_datetime:
                # Append the symbol (assuming it's in the second column) to stockList
                if len(row) > 1:
                    stockList.append(f"{row[1]}-EQ")  # Append "-EQ" to each symbol
    
    # Filter out symbols to remove
    stocksList = [symbol for symbol in stockList if symbol not in remove_stocks]
    
    # Print symbols matching the target datetime
    print('Symbols matching the target datetime:')
    print(stocksList)
    
    qtyGet = len(stocksList)
    print(f"Number of stocks selected: {qtyGet}")
    
    # Example logic for calculating capital per stock
    capUsed = 5000
    if qtyGet <= 2:
        capForEachStock = 3000
    elif qtyGet == 3:
        capForEachStock = 3000
    else:
        capForEachStock = int(capUsed * 5 / qtyGet)
        
    print(f"Capital for each stock: {capForEachStock}")
    
    # Iterate over each symbol and retrieve data
    for symbol in stocksList:
        try:
            # Retrieve quote for the current symbol using the API (replace with actual API call)
            quote = api.get_quotes(exchange=exchange, token=symbol)
            LTP = float(quote["lp"])
            
            # Calculate quantity to place for each stock
            PlaceQtyForEachStock = int(capForEachStock / LTP)
            PlaceQtyForEachStockArray.append(PlaceQtyForEachStock)
            slArray.append(LTP)
            
            # Example: Place order (replace with actual order placement code)
            api.place_order(buy_or_sell='S', product_type='I', exchange=exchange, tradingsymbol=symbol,
                            quantity=PlaceQtyForEachStock, discloseqty=0, price_type='MKT',
                            trigger_price=None, retention='DAY', remarks='stop_loss_order')
        
        except ValueError:
            print(f"Symbol {symbol} not found in the list.")
        except Exception as e:
            print(f"Error occurred for symbol {symbol}: {e}")






# Function to book orders based on certain conditions
def book_orders(scheduler=None):
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray, Stock_Symbols, Stock_Tokens
    exchange = 'NSE'
    
    # Calculate day's mark-to-market and profit/loss
    mtm = sum(float(i['urmtom']) for i in ret)
    pnl = sum(float(i['rpnl']) for i in ret)
    day_m2m = mtm + pnl

    # Place stop-loss orders if conditions are met
    if day_m2m <= -220 and not all_orders_completed:
        print('Executing all stop-loss orders')
        for i, symbol in enumerate(stocksList):
            try:
                api.place_order(buy_or_sell='B', product_type='I', exchange=exchange, tradingsymbol=symbol,
                                quantity=PlaceQtyForEachStockArray[i], discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')
            except ValueError:
                print(f"Symbol {symbol} not found in the list.")
            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")
        
        all_orders_completed = True  # Indicate all stop-loss orders are placed
        stocksList.clear()  # Clear the stock list after orders are placed
        
        if scheduler:
            scheduler.stop()  # Stop the scheduler if provided
        return  # Exit the function after placing stop-loss orders
    

    else:
        # Check each stock for hitting stop-loss or target price
        for i, symbol in enumerate(stocksList):
            try:
                targetPrice = round((slArray[i] * 1.008), 2)
                stopLoss = round((slArray[i] * 0.9955), 2)
                stopLossFinal = round(float(stopLoss) * 10) / 10
                targetPriceFinal = round(float(targetPrice) * 10) / 10

                index = Stock_Symbols.index(symbol)
                tokenForStock = Stock_Tokens[index]
                quote = api.get_quotes(exchange=exchange, token=tokenForStock)
                LTP = float(quote["lp"])

                if LTP <= stopLossFinal or LTP >= targetPriceFinal:
                    api.place_order(buy_or_sell='S', product_type='I', exchange=exchange, tradingsymbol=symbol,
                                    quantity=PlaceQtyForEachStockArray[i], discloseqty=0, price_type='MKT',
                                    trigger_price=None, retention='DAY', remarks='stop_loss_order')
                    print(f"Stop loss/target hit for symbol: {symbol} at price: {LTP}")
                    completed_orders.append(symbol)
                else:
                    print(f"No target or stop loss hit for symbol: {symbol} at price: {LTP}")
                    continue
            
            except ValueError:
                print(f"Symbol {symbol} not found in the list.")
            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")

    # Remove completed orders from active lists
    for symbol in completed_orders:
        index = stocksList.index(symbol)
        stocksList.pop(index)
        slArray.pop(index)
        PlaceQtyForEachStockArray.pop(index)

    completed_orders.clear()  # Clear completed orders list
    
    # Check if all orders are completed
    if not stocksList:
        all_orders_completed = True
        if scheduler:
            scheduler.stop()  # Stop the scheduler if provided


# Thread function to schedule the book_orders() function every 5 seconds
def schedule_book_orders():
    while True:
        schedule.run_pending()
        time.sleep(5)




# Schedule execution of execute_strategy() once at start
execute_strategy()

# Schedule book_orders() to run every 5 seconds
schedule.every(5).seconds.do(book_orders)

# Start a thread to handle schedule run loop for book_orders()
schedule_thread = threading.Thread(target=schedule_book_orders)
schedule_thread.start()