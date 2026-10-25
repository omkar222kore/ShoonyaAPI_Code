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
from flask import Flask, render_template, request, jsonify, send_file, session
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

def emit_closed_trade(row):
    socketio.emit("closed_trade", {"data": row})

bot.on_log = emit_log
bot.on_pnl = emit_pnl
bot.on_positions = emit_positions
bot.on_status = emit_status
bot.on_order = emit_order
bot.on_closed_trade = emit_closed_trade


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": str(getattr(e, "description", None) or e)}), 500


UNLOCK_EXEMPT = {"/api/unlock", "/webhook"}

@app.before_request
def _require_ui_auth():
    path = request.path
    if path.startswith("/static/") or path in UNLOCK_EXEMPT:
        return None
    if session.get("ui_auth"):
        return None
    if path == "/" or path.startswith("/api/"):
        if path == "/":
            return render_template("unlock.html")
        return jsonify({"error": "Locked", "locked": True}), 401
    return None

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.route("/")
def index():
    if not session.get("ui_auth"):
        return render_template("unlock.html")
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
    virtual = body.get("virtual", cfg.VIRTUAL_MODE_DEFAULT)
    if not token:
        return jsonify({"error": "SuperToken required"}), 400
    try:
        cap = int(cap)
    except ValueError:
        cap = cfg.DEFAULT_TRADING_CAP
    ok = bot.start(token, cap, virtual=bool(virtual))
    if ok:
        return jsonify({"status": "started", "mode": "virtual" if bot.virtual else "live"})
    if bot._eod_reached():
        return jsonify({
            "error": f"Square-off time {bot.eod_time} has already passed. "
                     "Change the SQUARE-OFF AT time first."
        }), 400
    return jsonify({"error": "Login failed"}), 400


@app.route("/api/stop", methods=["POST"])
def api_stop():
    bot.stop()
    return jsonify({"status": "stopped"})


@app.route("/api/unlock", methods=["POST"])
def api_unlock():
    body = request.json or {}
    if (body.get("password") or "") == cfg.UI_PASSWORD:
        session["ui_auth"] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "Wrong password"}), 403

@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.json or {}
    ok, msg, user = bot.login_from_ui(
        user_id=(body.get("user_id") or "").strip(),
        password=body.get("password") or "",
        otp=(body.get("otp") or "").strip(),
        jkey=(body.get("jkey") or "").strip(),
    )
    if ok:
        try:
            socketio.emit("auth", {"logged_in": True, "user": user})
        except Exception:
            pass
        return jsonify({"status": "ok", "user": user, "message": msg})
    return jsonify({"error": msg}), 400

@app.route("/api/getjkey", methods=["POST"])
def api_getjkey():
    body = request.json or {}
    ok, msg, token = bot.fetch_jkey(
        uid=(body.get("user_id") or body.get("uid") or "").strip(),
        pwd=body.get("password") or body.get("pwd") or "",
        otp=(body.get("otp") or body.get("factor2") or "").strip(),
        vc=(body.get("vc") or "").strip(),
        appkey=(body.get("appkey") or body.get("app_key") or "").strip(),
        imei=(body.get("imei") or "").strip(),
        source=(body.get("source") or "WEB").strip(),
        apkversion=(body.get("apkversion") or "1.0.0").strip(),
    )
    if ok:
        return jsonify({"status": "ok", "jkey": token, "supertoken": token})
    return jsonify({"error": msg}), 400

@app.route("/api/login/save", methods=["POST"])
def api_login_save():
    body = request.json or {}
    ok, msg = bot.save_credentials(
        user_id=(body.get("user_id") or "").strip(),
        password=body.get("password") or "",
        otp=(body.get("otp") or "").strip(),
        jkey=(body.get("jkey") or "").strip(),
    )
    if ok:
        return jsonify({"status": "ok", "message": msg})
    return jsonify({"error": msg}), 400

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "running": bot.running,
        "mode": "virtual" if bot.virtual else "live",
        "realized_pnl": round(bot.realized_pnl, 2) if bot.virtual else bot.today_realized_pnl(),
        "pnl": bot.last_pnl if bot.running else bot.today_realized_pnl(),
        "uptime": int(time.time() - _start_time),
        "ngrok_urls": ngrok_urls,
        "webhook_url": ngrok_urls.get(5000, ""),
        "eod_time": bot.eod_time,
        "eod_done": bot._eod_done,
        "eod_pending": bot._eod_reached(),
        "square_off_pending": bot._sq_off_requested,
        "logged_in": bot.logged_in,
        "user": bot.userId,
    })


@app.route("/api/closedtrades", methods=["GET"])
def api_closed_trades():
    """Today's closes for the positions table.

    The Excel journal keeps full history; the screen only ever shows the
    current trading day. Falls back to the journal after a server restart.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    rows = [r for r in bot.closed_trades if str(r.get("date", "")) == today]

    if not rows:
        try:
            import trade_log
            rows = [r for r in trade_log.read_trades(500)
                    if str(r.get("date", "")) == today]
        except Exception as e:
            return jsonify({"data": [], "error": str(e)})

    return jsonify({"data": rows[:50], "date": today})


@app.route("/api/eod", methods=["POST"])
def api_eod():
    body = request.json or {}
    ok, msg = bot.set_eod_time(body.get("time", ""))
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"status": msg, "eod_time": bot.eod_time})


@app.route("/api/squareoff", methods=["POST"])
def api_squareoff():
    if not bot.running:
        return jsonify({"error": "Bot is not running"}), 400
    ok, msg = bot.request_square_off()
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"status": "requested", "message": msg})


@app.route("/api/tradelog", methods=["GET"])
def api_tradelog():
    import trade_log
    st = trade_log.status()
    if not st["available"]:
        return jsonify({"error": f"openpyxl unavailable: {st['error']}"}), 500
    if not st["exists"]:
        return jsonify({"error": "Trade log is empty - no trades closed yet"}), 404
    return send_file(st["file"], as_attachment=True, download_name="trade_log.xlsx")


@app.route("/api/tradesummary", methods=["GET"])
def api_tradesummary():
    import trade_log
    return jsonify({"file": cfg.TRADE_LOG_FILE, "summary": trade_log.read_summary()})


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


def _collect_tunnels(timeout=15):
    """Populate ngrok_urls by querying the local ngrok agent API."""
    for _ in range(timeout):
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
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_ngrok():
    global ngrok_process
    ngrok_exe = cfg.NGROK_EXE
    ngrok_cfg = cfg.NGROK_CONFIG
    if not os.path.exists(ngrok_exe):
        emit_log("[NGROK] ngrok.exe not found, skipping tunnel")
        return
    if not os.path.exists(ngrok_cfg):
        emit_log("[NGROK] ngrok.yml not found, skipping tunnel")
        return

    # Reuse an agent that is already running so the public URL survives restarts.
    if _collect_tunnels(timeout=2):
        emit_log("[NGROK] Reusing running ngrok agent")
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
            emit_log("[NGROK] Spawn exited - checking for an existing agent")
            if not _collect_tunnels(timeout=5):
                emit_log("[NGROK] Failed to start")
            return
        if not _collect_tunnels(timeout=15):
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
