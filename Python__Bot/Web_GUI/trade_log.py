"""
Trade Log - appends every closed trade to an Excel workbook.

Two sheets:
  TRADES  - one row per closed position
  SUMMARY - one row per trading date, recomputed on every save

Guarantees: never raises. A failed write must not interrupt trading.
"""
import os
import threading
from datetime import datetime

from config import TRADE_LOG_FILE

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font
    AVAILABLE = True
    _IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover
    AVAILABLE = False
    _IMPORT_ERROR = str(exc)

TRADE_HEADERS = [
    "Date", "Time", "Exchange", "Symbol", "Side", "Qty",
    "Entry", "Exit", "P&L", "Mode", "Reason", "OrderID", "Cum P&L",
]

SUMMARY_HEADERS = [
    "Date", "Trades", "Wins", "Losses", "Gross P&L", "Cum P&L",
]

_PNL_IDX = 8

_lock = threading.Lock()


def _bold_header(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"


def _write_header(ws, headers):
    """Write the header into row 1 and pin the append cursor there.

    openpyxl's new sheets start with _current_row == 1, so ws.append()
    would land on row 2. Write cells directly and reset the cursor.
    """
    for i, value in enumerate(headers, start=1):
        ws.cell(row=1, column=i, value=value)
    ws._current_row = 1
    _bold_header(ws)


def _ensure_header(ws, headers):
    if ws.cell(row=1, column=1).value:
        return
    _write_header(ws, headers)


def _load():
    """Open (or create) the workbook, returning (wb, trades_sheet)."""
    if os.path.exists(TRADE_LOG_FILE):
        wb = load_workbook(TRADE_LOG_FILE)
    else:
        wb = Workbook()
        wb.active.title = "TRADES"

    if "TRADES" not in wb.sheetnames:
        wb.create_sheet("TRADES", 0)
    if "SUMMARY" not in wb.sheetnames:
        wb.create_sheet("SUMMARY")

    _ensure_header(wb["TRADES"], TRADE_HEADERS)
    _ensure_header(wb["SUMMARY"], SUMMARY_HEADERS)
    return wb, wb["TRADES"]



def _cumulative(ws):
    total = 0.0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) <= _PNL_IDX:
            continue
        try:
            total += float(row[_PNL_IDX] or 0)
        except (TypeError, ValueError):
            continue
    return total


def _write_summary(wb):
    """Rebuild the SUMMARY sheet from TRADES."""
    ws = wb["TRADES"]
    groups = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        date = str(row[0])
        try:
            pnl = float(row[_PNL_IDX] or 0)
        except (TypeError, ValueError):
            pnl = 0.0
        g = groups.setdefault(date, {"t": 0, "w": 0, "l": 0, "p": 0.0})
        g["t"] += 1
        if pnl > 0:
            g["w"] += 1
        elif pnl < 0:
            g["l"] += 1
        g["p"] += pnl

    idx = wb.sheetnames.index("SUMMARY") if "SUMMARY" in wb.sheetnames else len(wb.sheetnames)
    if "SUMMARY" in wb.sheetnames:
        del wb["SUMMARY"]
    sm = wb.create_sheet("SUMMARY", idx)
    _write_header(sm, SUMMARY_HEADERS)

    running = 0.0
    for date in sorted(groups):
        g = groups[date]
        running += g["p"]
        sm.append([
            date, g["t"], g["w"], g["l"],
            round(g["p"], 2), round(running, 2),
        ])


def append_trade(row):
    """Append one closed trade. Returns True on success, False otherwise."""
    if not AVAILABLE:
        return False

    with _lock:
        try:
            wb, ws = _load()
            pnl = float(row.get("pnl") or 0)
            cum = _cumulative(ws) + pnl
            ws.append([
                row.get("date") or datetime.now().strftime("%Y-%m-%d"),
                row.get("time") or datetime.now().strftime("%H:%M:%S"),
                row.get("exchange", "NSE"),
                row.get("symbol", ""),
                row.get("side", ""),
                row.get("qty", 0),
                row.get("entry"),
                row.get("exit"),
                round(pnl, 2),
                row.get("mode", ""),
                row.get("reason", ""),
                row.get("order_id", ""),
                round(cum, 2),
            ])
            _write_summary(wb)
            wb.save(TRADE_LOG_FILE)
            return True
        except Exception as exc:
            print(f"[TRADE_LOG] write failed: {exc}")
            return False


def read_summary():
    """Return SUMMARY rows as a list of dicts. Never raises."""
    if not AVAILABLE:
        return []
    with _lock:
        try:
            if not os.path.exists(TRADE_LOG_FILE):
                return []
            wb = load_workbook(TRADE_LOG_FILE, read_only=True)
            if "SUMMARY" not in wb.sheetnames:
                return []
            ws = wb["SUMMARY"]
            out = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                out.append({
                    "date": row[0], "trades": row[1], "wins": row[2],
                    "losses": row[3], "gross_pnl": row[4], "cum_pnl": row[5],
                })
            wb.close()
            return out
        except Exception as exc:
            print(f"[TRADE_LOG] read failed: {exc}")
            return []


def read_trades(limit=50):
    """Return the most recent trades, newest first, as list of dicts."""
    if not AVAILABLE:
        return []
    with _lock:
        try:
            if not os.path.exists(TRADE_LOG_FILE):
                return []
            wb = load_workbook(TRADE_LOG_FILE, read_only=True)
            if "TRADES" not in wb.sheetnames:
                return []
            ws = wb["TRADES"]
            raw = [r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
            wb.close()
        except Exception as exc:
            print(f"[TRADE_LOG] read failed: {exc}")
            return []

    out = []
    for row in raw[-limit:][::-1]:
        out.append({
            "date": row[0], "time": row[1], "exchange": row[2],
            "symbol": row[3], "side": row[4], "qty": row[5],
            "entry": row[6], "exit": row[7], "pnl": row[8],
            "mode": row[9], "reason": row[10], "order_id": row[11],
        })
    return out


def status():
    return {
        "available": AVAILABLE,
        "file": TRADE_LOG_FILE,
        "exists": os.path.exists(TRADE_LOG_FILE),
        "error": _IMPORT_ERROR,
    }


if __name__ == "__main__":
    print(status())
