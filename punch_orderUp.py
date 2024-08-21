
import os
import csv
import json
from datetime import datetime as dt_datetime, timedelta
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
from datetime import datetime as dt_datetime, date as dt_date

class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')

# Configuration Constants
USER = 'FA74468'
PWD = 'GURU222kore$'
TOKEN = 'XT2L66VT73Q22P33BNCHKN6WA2Q37KK6'
VC = 'FA74468_U'
APP_KEY = 'c98e82a190da8181c80fb94cf0a31144'
IMEI = 'abc1234'
CSV_FILE_PATH = "C:\\Users\\omkar\\Downloads\\Backtest BB Blast_Omk, Technical Analysis Scanner.csv"
SHARED_DATA_JSON = "D:\\AA_trading_Algos\ShoonyaAPI_Code\\shared_data.json"
REMOVE_STOCKS = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']  # Stocks to remove

# Initialize API
api = ShoonyaApiPy()
factor2 = pyotp.TOTP(TOKEN).now()
api.login(userid=USER, password=PWD, twoFA=factor2, vendor_code=VC, api_secret=APP_KEY, imei=IMEI)




def is_first_run_of_day(file_path):
    """Check if it's the first run of the day based on the file modification time."""
    if not os.path.exists(file_path):
        return True
    file_mod_time = dt_datetime.fromtimestamp(os.path.getmtime(file_path))
    return file_mod_time.date() != dt_date.today()

def extract_stock_list_from_csv(csv_file_path, target_datetime_str):
    stock_list = []
    try:
        # Parse the target datetime string in 24-hour format
        target_datetime = dt_datetime.strptime(target_datetime_str, '%d-%m-%Y %I:%M %p')
        target_date = target_datetime.date()
        target_time = target_datetime.time()
        print(f"Target date for comparison: {target_date}, Target time: {target_time}")

        with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            print("Headers found in CSV:", reader.fieldnames)

            for row in reader:
                try:
                    # Parse the row date and time in 12-hour format with AM/PM
                    row_datetime = dt_datetime.strptime(row['date'], '%d-%m-%Y %I:%M %p')
                except ValueError as e:
                    print(f"Date parsing error for row '{row['date']}': {e}")
                    continue

                if row_datetime.date() == target_date and row_datetime.time() == target_time:
                    stock_list.append(f"{row['symbol']}-EQ")
    except Exception as e:
        print(f"An error occurred while extracting stock list: {e}")
    return stock_list

def place_orders(target_datetime_str):
    """Place orders based on the extracted stock list."""
    global stocksList, slArray, tgtArray

    stocksList = extract_stock_list_from_csv(CSV_FILE_PATH, target_datetime_str)
    stocksList = [symbol for symbol in stocksList if symbol not in REMOVE_STOCKS]

    # Check if the size of stocksList exceeds 3
    if len(stocksList) > 3:
        stocksList = []  # Set stocksList to an empty list
        print("More than 3 stocks found. No orders will be placed.")

    # Check if it's the first run of the day and clear the file if it is
    if is_first_run_of_day(SHARED_DATA_JSON):
        open(SHARED_DATA_JSON, 'w').close()

    # Load existing data from JSON file
    try:
        if os.path.exists(SHARED_DATA_JSON):
            with open(SHARED_DATA_JSON, 'r', encoding='utf-8-sig') as file:
                data = json.load(file)
        else:
            data = []
    except json.JSONDecodeError:
        data = []

    if not stocksList:
        slArray = []
        tgtArray = []
        print("No stocks found for the given time. Clearing previous stock lists.")
    else:
        slArray = []
        tgtArray = []

        for symbol in stocksList:
            try:
                quote = api.get_quotes(exchange='NSE', token=symbol)
                LTP = float(quote["lp"])

                # Calculate stop-loss and target prices
                stop_lossCal = round((LTP * 1.0045),2)
                targetCal = round((LTP * 0.992),2)
                stop_loss = round(float(stop_lossCal) * 10) / 10
                target = round(float(targetCal) * 10) / 10
                Qty_Stock=round(10000/LTP)
                slArray.append(stop_loss)
                tgtArray.append(target)

                print(f"LTP: {LTP}, Stop-Loss: {stop_loss}, Target: {target}")
                
                api.place_order(buy_or_sell='S', product_type='I', exchange='NSE', tradingsymbol=symbol,
                      quantity=Qty_Stock, discloseqty=0, price_type='MKT', trigger_price=None,  # Use stop_loss variable as trigger price
                      retention='DAY', remarks='Place_order')
                

                # Append the stock data to the JSON data
                data.append({
                    "stock": symbol,
                    "stop_loss": stop_loss,
                    "target": target,
                    "quantity":Qty_Stock
                })

            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")

    # Write updated data back to JSON file
    with open(SHARED_DATA_JSON, 'w', encoding='utf-8-sig') as file:
        json.dump(data, file, indent=4)

def round_down_to_nearest_15_minutes(dt):
    """Round down a datetime object to the nearest 15 minutes."""
    new_minute = (dt.minute // 15) * 15
    return dt.replace(minute=new_minute, second=0, microsecond=0)

def get_previous_timestamp():
    """Get the previous 15-minute interval timestamp."""
    now = dt_datetime.now()
    previous_time = now - timedelta(minutes=15)  # Subtract 15 minutes
    rounded_time = round_down_to_nearest_15_minutes(previous_time)  # Round down to nearest 15 minutes
    return rounded_time.strftime('%d-%m-%Y %I:%M %p')  # Return in the desired format

def print_selected_global_variables():
    """Print selected global variables."""
    variables_to_print = ['stocksList', 'slArray', 'tgtArray']
    for name in variables_to_print:
        value = globals().get(name, 'Variable not found')
        print(f'{name}: {value}')

if __name__ == "__main__":
    # Create the target datetime string using the previous 15-minute interval
    target_datetime_str = get_previous_timestamp()
    print(f"Target datetime for orders: {target_datetime_str}")

    place_orders(target_datetime_str)
    print_selected_global_variables()


