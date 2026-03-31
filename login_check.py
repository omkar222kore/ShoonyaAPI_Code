import csv
from datetime import datetime as dt_datetime, timedelta
import time
import threading
import logging
import pandas as pd
from NorenRestApiPy.NorenApi import NorenApi
import pyotp
import yaml


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(host='https://api.shoonya.com/NorenWClientTP/',
                         websocket='wss://api.shoonya.com/NorenWSTP/')


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

if ret:
    print("Login Successful")
else:
    print("Login Failed")
    exit()