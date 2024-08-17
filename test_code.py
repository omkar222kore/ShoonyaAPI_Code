
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
SHARED_DATA_JSON = "E:\\Z_algo_Script\\TestingNewWay\\shared_data.json"
REMOVE_STOCKS = ['M&M-EQ', 'M&MFIN-EQ', 'J&KBANK-EQ']  # Stocks to remove

# Initialize API
api = ShoonyaApiPy()
factor2 = pyotp.TOTP(TOKEN).now()
api.login(userid=USER, password=PWD, twoFA=factor2, vendor_code=VC, api_secret=APP_KEY, imei=IMEI)

api.place_order(buy_or_sell='S', product_type='I', exchange='NSE', tradingsymbol='TCS-EQ',
                      quantity=5, discloseqty=0, price_type='SL-LMT',
                      price=4418,  # Use target price or another logic
                      trigger_price=4450,  # Use stop_loss variable as trigger price
                      retention='DAY', remarks='stop_loss_order')