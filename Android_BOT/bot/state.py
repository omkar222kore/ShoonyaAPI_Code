"""Shared JSON state between the Android service, the Flask server and the Kivy UI."""
import json
import os
import threading

from . import config as cfg

_lock = threading.Lock()
_d = {}


def update(**kw):
    global _d
    with _lock:
        _d.update(kw)
        try:
            os.makedirs(os.path.dirname(cfg.status_path()), exist_ok=True)
            with open(cfg.status_path(), "w") as f:
                json.dump(_d, f)
        except Exception:
            pass


def get(key, default=None):
    with _lock:
        return _d.get(key, default)


def all_data():
    with _lock:
        return dict(_d)


def load_from_disk():
    global _d
    try:
        with open(cfg.status_path()) as f:
            _d = json.load(f)
    except Exception:
        _d = {}


def read_file():
    try:
        with open(cfg.status_path()) as f:
            return json.load(f)
    except Exception:
        return {}