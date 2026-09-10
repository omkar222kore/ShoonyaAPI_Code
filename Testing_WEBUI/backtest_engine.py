"""
Backtest Engine - extracted from BackTest_Final.ipynb
Filter CSV → Download data → Run backtest → Excel results
"""
import os
import time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from NorenRestApiPy.NorenApi import NorenApi
import yaml


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        super().__init__(
            host="https://trade.shoonya.com/NorenWClientWeb/",
            websocket="wss://trade.shoonya.com/NorenWSWeb/"
        )


class BacktestEngine:
    def __init__(self, on_progress=None):
        self.api = None
        self.on_progress = on_progress or (lambda msg: None)

    def _log(self, msg):
        self.on_progress(msg)

    def login(self, super_token):
        import config as cfg
        with open(cfg.BROKER_CRED) as f:
            cred = yaml.load(f, Loader=yaml.FullLoader)
        self.api = ShoonyaApiPy()
        ret = self.api.set_session(cred["user"], cred["pwd"], super_token)
        if ret:
            self._log(f"Login OK | User: {cred['user']}")
            return True
        self._log("Login FAILED")
        return False

    def filter_csv(self, csv_path):
        self._log(f"Filtering CSV: {csv_path}")
        df = pd.read_csv(csv_path)
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(
            df[date_col].astype(str).str.strip(),
            format="%d-%m-%Y %I:%M %p", errors="coerce"
        )
        df = df.dropna(subset=[date_col])
        df["time_only"] = df[date_col].dt.strftime("%H:%M")
        valid_times = ["09:45", "10:00", "10:30", "10:45"]
        filtered = df[df["time_only"].isin(valid_times)].copy()
        filtered["ts"] = filtered[date_col].dt.strftime("%Y-%m-%d %H:%M:%S")
        counts = filtered["ts"].value_counts()
        valid_ts = counts[counts <= 3].index
        filtered = filtered[filtered["ts"].isin(valid_ts)].copy()
        stocks_info = [
            (str(row.iloc[0]).strip(), str(row.iloc[1]).strip())
            for _, row in filtered.iterrows()
        ]
        self._log(f"Filtered: {len(stocks_info)} stocks from {len(df)} rows")
        return stocks_info

    def download_data(self, stocks_info):
        import config as cfg
        output_dir = cfg.STOCKS_DATA_DIR
        os.makedirs(output_dir, exist_ok=True)

        # Load token lookup from Excel
        token_df = pd.read_excel(cfg.EXCEL_FILE)
        token_df["TradingSymbol"] = token_df["TradingSymbol"].astype(str).str.strip().str.upper()
        self._log(f"Loaded {len(token_df)} tokens from Excel")

        symbols = list({f"{s}-EQ" for _, s in stocks_info})
        symbols.sort()
        self._log(f"Downloading {len(symbols)} unique symbols...")

        now = datetime.now()
        start_ts = (now - relativedelta(months=6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        ok, fail = [], []
        for i, sym in enumerate(symbols, 1):
            try:
                # Look up numeric token from Excel
                match = token_df[token_df["TradingSymbol"] == sym.upper()]
                if match.empty:
                    self._log(f"[{i}/{len(symbols)}] {sym}: TOKEN NOT FOUND in Excel")
                    fail.append(sym)
                    continue
                numeric_token = str(match.iloc[0]["Token"])

                self._log(f"[{i}/{len(symbols)}] {sym} (token={numeric_token})...")
                ret = self.api.get_time_price_series(
                    exchange="NSE", token=numeric_token,
                    starttime=start_ts, interval=1
                )
                if ret and len(ret) > 0:
                    pd.DataFrame(ret).to_excel(
                        os.path.join(output_dir, f"{sym}.xlsx"), index=False
                    )
                    ok.append(sym)
                    self._log(f"  OK ({len(ret)} rows)")
                else:
                    fail.append(sym)
                    self._log(f"  NO DATA")
            except Exception as e:
                fail.append(sym)
                self._log(f"  ERROR: {str(e)[:60]}")

        self._log(f"Download done: {len(ok)} ok, {len(fail)} failed")
        return ok, fail

    def run_backtest(self, stocks_info, sl_pct=0.6, tp_pct=1.3, capital=200000):
        import config as cfg
        data_dir = cfg.STOCKS_DATA_DIR
        results = []
        sl_mult = 1 + sl_pct / 100
        tp_mult = 1 - tp_pct / 100

        self._log(f"Running backtest: SL={sl_pct}% TP={tp_pct}% Cap={capital}")

        for idx, (entry_time_str, stock_name) in enumerate(stocks_info, 1):
            xlsx = os.path.join(data_dir, f"{stock_name}-EQ.xlsx")
            try:
                sd = pd.read_excel(xlsx, usecols=["time", "intc"])
                sd["time"] = pd.to_datetime(sd["time"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
                sd.sort_values("time", inplace=True)

                entry_time = pd.to_datetime(entry_time_str, format="%Y-%m-%d %H:%M:%S")
                start_t = entry_time + pd.Timedelta(minutes=2)
                rows = sd[sd["time"] >= start_t]

                if rows.empty:
                    self._log(f"[{idx}/{len(stocks_info)}] {stock_name}: NO ENTRY after {start_t}")
                    continue

                ep = rows.iloc[0]["intc"]
                entry_actual = rows.iloc[0]["time"]
                qty = int(capital / ep)
                sl_price = ep * sl_mult
                tp_price = ep * tp_mult
                self._log(f"[{idx}/{len(stocks_info)}] {stock_name} | ENTRY: {entry_actual} @ {ep:.2f} | Qty: {qty} | SL: {sl_price:.2f} | TP: {tp_price:.2f}")

                sub = sd[sd["time"] > entry_actual]
                hit = False
                for _, row in sub.iterrows():
                    cp, ct = row["intc"], row["time"]
                    if cp < tp_price:
                        pnl = (ep - cp) * qty
                        results.append([stock_name, entry_time, ct, cp, "Profit", pnl])
                        self._log(f"  EXIT: {ct} @ {cp:.2f} | TP HIT | PnL: +{pnl:.2f}")
                        hit = True
                        break
                    elif cp > sl_price:
                        pnl = (ep - cp) * qty
                        results.append([stock_name, entry_time, ct, cp, "Loss", pnl])
                        self._log(f"  EXIT: {ct} @ {cp:.2f} | SL HIT | PnL: {pnl:.2f}")
                        hit = True
                        break

                if not hit:
                    cutoff = pd.to_datetime(entry_time_str[:10] + " 15:15:00")
                    cut_rows = sd[sd["time"] >= cutoff]
                    if not cut_rows.empty:
                        cp = cut_rows.iloc[0]["intc"]
                        pnl = (ep - cp) * qty
                        s = "Profit" if cp < ep else "Loss"
                        results.append([stock_name, entry_time, cutoff, cp, f"Cut 15:15 ({s})", pnl])
                        sign = "+" if pnl >= 0 else ""
                        self._log(f"  EXIT: {cutoff} @ {cp:.2f} | CUT 15:15 | PnL: {sign}{pnl:.2f}")
                    else:
                        self._log(f"  NO CUT DATA at 15:15 for {stock_name}")

            except Exception as e:
                self._log(f"[{idx}] {stock_name}: ERROR {str(e)[:60]}")

        self._log(f"Backtest done: {len(results)} trades")
        return results

    def save_results(self, results, output_path):
        if not results:
            self._log("No results to save")
            return None
        df = pd.DataFrame(results, columns=[
            "Stock Name", "Entry Time", "Hit/Exit Time", "Price", "Status", "Profit/Loss Amount"
        ])
        df.to_excel(output_path, index=False)

        total = df["Profit/Loss Amount"].sum()
        wins = len(df[df["Profit/Loss Amount"] > 0])
        losses = len(df[df["Profit/Loss Amount"] < 0])
        n = len(df)
        wr = (wins / n * 100) if n > 0 else 0

        summary = {
            "total_pnl": round(total, 2),
            "wins": wins,
            "losses": losses,
            "total_trades": n,
            "win_rate": round(wr, 1),
            "output_file": output_path,
        }
        self._log(f"PnL: {total:,.2f} | Wins: {wins} | Losses: {losses} | WR: {wr:.1f}%")
        return summary
