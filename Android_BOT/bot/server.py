"""Shoonya phone bot - Flask + SocketIO server with token auth."""
import os
import time
import threading
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO

from . import config as cfg
from . import state
from .bot_core import TradingBot

app = Flask(
    __name__,
    template_folder=os.path.join(cfg.PKG_DIR, "templates"),
    static_folder=os.path.join(cfg.PKG_DIR, "static"),
)
app.config["SECRET_KEY"] = cfg.SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

bot = TradingBot()
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

PUBLIC_PATHS = ("/api/login",)
WEBHOOK = "/webhook"


def is_authed():
    return session.get("auth") is True


@app.before_request
def guard():
    p = request.path
    if p.startswith("/static") or p in PUBLIC_PATHS or p == "/":
        return None
    if is_authed():
        return None
    if p == WEBHOOK and request.args.get("token", "") == cfg.AUTH_TOKEN:
        return None
    return jsonify({"error": "unauthorized"}), 401


@socketio.on("connect")
def sio_connect(auth=None):
    try:
        auth = auth or {}
        if isinstance(auth, dict) and auth.get("token") == cfg.AUTH_TOKEN:
            return True
    except Exception:
        pass
    return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.json or {}
    if body.get("token", "") == cfg.AUTH_TOKEN:
        session["auth"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "wrong token"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


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
    pwd = body.get("pwd", "").strip() or None
    user_id = body.get("user_id", "").strip() or None
    if not token:
        return jsonify({"error": "SuperToken required"}), 400
    try:
        cap = int(cap)
    except ValueError:
        cap = cfg.DEFAULT_TRADING_CAP
    ok = bot.start(token, cap, pwd, user_id)
    if ok:
        return jsonify({"status": "started"})
    return jsonify({"error": "Login failed"}), 400


@app.route("/api/stop", methods=["POST"])
def api_stop():
    bot.stop()
    return jsonify({"status": "stopped"})


@app.route("/api/status", methods=["GET"])
def api_status():
    st = state.read_file()
    tunnel_url = st.get("tunnel_url", "")
    webhook_url = ""
    if tunnel_url:
        webhook_url = f"{tunnel_url}/webhook?token={cfg.AUTH_TOKEN}"
    return jsonify({
        "running": bot.running,
        "pnl": bot.get_total_pnl() if bot.running else 0,
        "uptime": int(time.time() - _start_time),
        "tunnel_url": tunnel_url,
        "webhook_url": webhook_url,
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


def run():
    socketio.run(app, host=cfg.HOST, port=cfg.PORT, debug=False,
                 allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run()