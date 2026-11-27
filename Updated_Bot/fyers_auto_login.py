import sys

from Login_Fyers import login_once

try:
    login_once()
except Exception as exc:
    print(f"FYERS login failed: {exc}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
