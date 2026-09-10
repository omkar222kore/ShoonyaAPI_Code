import sys
sys.path.insert(0, r"D:\AlgoRepo\ShoonyaAPI_Code\Testing_WEBUI")
from backtest_engine import BacktestEngine

engine = BacktestEngine(on_progress=print)
stocks = engine.filter_csv(r"C:\Users\omkar\Downloads\Backtest bb_blast_sell_Combined.csv")
print(f"\nRunning backtest on {len(stocks)} stocks...\n")
results = engine.run_backtest(stocks, sl_pct=0.6, tp_pct=1.3, capital=200000)
summary = engine.save_results(results, r"C:\Users\omkar\Downloads\backtest_all_stocks.xlsx")
print(f"\nDONE: {summary}")
