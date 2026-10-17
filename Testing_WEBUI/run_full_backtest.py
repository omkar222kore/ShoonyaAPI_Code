"""
Standalone backtest run (no web UI, no login).

Uses the paths from config.py and writes the Excel into Testing_WEBUI\\results\\.
Requires the downloaded OHLC files to already exist in cfg.STOCKS_DATA_DIR
(use the web UI once, or call engine.download_data yourself).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg
from backtest_engine import BacktestEngine

engine = BacktestEngine(on_progress=print)
stocks = engine.filter_csv(cfg.DEFAULT_CSV)
print(f"\nRunning backtest on {len(stocks)} stocks...\n")
results = engine.run_backtest(
    stocks,
    sl_pct=cfg.DEFAULT_SL_PCT,
    tp_pct=cfg.DEFAULT_TP_PCT,
    capital=cfg.DEFAULT_CAPITAL,
    eod_time=cfg.EOD_EXIT_TIME,
)
os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
out = os.path.join(cfg.RESULTS_DIR, "backtest_all_stocks.xlsx")
summary = engine.save_results(results, out)
print(f"\nDONE: {summary}")
