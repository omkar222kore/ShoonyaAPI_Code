"""cloudflared quick-tunnel manager (writes URL + diagnostics into shared state).

The cloudflared binary is shipped as a native library (libcloudflared.so) so it
lands in nativeLibraryDir with exec permission; we exec it from there. The
assets copy is kept only as a fallback.
"""
import os
import re
import subprocess
import threading
import time

from . import config as cfg
from . import state

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _native_lib_dir():
    """Resolve the app's nativeLibraryDir from our own process's memory map."""
    try:
        with open("/proc/self/maps") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6 and "/lib/" in parts[-1]:
                    path = parts[-1]
                    if "libpython" in path or "libmain" in path:
                        return os.path.dirname(path)
    except Exception:
        pass
    return None


def _candidates():
    paths = []
    nl = _native_lib_dir()
    if nl:
        paths.append(os.path.join(nl, "libcloudflared.so"))
    paths.append(cfg.CLOUDFLARED_BIN)
    return paths


def _mount_for(path):
    try:
        best = None
        with open("/proc/mounts") as f:
            for line in f:
                p = line.split()
                if len(p) >= 4 and path.startswith(p[1]):
                    if not best or len(p[1]) > len(best[1]):
                        best = (p[1], p[2], p[3])
        if best:
            return "%s (%s) opts=[%s]" % (best[0], best[1], best[2])
    except Exception as e:
        return "mount read failed: %s" % e
    return "unknown-mount"


class TunnelManager:
    def __init__(self):
        self._thread = None
        self._process = None
        self._binary = None

    def start(self):
        binpath = None
        for p in _candidates():
            if os.path.exists(p):
                binpath = p
                break
        if binpath is None:
            state.update(tunnel_error="no cloudflared binary (looked: %s)"
                                      % "; ".join(_candidates()))
            return
        self._binary = binpath
        state.update(tunnel_starting=True, tunnel_url="", tunnel_error="", tunnel_log="")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        from . import state as st
        while True:
            started = False
            for b in _candidates():
                if not os.path.exists(b):
                    continue
                self._binary = b
                proc = self._try_start(st, b)
                if proc is not None:
                    started = True
                    break
            if not started:
                time.sleep(5)
                continue

            self._process = proc
            if proc.stdout:
                lines = []
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        lines.append(line)
                        if len(lines) > 40:
                            lines = lines[-40:]
                        st.update(tunnel_log="\n".join(lines))
                    m = TUNNEL_URL_RE.search(line)
                    if m:
                        st.update(tunnel_url=m.group(0),
                                  tunnel_starting=False,
                                  tunnel_error="")

            try:
                rc = self._process.wait() or 0
            except Exception:
                rc = -1

            if rc != 0:
                lines = []
                try:
                    tail = st.get().get("tunnel_log", "").splitlines()[-25:]
                    lines = tail if lines == [] and tail else lines
                except Exception:
                    pass
                st.update(tunnel_starting=False,
                          tunnel_error="cloudflared exited (rc %s)\n%s"
                          % (rc, "\n".join(lines)))
            time.sleep(5)

    def _try_start(self, st, b):
        try:
            proc = subprocess.Popen(
                [b, "tunnel", "--url", "http://127.0.0.1:%s" % cfg.PORT,
                 "--no-autoupdate"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            st.update(tunnel_error="")
            return proc
        except Exception as e:
            st.update(tunnel_error="cloudflared start failed: %s (%s)\nmount: %s"
                                   % (b, e, _mount_for(b)))
            return None

    def stop(self):
        try:
            if self._process:
                self._process.terminate()
        except Exception:
            pass
        state.update(tunnel_url="", tunnel_starting=False)