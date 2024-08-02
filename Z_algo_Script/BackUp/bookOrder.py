
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



def execute_orders(api, exchange, stocksList, remove_stocks, capUsed=18000):
    PlaceQtyForEachStockArray = []
    slArray = []
    
    # Filter out symbols to remove
    stocksList = [symbol for symbol in stocksList if symbol not in remove_stocks]
    
    print('Symbols matching the target datetime:')
    print(stocksList)
    
    qtyGet = len(stocksList)
    print(f"Number of stocks selected: {qtyGet}")
    
    # Example logic for calculating capital per stock
    if qtyGet <= 2:
        capForEachStock = 20000
    elif qtyGet == 3:
        capForEachStock = 25000
    else:
        capForEachStock = int(capUsed * 5 / qtyGet)
        
    print(f"Capital for each stock: {capForEachStock}")
    
    if len(stocksList) <= 5:
        for symbol in stocksList:
            try:
                # Retrieve quote for the current symbol (replace with actual API call)
                quote = api.get_quotes(exchange=exchange, token=symbol)
                LTP = float(quote["lp"])
                
                # Calculate quantity to place for each stock
                PlaceQtyForEachStock = int(capForEachStock / LTP)
                PlaceQtyForEachStockArray.append(PlaceQtyForEachStock)
                slArray.append(LTP)
                
                # Place order (replace with actual order placement code)
                api.place_order(buy_or_sell='S', product_type='I', exchange=exchange, tradingsymbol=symbol,
                                quantity=PlaceQtyForEachStock, discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')
            
            except Exception as e:
                print(f"Error occurred for symbol {symbol}: {e}")
    else:
        stocksList = []
        print("Stock list has more than 5 stocks. It has been set to an empty array.")
    
    return stocksList, PlaceQtyForEachStockArray, slArray
