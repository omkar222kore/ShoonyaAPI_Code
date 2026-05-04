### this is to just login into briker terminal . make sure whenever we login for first time 
# place an dummy order get Super token by clicking shit+ ctrl+i --> network --> payload .


import csv
from datetime import datetime as dt_datetime, timedelta
import time
import threading
import logging
import pandas as pd
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
import yaml
import token
from dateutil.relativedelta import relativedelta


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        # super().__init__(host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')
        super().__init__(host='https://trade.shoonya.com/NorenWClientWeb/', websocket='wss://trade.shoonya.com/NorenWSWeb/')



# Initialize API
api = ShoonyaApiPy()

with open('cred.yml') as f:
    cred = yaml.load(f, Loader=yaml.FullLoader)

SuperToken ="31c954501666f2a546ef4384b9bc79c2f6273440ca3065b63da6f8d14d01bebd"
userId=cred['user']
Passwrd=cred['pwd']
ret = api.set_session(userId , Passwrd ,SuperToken )


if ret:
    print("Login Successful")
else:
    print("Login Failed")
    exit()

print(ret)


close_response = api.place_order(
                buy_or_sell='B',  # BUY to close SHORT
                product_type='I',
                exchange='NSE',
                tradingsymbol="GVT&D-EQ",
                quantity=1,
                discloseqty=0,
                price_type='MKT',
                retention='DAY',
                remarks='Close_TP')
                                        

print("Close Order Response:", close_response)