import time
import schedule
import logging
import pandas as pd
import glob
import os
import csv
from datetime import datetime as dt_datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import pyotp
from NorenRestApiPy.NorenApi import NorenApi

class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')
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

# Define the path to the Downloads folder
downloads_folder = r'C:\Users\omkar\Downloads'

# Create the full path for CSV files
csv_files = glob.glob(os.path.join(downloads_folder, '*.csv'))

# Iterate over the list of CSV files and delete each one
for file in csv_files:
    try:
        os.remove(file)
        print(f"Deleted: {file}")
    except Exception as e:
        print(f"Error deleting {file}: {e}")

print("All .csv files have been deleted.")

# Global variables for strategy execution
stocksList = []
completed_orders = []
all_orders_completed = False
slArray = []
PlaceQtyForEachStockArray = []
Stock_Symbols = []  # Define Stock Symbols as needed
Stock_Tokens = []   # Define Stock Tokens as needed
remove_stocks = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']

def process_website_and_csv_download(chrome_driver_path, login_url, username, password, csv_file_name, target_datetime_str):
    stockList = []
    
    try:
        # Initialize Chrome WebDriver
        service = Service(chrome_driver_path)
        options = webdriver.ChromeOptions()
        # Uncomment the following line if you want to use the user data directory
        # options.add_argument("user-data-dir=C:/Users/omkar/AppData/Local/Google/Chrome/User Data/Default")
        # Uncomment the following line to run Chrome in headless mode
        # options.add_argument("--headless")
        
        driver = webdriver.Chrome(service=service, options=options)
        
        # Open the login URL
        driver.get(login_url)
        
        # Wait for the page to load completely
        time.sleep(5)
        
        # Locate the username and password fields and enter the credentials
        username_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")
        
        username_field.send_keys(username)
        password_field.send_keys(password)
        
        # Submit the login form
        password_field.send_keys(Keys.RETURN)
        
        # Wait for a while to see the result of the login
        time.sleep(2)
        
        # Click on the first button with the specified XPath
        button1 = driver.find_element(By.XPATH, '//*[@id="home"]/table/tbody/tr[4]/td[1]/a/b')
        button1.click()
        
        # Wait for a while after clicking the first button
        time.sleep(2)
        
        # Click on the second button with the specified XPath (CSV file downloader)
        button2 = driver.find_element(By.XPATH, '//*[@id="backtest-container"]/div[2]/a')
        button2.click()
        
        # Wait for a while after clicking the second button
        time.sleep(2)
        
        # Define the path to the CSV file in the Downloads folder
        downloads_folder = os.path.expanduser('~/Downloads')
        csv_file_path = os.path.join(downloads_folder, csv_file_name)
        
        # Define the target datetime
        target_datetime = dt_datetime.strptime(target_datetime_str, '%d-%m-%Y %I:%M %p')
        
        # Function to parse datetime with error handling
        def parse_datetime(date_str):
            try:
                return dt_datetime.strptime(date_str.strip(), '%d-%m-%Y %I:%M %p')
            except ValueError:
                return None
        
        # Open the CSV file and read its content
        with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader)  # Read the header row
        
            # Iterate through each row in the CSV
            for row in reader:
                if len(row) > 0:
                    cell_value = row[0].strip()  # Assuming the datetime is in the first column
                    cell_datetime = parse_datetime(cell_value)
                    
                    # Check if the cell datetime matches the target datetime exactly
                    if cell_datetime and cell_datetime == target_datetime:
                        # Append the symbol (assuming it's in the second column) to stockList
                        if len(row) > 1:
                            stockList.append(f"{row[1]}-EQ")  # Append "-EQ" to each symbol
        
    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        # Close the browser
        driver.quit()
    
    # Return the list of symbols matching the target datetime
    return stockList

# Function to execute the main strategy
def execute_strategy():
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray, Stock_Symbols, Stock_Tokens
    
    exchange = 'NSE'
    # Example usage within execute_strategy function
    chrome_driver_path = "C:/Users/omkar/AppData/Local/Google/Chrome/User Data/Default/chromedriver-win64/chromedriver.exe"
    login_url = "https://chartink.com/login"
    username = "akashkharade.760@gmail.com"
    password = "7030232281"
    csv_file_name = "Backtest BB Blast_Omk, Technical Analysis Scanner.csv"
    
    # Set target_datetime_str to today's date at 10:15 AM
    target_datetime_str = dt_datetime.today().strftime('%d-%m-%Y') + " 10:15 am"
    
    # Call the function to process website login, CSV download, and retrieve stockList
    stockList = process_website_and_csv_download(chrome_driver_path, login_url, username, password, csv_file_name, target_datetime_str)
    
    # Filter out symbols to remove
    stocksList = [symbol for symbol in stockList if symbol not in remove_stocks]
    
    # Print symbols matching the target datetime
    print('Symbols matching the target datetime:')
    print(stocksList)
    
    qtyGet = len(stocksList)
    print(f"Number of stocks selected: {qtyGet}")
    
    # Example logic for calculating capital per stock
    capUsed = 18000
    if qtyGet <= 2:
        capForEachStock = 20000
    elif qtyGet == 3:
        capForEachStock = 25000
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

# Function to book orders after strategy execution
def book_orders():
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray, Stock_Symbols, Stock_Tokens
    
    # Wait for 20 seconds after execute_strategy completes
    time.sleep(20)
    
    exchange = 'NSE'
    ret = api.get_positions()
    
    # Check if ret is None
    if ret is None:
        print("Error: No positions data retrieved.")
        return
    
    mtm = 0
    pnl = 0
    for i in ret:
        mtm += float(i['urmtom'])
        pnl += float(i['rpnl'])
        day_m2m = mtm + pnl

    print(f'{day_m2m} is your Daily MTM')

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
        
        return  # Exit the function after placing stop-loss orders
    
    # Check each stock for hitting stop-loss or target price
    for i, symbol in enumerate(stocksList):
        try:
            targetPrice = round((slArray[i] * 0.992), 2)
            stopLoss = round((slArray[i] * 1.004), 2)
            stopLossFinal = round(float(stopLoss) * 10) / 10
            targetPriceFinal = round(float(targetPrice) * 10) / 10

            index = Stock_Symbols.index(symbol)
            tokenForStock = Stock_Tokens[index]
            quote = api.get_quotes(exchange=exchange, token=tokenForStock)
            LTP = float(quote["lp"])

            if LTP <= stopLossFinal or LTP >= targetPriceFinal:
                api.place_order(buy_or_sell='B', product_type='I', exchange=exchange, tradingsymbol=symbol,
                                quantity=PlaceQtyForEachStockArray[i], discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')
                print(f"Stop loss/target hit for symbol: {symbol} at price: {LTP}")
                completed_orders.append(symbol)
                
        except ValueError:
            print(f"Symbol {symbol} not found in the list.")
        except Exception as e:
            print(f"Error occurred for symbol {symbol}: {e}")

# Schedule execution of execute_strategy() at 10:15 AM
target_time = dt_datetime.combine(dt_datetime.today(), dt_datetime.time(hour=10, minute=30))
schedule.every().day.at(target_time.strftime('%H:%M')).do(execute_strategy)

# Schedule book_orders() to run every 5 seconds
schedule.every(5).seconds.do(book_orders)

# Loop to run the scheduler
while True:
    schedule.run_pending()
    time.sleep(1)