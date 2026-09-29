"""Desktop smoke-test: runs the ported server on the PC before APK build."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import server
from bot import state
from bot import tunnel

if __name__ == "__main__":
    print("Assets:", server.cfg.ASSETS_DIR)
    print("Excel exists:", os.path.exists(server.cfg.EXCEL_FILE))
    print("Auth token set:", bool(server.cfg.AUTH_TOKEN))
    TunnelManager().start()
    server.run()