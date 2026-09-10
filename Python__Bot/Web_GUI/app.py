"""
Shoonya WebApp - Flask + SocketIO Server
Dashboard + /webhook endpoint + ngrok management.
"""
import os
import sys
import time
import json
import subprocess
import threading
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

import config as cfg
from bot_core import TradingBot

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

bot = TradingBot()
ngrok_process = None
ngrok_urls = {}
_start_time = time.time()


def emit_log(msg):
    socketio.emit("log", {"message": msg})

def emit_pnl(pnl):
    socketio.emit("pnl", {"value": pnl})

def emit_positions(positions):
    socketio.emit("positions", {"data": positions})

def emit_status(status):
    socketio.emit("status", {"state": status})

def emit_order(order):
    socketio.emit("order", {"data": order})

bot.on_log = emit_log
bot.on_pnl = emit_pnl
bot.on_positions = emit_positions
bot.on_status = emit_status
bot.on_order = emit_order


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not bot.running:
        return jsonify({"status": "bot_not_running"}), 400
    result = bot.handle_webhook(data)
    return jsonify(result), 200


@app.route("/api/start", methods=["POST"])
def api_start():
    body = request.json or {}
    token = body.get("super_token", "").strip()
    cap = body.get("trading_cap", cfg.DEFAULT_TRADING_CAP)
    if not token:
        return jsonify({"error": "SuperToken required"}), 400
    try:
        cap = int(cap)
    except ValueError:
        cap = cfg.DEFAULT_TRADING_CAP
    ok = bot.start(token, cap)
    if ok:
        return jsonify({"status": "started"})
    return jsonify({"error": "Login failed"}), 400


@app.route("/api/stop", methods=["POST"])
def api_stop():
    bot.stop()
    return jsonify({"status": "stopped"})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "running": bot.running,
        "pnl": bot.get_total_pnl() if bot.running else 0,
        "uptime": int(time.time() - _start_time),
        "ngrok_urls": ngrok_urls,
        "webhook_url": ngrok_urls.get(5000, ""),
    })


@app.route("/api/positions", methods=["GET"])
def api_positions():
    if not bot.running:
        return jsonify([])
    positions = bot.get_positions()
    result = []
    for p in positions:
        result.append({
            "symbol": str(p.get("tsym", "")).strip(),
            "qty": int(float(p.get("netqty", 0))),
            "pnl": float(p.get("urmtom", 0)),
        })
    return jsonify(result)


def start_ngrok():
    global ngrok_process, ngrok_urls
    ngrok_exe = cfg.NGROK_EXE
    ngrok_cfg = cfg.NGROK_CONFIG
    if not os.path.exists(ngrok_exe):
        emit_log("[NGROK] ngrok.exe not found, skipping tunnel")
        return
    if not os.path.exists(ngrok_cfg):
        emit_log("[NGROK] ngrok.yml not found, skipping tunnel")
        return
    emit_log("[NGROK] Starting ngrok tunnels...")
    try:
        ngrok_process = subprocess.Popen(
            [ngrok_exe, "start", "--all", "--config", ngrok_cfg],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(4)
        if ngrok_process.poll() is not None:
            emit_log("[NGROK] Failed to start")
            return
        for _ in range(15):
            try:
                resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
                tunnels = resp.json().get("tunnels", [])
                if tunnels:
                    for t in tunnels:
                        addr = t.get("config", {}).get("addr", "")
                        url = t.get("public_url", "")
                        if ":5000" in addr:
                            ngrok_urls[5000] = url
                        elif ":5001" in addr:
                            ngrok_urls[5001] = url
                        elif ":5002" in addr:
                            ngrok_urls[5002] = url
                    emit_log(f"[NGROK] Tunnels ready: {len(tunnels)}")
                    for port, url in ngrok_urls.items():
                        emit_log(f"  Port {port} -> {url}")
                    socketio.emit("ngrok", {"urls": ngrok_urls})
                    break
            except Exception:
                pass
            time.sleep(1)
        if not ngrok_urls:
            emit_log("[NGROK] No tunnels found after waiting")
    except Exception as e:
        emit_log(f"[NGROK] Error: {e}")


def stop_ngrok():
    global ngrok_process, ngrok_urls
    if ngrok_process:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(ngrok_process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except:
            pass
        ngrok_process = None
    ngrok_urls = {}


if __name__ == "__main__":
    emit_log("Starting Shoonya WebApp...")
    threading.Thread(target=start_ngrok, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=cfg.PORT, debug=False, allow_unsafe_werkzeug=True)
