import os
import csv
from datetime import datetime as dt_datetime
from NorenRestApiPy.NorenApi import NorenApi
import pyotp

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

def extract_stock_list_from_csv(csv_file_path, target_datetime_str):
    stockList = []
    try:
        target_datetime = dt_datetime.strptime(target_datetime_str, '%d-%m-%Y %I:%M %p')
        with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader)
            for row in reader:
                if len(row) > 0:
                    cell_value = row[0].strip()
                    cell_datetime = dt_datetime.strptime(cell_value, '%d-%m-%Y %I:%M %p')
                    if cell_datetime == target_datetime and len(row) > 1:
                        stockList.append(f"{row[1]}-EQ")
    except Exception as e:
        print(f"An error occurred: {e}")
    return stockList

def place_orders():
    global stocksList, PlaceQtyForEachStockArray, slArray  # Declare these as global to access them outside the function

    csv_file_path = "C:/Users/omkar/Downloads/Backtest BB Blast_Omk, Technical Analysis Scanner.csv"
    target_datetime_str = dt_datetime.today().strftime('%d-%m-%Y') + " 10:15 AM"
    stocksList = extract_stock_list_from_csv(csv_file_path, target_datetime_str)
    remove_stocks = []  # Populate this list if needed
    stocksList = [symbol for symbol in stocksList if symbol not in remove_stocks]

    qtyGet = len(stocksList)
    capUsed = 18000
    capForEachStock = int(capUsed * 5 / qtyGet) if qtyGet > 3 else (25000 if qtyGet == 3 else 20000)

    PlaceQtyForEachStockArray = []
    slArray = []

    if qtyGet <= 5:
        for symbol in stocksList:
            try:
                quote = api.get_quotes(exchange='NSE', token=symbol)
                LTP = float(quote["lp"])
                PlaceQtyForEachStock = int(capForEachStock / LTP)
                PlaceQtyForEachStockArray.append(PlaceQtyForEachStock)
                slArray.append(LTP)

                api.place_order(buy_or_sell='S', product_type='I', exchange='NSE', tradingsymbol=symbol,
                                quantity=PlaceQtyForEachStock, discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')

            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")
    else:
        stocksList = []

    with open("shared_data.csv", mode='w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(["stocksList", "PlaceQtyForEachStockArray", "slArray"])
        for i in range(len(stocksList)):
            writer.writerow([stocksList[i], PlaceQtyForEachStockArray[i], slArray[i]])

def print_selected_global_variables():
    # Print only the selected global variables
    for name in ['stocksList', 'PlaceQtyForEachStockArray', 'slArray']:
        value = globals().get(name, 'Variable not found')
        print(f'{name}: {value}')

if __name__ == "__main__":
    place_orders()
    print_selected_global_variables()
