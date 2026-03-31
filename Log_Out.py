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

api = ShoonyaApiPy()

with open('cred.yml') as f:
    cred = yaml.load(f, Loader=yaml.FullLoader)

otp = pyotp.TOTP(cred['factor2']).now()

# LOGIN (mandatory)
login_ret = api.login(
    userid=cred['user'],
    password=cred['pwd'],
    twoFA=otp,
    vendor_code=cred['vc'],
    api_secret=cred['apikey'],
    imei=cred['imei']
)

if login_ret is None:
    print("Login failed")
    exit()

print("Login successful")

# LOGOUT
logout_ret = api.logout()

if logout_ret:
    print("Logout successful")
else:
    print("Logout failed")
