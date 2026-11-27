import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def load_super_token(path):
    if not path or not os.path.exists(path):
        raise FileNotFoundError("super_token.txt not found: %s" % path)
    with open(path, "r", encoding="utf-8") as fh:
        token = fh.read().strip()
    if not token:
        raise ValueError("super_token.txt is empty: %s" % path)
    return token


class ShoonyaBroker:
    def __init__(self, user_id, token_file, paper=True, timeout=12):
        self.user_id = str(user_id)
        self.token_file = token_file
        self.paper = bool(paper)
        self.timeout = timeout
        self.token = load_super_token(token_file)
        self._paper_seq = 0

    def _post(self, endpoint, jdata, timeout=None):
        values = dict(jdata)
        values.setdefault("uid", self.user_id)
        payload = ("jData=" + json.dumps(values, separators=(",", ":")) + "&jKey=" + self.token).encode("utf-8")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        url = "https://trade.shoonya.com/NorenWClientWeb/" + endpoint
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else None

    def get_quote(self, exchange, token):
        res = self._post("GetQuotes", {"exch": exchange, "token": str(token)})
        if not isinstance(res, dict) or res.get("stat") != "Ok":
            return None
        return res

    def get_time_price_series(self, exchange, token, starttime, endtime=None, interval=15):
        jdata = {
            "ordersource": "API",
            "exch": exchange,
            "token": str(token),
            "st": str(int(starttime)),
            "intrv": str(interval),
        }
        if endtime is not None:
            jdata["et"] = str(int(endtime))
        res = self._post("TPSeries", jdata)
        return res if isinstance(res, list) else None

    def place_order(self, tsym, qty, side, remarks="BB_BLAST_SHORT"):
        if self.paper:
            self._paper_seq += 1
            return "PAPER_%d_%d" % (int(time.time() * 1000), self._paper_seq)
        jdata = {
            "uid": self.user_id,
            "actid": self.user_id,
            "ordersource": "API",
            "exch": "NSE",
            "tsym": urllib.parse.quote_plus(tsym),
            "qty": str(int(qty)),
            "dscqty": "0",
            "prc": "0",
            "prd": "I",
            "trantype": side,
            "prctyp": "MKT",
            "ret": "DAY",
            "amo": "NO",
            "remarks": remarks,
        }
        res = self._post("PlaceOrder", jdata)
        if not isinstance(res, dict) or res.get("stat") != "Ok":
            raise RuntimeError("PlaceOrder failed for %s: %s" % (tsym, res))
        order_id = res.get("norenordno") or res.get("orderid") or res.get("result")
        if not order_id:
            raise RuntimeError("PlaceOrder returned no order id for %s: %s" % (tsym, res))
        return str(order_id)

    def get_order_book(self):
        res = self._post("OrderBook", {})
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            if isinstance(res.get("data"), list):
                return res["data"]
            if res.get("stat") == "Ok":
                return []
        return []

    def get_positions(self):
        res = self._post("PositionBook", {})
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            if isinstance(res.get("data"), list):
                return res["data"]
            if res.get("stat") == "Ok":
                return []
        return []

    def get_limits(self):
        return self._post("Limits", {})

    def available_margin(self):
        res = self.get_limits()
        if not res:
            return None
        containers = res if isinstance(res, list) else [res]
        for container in containers:
            if not isinstance(container, dict):
                continue
            candidates = [container]
            for value in container.values():
                if isinstance(value, dict):
                    candidates.append(value)
            for item in candidates:
                for key in ("availablemargin", "availablecash", "availcash", "cash", "net", "margin"):
                    if key in item:
                        try:
                            return float(item[key])
                        except (TypeError, ValueError):
                            pass
        return None

    def wait_for_fill(self, order_id, timeout=8.0):
        if self.paper:
            return {"status": "COMPLETE", "avgprc": None, "fillshares": None}
        deadline = time.time() + timeout
        while time.time() < deadline:
            for order in self.get_order_book():
                if not isinstance(order, dict):
                    continue
                if str(order.get("norenordno", "")) != str(order_id):
                    continue
                status = str(order.get("status", "")).strip().upper()
                if status in ("REJECTED", "CANCELED", "CANCELLED", "INVALID"):
                    return None
                if status in ("COMPLETE", "FILLED"):
                    try:
                        avg = float(order.get("avgprc") or order.get("averageprice") or 0)
                    except (TypeError, ValueError):
                        avg = 0.0
                    try:
                        filled = int(float(order.get("fillshares") or order.get("qty") or 0))
                    except (TypeError, ValueError):
                        filled = 0
                    return {"status": status, "avgprc": avg, "fillshares": filled, "raw": order}
            time.sleep(0.25)
        return None

    def position_qty(self, tsym):
        for position in self.get_positions():
            if not isinstance(position, dict):
                continue
            if str(position.get("tsym", "")).strip().upper() != str(tsym).strip().upper():
                continue
            try:
                return int(float(position.get("netqty", 0) or 0))
            except (TypeError, ValueError):
                return 0
        return 0
