"""Shoonya phone bot - Android background service (runs Flask + tunnel)."""
import os
import sys
import threading
import time
import traceback
from datetime import datetime

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)


def _log_file():
    from bot import config as cfg
    return os.path.join(cfg.app_data_dir(), "service.log")


def log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_log_file(), "a") as f:
            f.write("%s %s\n" % (ts, msg))
    except Exception:
        pass


def _foreground_notice():
    try:
        from android import service
        service.start_foreground(1337, dict(lowness=1))
    except Exception:
        pass
    try:
        from android.notification import notify
        notify(
            title="Shoonya Bot",
            message="Bot running on 127.0.0.1:5000 (tap to open dashboard)",
            show_in_tray=True,
        )
    except Exception:
        pass


def _flask_loop():
    from bot import config as cfg
    from bot import state
    while True:
        try:
            from bot import server as srv
            state.update(flask="starting", flask_error="")
            srv.socketio.run(
                srv.app, host=cfg.HOST, port=cfg.PORT,
                debug=False, use_reloader=False,
                allow_unsafe_werkzeug=True,
            )
        except Exception as e:
            state.update(flask_error=str(e)[:300])
            log("flask error: %s" % e)
            traceback.print_exc()
        state.update(flask="down")
        time.sleep(5)


def _tunnel_loop():
    from bot import state
    try:
        from bot.tunnel import TunnelManager
        TunnelManager().start()
        state.update(tunnel_error="")
        log("tunnel manager started")
    except Exception as e:
        state.update(tunnel_error=str(e)[:300])
        log("tunnel error: %s" % e)
        traceback.print_exc()


def main():
    from bot import state
    state.load_from_disk()
    state.update(running=True, started=time.time(), service_error="")
    log("service main started")
    _foreground_notice()

    threading.Thread(target=_flask_loop, daemon=True).start()
    threading.Thread(target=_tunnel_loop, daemon=True).start()

    while True:
        time.sleep(20)
        state.update(alive=True, tick=time.time(), service_error="")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        from bot import state
        state.update(service_error=str(e)[:300])
        log("service crashed: %s" % e)
        traceback.print_exc()
        time.sleep(5)