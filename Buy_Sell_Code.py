import csv
from datetime import datetime as dt_datetime, timedelta
import time
import threading
import logging
import pandas as pd
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
import yaml
import time
import os
import csv
from datetime import datetime as dt_datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import glob




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

# Example usage
chrome_driver_path = r'C:\Users\omkar\AppData\Local\Google\Chrome\User Data\Default\chromedriver-win64\chromedriver.exe'
login_url = "https://chartink.com/login"
username = "om222kore@gmail.com"
password = "OMKAR222kore@"
csv_file_name = "Backtest BB_Blast_Sell, Technical Analysis Scanner.csv"



if ret:
    print("Login Successful")
else:
    print("Login Failed")
    exit()

# File and Logging Configuration
CSV_FILE_PATH = "C:\\Users\\omkar\\Downloads\\Backtest BB_Blast_Sell, Technical Analysis Scanner.csv"
REMOVE_STOCKS = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']
PNL_LOWER_THRESHOLD = -120
PNL_UPPER_THRESHOLD = 240
folder_path = r'C:\Users\omkar\Downloads'

def delete_csv_files():
    """Delete only CSV files in the folder."""
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    for file in csv_files:
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")
            


def download_csv(chrome_driver_path, login_url, username, password, csv_file_name, xpath_index):
    """Download the CSV file."""
    service = Service(chrome_driver_path)
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        print("STARTED")
        driver.get(login_url)
        time.sleep(2)
        
        username_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys(username)
        password_field.send_keys(password)
        password_field.send_keys(Keys.RETURN)
        time.sleep(2)
        
        # Dynamically replace the XPath index
        button_xpath = f"(//b[contains(text(),'BB_Blast_Sell')])[{xpath_index}]"
        button1 = driver.find_element(By.XPATH, button_xpath)
        button1.click()
        time.sleep(2)
        
        download_button = driver.find_element(By.XPATH, "//a[normalize-space()='Download csv']")
        download_button.click()
        time.sleep(5)

        csv_file_path = os.path.join(folder_path, csv_file_name)
        
        if not os.path.exists(csv_file_path):
            print(f"CSV file not found: {csv_file_path}")
            return []

        stock_list = []
        with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader)  # Skip the header if there is one
            for row in reader:
                if len(row) > 0:
                    cell_value = row[0].strip()
                    try:
                        cell_datetime = dt_datetime.strptime(cell_value, '%d-%m-%Y %H:%M')
                        stock_list.append((cell_datetime, row[1]))  # Store both datetime and stock name
                    except ValueError:
                        pass  # Ignore date parsing errors

        return stock_list
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return []
    
    finally:
        driver.quit()


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
                        quantity=net_quantities[i],
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


# # Scheduling Functions
# def schedule_place_orders():
#     specific_times = ["09:46:35", "10:01:35", "10:46:35"]
#     end_time = dt_datetime.combine(dt_datetime.now().date(), dt_datetime.strptime("15:15:00", "%H:%M:%S").time())

#     while True:
#         now = dt_datetime.now()
#         if now >= end_time:
#             logging.info("Stopping schedule_place_orders as it is past 3:15 PM.")
#             break

#         for target_time in specific_times:
#             target_datetime = dt_datetime.combine(now.date(), dt_datetime.strptime(target_time, "%H:%M:%S").time())
#             if now < target_datetime:
#                 sleep_duration = (target_datetime - now).total_seconds()
#                 time.sleep(sleep_duration)
#                 place_orders(get_previous_timestamp())
                
# # Define the times for the function to run
# run_times = [
#     dt_datetime.now().replace(hour=9, minute=46, second=5, microsecond=0),
#     dt_datetime.now().replace(hour=10, minute=1, second=5, microsecond=0),
#     dt_datetime.now().replace(hour=10, minute=46, second=5, microsecond=0),
# ]



# # Main loop
# for run_time in run_times:
#     now = dt_datetime.now()
#     if now < run_time:
#         wait_time = (run_time - now).total_seconds()
#         print(f"Waiting for {wait_time} seconds until {run_time.strftime('%I:%M:%S %p')}.")
#         time.sleep(wait_time)
    
#     # Determine the XPath index based on the current time
#     xpath_index = run_times.index(run_time) + 1  # 1 for 9:45, 2 for 10:00, 3 for 10:45
#     print(f"Running at {run_time.strftime('%I:%M:%S %p')} with XPath index: {xpath_index}")
    
