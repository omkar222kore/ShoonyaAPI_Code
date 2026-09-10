"""
Testing_WEBUI - Flask App
Backtest machine: login → filter CSV → download data → run backtest → Excel
"""
import os
import json
import time
import queue
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO

import config as cfg
from backtest_engine import BacktestEngine

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

engine = None
backtest_running = False
last_results = None
last_summary = None


def emit_log(msg):
    socketio.emit("log", {"message": msg})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    global engine
    body = request.json or {}
    token = body.get("super_token", "").strip()
    if not token:
        return jsonify({"error": "SuperToken required"}), 400
    engine = BacktestEngine(on_progress=emit_log)
    ok = engine.login(token)
    if ok:
        return jsonify({"status": "logged_in"})
    return jsonify({"error": "Login failed"}), 400


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    global backtest_running, last_results, last_summary
    if backtest_running:
        return jsonify({"error": "Backtest already running"}), 400
    if not engine or not engine.api:
        return jsonify({"error": "Login first"}), 400

    body = request.json or {}
    csv_path = body.get("csv_path", cfg.DEFAULT_CSV)
    sl_pct = float(body.get("sl_pct", cfg.DEFAULT_SL_PCT))
    tp_pct = float(body.get("tp_pct", cfg.DEFAULT_TP_PCT))
    capital = int(body.get("capital", cfg.DEFAULT_CAPITAL))
    skip_download = body.get("skip_download", False)

    def run():
        global backtest_running, last_results, last_summary
        backtest_running = True
        socketio.emit("backtest_status", {"state": "running"})

        try:
            stocks_info = engine.filter_csv(csv_path)
            if not stocks_info:
                emit_log("No stocks found in CSV")
                backtest_running = False
                socketio.emit("backtest_status", {"state": "error"})
                return

            if not skip_download:
                engine.download_data(stocks_info)

            results = engine.run_backtest(stocks_info, sl_pct, tp_pct, capital)

            os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = os.path.join(cfg.RESULTS_DIR, f"backtest_{ts}.xlsx")
            summary = engine.save_results(results, out)

            last_results = results
            last_summary = summary
            socketio.emit("backtest_status", {"state": "done", "summary": summary})
        except Exception as e:
            emit_log(f"FATAL: {e}")
            socketio.emit("backtest_status", {"state": "error"})
        finally:
            backtest_running = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "backtest_running": backtest_running,
        "summary": last_summary,
        "has_results": last_results is not None,
    })


@app.route("/api/download", methods=["GET"])
def api_download():
    if not last_summary or not last_summary.get("output_file"):
        return jsonify({"error": "No results yet"}), 400
    path = last_summary["output_file"]
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
    socketio.run(app, host="0.0.0.0", port=cfg.PORT, debug=False, allow_unsafe_werkzeug=True)
