"""
Testing_WEBUI - Config
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Testing_Use"))

BROKER_CRED = os.path.join(SHARED_DIR, "cred.yml")
EXCEL_FILE = os.path.join(SHARED_DIR, "NSE_symbols_filtered.xlsx")
STOCKS_DATA_DIR = os.path.join(SHARED_DIR, "Stocks_DATA")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

PORT = 5000

DEFAULT_CSV = os.path.join(r"C:\Users\omkar\Downloads", "Backtest bb_blast_sell_Combined.csv")
DEFAULT_SL_PCT = 0.6
DEFAULT_TP_PCT = 1.3
DEFAULT_CAPITAL = 200000
