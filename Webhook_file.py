import json
import time
import threading
from datetime import datetime
from flask import Flask, request


app = Flask(__name__)

received_webhooks = []


def parse_webhook_payload(data):
    """
    Convert Chartink webhook payload into internal stock list.
    """

    if not data:
        raise ValueError("Webhook payload is empty")

    stocks_raw = data.get("stocks", "")
    prices_raw = data.get("trigger_prices", "")
    triggered_at = data.get("triggered_at", "")

    if not stocks_raw:
        raise ValueError("Missing 'stocks' in webhook payload")

    if not prices_raw:
        raise ValueError("Missing 'trigger_prices' in webhook payload")

    if not triggered_at:
        raise ValueError("Missing 'triggered_at' in webhook payload")

    symbols = [symbol.strip() for symbol in stocks_raw.split(",") if symbol.strip()]
    prices = [price.strip() for price in prices_raw.split(",") if price.strip()]

    if len(symbols) != len(prices):
        raise ValueError(
            f"Stocks count and trigger price count mismatch: "
            f"{len(symbols)} stocks, {len(prices)} prices"
        )

    trigger_time = datetime.strptime(
        triggered_at.strip().upper(),
        "%I:%M %p"
    ).strftime("%H:%M")

    parsed_stocks = []

    for symbol, price in zip(symbols, prices):
        parsed_stocks.append({
            "symbol": symbol.strip().upper(),
            "symbol_eq": f"{symbol.strip().upper()}-EQ",
            "trigger_price": float(price),
            "time": trigger_time,
            "scan_name": data.get("scan_name", ""),
            "scan_url": data.get("scan_url", ""),
            "alert_name": data.get("alert_name", "")
        })

    return parsed_stocks


@app.route("/webhook", methods=["POST"])
def webhook_handler():
    try:
        data = request.json

        print("\n" + "=" * 80)
        print(f"WEBHOOK RECEIVED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        print("Raw payload:")
        print(json.dumps(data, indent=2))

        parsed_stocks = parse_webhook_payload(data)

        entry = {
            "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "raw_payload": data,
            "parsed_stocks": parsed_stocks
        }

        received_webhooks.append(entry)

        print("\nParsed stocks:")
        print(json.dumps(parsed_stocks, indent=2))

        print(f"\nTotal webhooks received: {len(received_webhooks)}")
        print("=" * 80)

        return {
            "status": "received",
            "message": "Webhook received successfully",
            "stocks_count": len(parsed_stocks),
            "parsed_stocks": parsed_stocks
        }, 200

    except Exception as e:
        print(f"Webhook error: {e}")

        return {
            "status": "error",
            "message": str(e)
        }, 400


print("=" * 80)
print("FLASK WEBHOOK RECEIVER STARTING")
print("=" * 80)
print("Local URL: http://127.0.0.1:5000/webhook")
print("LAN URL:   http://YOUR_LOCAL_IP:5000/webhook")
print("For Chartink, use ngrok URL ending with /webhook")
print("=" * 80)

app.run(host="0.0.0.0", port=5000, debug=False)