#     delete_csv_files()
#     stock_list = download_csv(chrome_driver_path, login_url, username, password, csv_file_name, xpath_index)

#     # Get the time exactly 15 minutes before now
#     target_time = dt_datetime.now() - timedelta(minutes=15)
    
#     # Filter stocks based on the target time
#     filtered_stocks = [f"{stock[1]}-EQ" for stock in stock_list if stock[0] == target_time]

#     # Print whether stocks were found or not
#     if filtered_stocks:
#         print(f"Stocks scanned at {target_time.strftime('%I:%M %p')}: {filtered_stocks}")
#     else:
#         print("No stocks found.")


# def schedule_place_buy_orders_based_on_positions():
#     start_time = dt_datetime.combine(dt_datetime.now().date(), dt_datetime.strptime("09:50:00", "%H:%M:%S").time())
#     end_time = dt_datetime.combine(dt_datetime.now().date(), dt_datetime.strptime("15:15:00", "%H:%M:%S").time())

#     now = dt_datetime.now()
#     if now < start_time:
#         sleep_duration = (start_time - now).total_seconds()
#         time.sleep(sleep_duration)

#     while True:
#         now = dt_datetime.now()
#         if now >= end_time:
#             logging.info("Stopping schedule_place_buy_orders_based_on_positions as it is past 3:15 PM.")
#             break

#         place_buy_orders_based_on_positions()
#         time.sleep(30)  # Run every minute


# # Main Execution
# if __name__ == "__main__":
#     threading.Thread(target=schedule_place_orders).start()
#     threading.Thread(target=schedule_place_buy_orders_based_on_positions).start()



def download_and_place_order():
    """Download the CSV and place orders sequentially."""
    try:
        # Determine XPath index based on the current time
        current_time = dt_datetime.now()
        if current_time.hour == 9 and current_time.minute >= 45:
            xpath_index = 1
        elif current_time.hour == 10 and current_time.minute >= 0:
            xpath_index = 2
        elif current_time.hour == 10 and current_time.minute >= 45:
            xpath_index = 3
        else:
            xpath_index = 1  # Default or fallback

        # Delete old CSV files before downloading
        delete_csv_files()

        # Download new CSV
        stock_list = download_csv(
            chrome_driver_path, login_url, username, password, csv_file_name, xpath_index
        )

        # Get the time exactly 15 minutes before now
        target_time = dt_datetime.now() - timedelta(minutes=15)

        # Filter stocks based on the target time
        filtered_stocks = [
            f"{stock[1]}-EQ" for stock in stock_list if stock[0] == target_time
        ]

        # Print the stocks found
        if filtered_stocks:
            print(f"Stocks scanned at {target_time.strftime('%I:%M %p')}: {filtered_stocks}")
        else:
            print("No stocks found.")

        # Place orders based on filtered stocks
        target_datetime_str = get_previous_timestamp()
        place_orders(target_datetime_str)

    except Exception as e:
        print(f"Error in download_and_place_order: {e}")


def buy_orders_schedule():
    """Schedule buy orders based on positions."""
    place_buy_orders_based_on_positions()


# Scheduler Configuration
def setup_schedule():
    # Task 1: Download CSV and place orders at specified times
    schedule.every().day.at("09:46:05").do(download_and_place_order)
    schedule.every().day.at("10:01:05").do(download_and_place_order)
    schedule.every().day.at("10:46:05").do(download_and_place_order)

    # Task 2: Buy orders schedule (runs every 30 seconds between 9:50 AM and 3:15 PM)
    def buy_orders_scheduler():
        now = dt_datetime.now()
        start_time = dt_datetime.combine(now.date(), dt_datetime.strptime("09:50:00", "%H:%M:%S").time())
        end_time = dt_datetime.combine(now.date(), dt_datetime.strptime("15:15:00", "%H:%M:%S").time())

        if start_time <= now <= end_time:
            buy_orders_schedule()

    schedule.every(30).seconds.do(buy_orders_scheduler)


# Run Scheduler
def run_scheduler():
    setup_schedule()
    while True:
        schedule.run_pending()
        time.sleep(1)


# Main Execution
if __name__ == "__main__":
    threading.Thread(target=run_scheduler).start()
