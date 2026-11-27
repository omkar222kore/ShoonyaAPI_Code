import base64, datetime, email.utils, json, os, sys, time, urllib.error, urllib.parse, urllib.request, pyotp
from fyers_apiv3 import fyersModel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_PATH  = os.path.join(SCRIPT_DIR, "fyers_creds.json")
VAGATOR    = "https://" + ".".join(["api-t2", "fyers", "in"]) + "/vagator/v2"
API_T1     = "https://" + ".".join(["api-t1", "fyers", "in"]) + "/api/v3"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(NoRedirect)

def post_json(url, payload, bearer=None):
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with OPENER.open(req, timeout=20) as resp:
            srv_date = resp.headers.get("Date")
            offset = (email.utils.parsedate_to_datetime(srv_date).timestamp() - time.time()) if srv_date else 0.0
            return json.loads(resp.read().decode("utf-8")), offset
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        if e.code in (301, 302, 307, 308):
            return json.loads(raw), 0.0
        raise RuntimeError(f"HTTP {e.code} on {url} -> {raw}")

def login_once():
    if not os.path.exists(CRED_PATH):
        raise FileNotFoundError(f"Missing {CRED_PATH}")
    with open(CRED_PATH, "r", encoding="utf-8") as f:
        C = json.load(f)

    r1, offset = post_json(f"{VAGATOR}/send_login_otp_v2", {"fy_id": base64.b64encode(C["FYERS_ID"].encode()).decode(), "app_id": "2"})
    srv_now = time.time() + offset
    if (srv_now % 30) > 25:
        time.sleep(6)
        srv_now = time.time() + offset

    otp = pyotp.TOTP(C["TOTP_SECRET"]).at(datetime.datetime.fromtimestamp(srv_now, tz=datetime.timezone.utc))
    r2, _ = post_json(f"{VAGATOR}/verify_otp", {"request_key": r1["request_key"], "otp": str(otp)})
    r3, _ = post_json(f"{VAGATOR}/verify_pin_v2", {"request_key": r2["request_key"], "identity_type": "pin", "identifier": base64.b64encode(str(C["PIN"]).encode()).decode()})

    app_id_only = C["CLIENT_ID"].replace("-100", "")
    r4, _ = post_json(f"{API_T1}/token", {
        "fyers_id": C["FYERS_ID"], "app_id": app_id_only, "redirect_uri": C["REDIRECT_URI"],
        "appType": "100", "code_challenge": "", "state": "None", "scope": "", "nonce": "", "response_type": "code", "create_cookie": True
    }, bearer=r3["data"]["access_token"])

    redirect_url = r4.get("Url") or r4.get("url")
    auth_code = next(iter(urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)["auth_code"]))

    session = fyersModel.SessionModel(client_id=C["CLIENT_ID"], secret_key=C["SECRET_KEY"], redirect_uri=C["REDIRECT_URI"], response_type="code", grant_type="authorization_code")
    session.set_token(auth_code)
    access_token = session.generate_token()["access_token"].strip()

    # Verify the new token actually works via get_profile() before saving
    fyers = fyersModel.FyersModel(client_id=C["CLIENT_ID"], token=access_token, is_async=False)
    prof = fyers.get_profile()
    if prof.get("s") != "ok":
        raise RuntimeError(f"Profile verification failed: {prof}")

    for target in dict.fromkeys([os.path.join(SCRIPT_DIR, "token.txt"), os.path.join(os.path.dirname(SCRIPT_DIR), "token.txt")]):
        with open(target, "w", encoding="utf-8") as f:
            f.write(access_token)
        print(f"VERIFIED FYERS token ({prof['data'].get('name')}) -> {target}")

def main():
    for attempt in range(1, 4):
        try:
            login_once()
            sys.exit(0)
        except Exception as exc:
            print(f"[Attempt {attempt}/3] Login warning: {exc}", file=sys.stderr)
            if attempt < 3:
                time.sleep(10)
    sys.exit(1)

if __name__ == "__main__":
    main()
