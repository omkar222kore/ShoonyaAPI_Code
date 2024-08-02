import time
import schedule
import logging
import pandas as pd
import glob
import os
import csv
from datetime import datetime as dt_datetime
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
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
