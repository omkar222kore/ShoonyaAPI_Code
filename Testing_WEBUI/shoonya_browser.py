"""Headless-browser login helper for the Shoonya web terminal.

The Shoonya web terminal (https://trade.shoonya.com/) is a Flutter app that
renders to a canvas, so there are no normal HTML inputs to fill. We drive it by
turning on Flutter's accessibility (semantics) tree and then interacting with
the semantic <input>/<button> nodes it exposes.

On a successful login the app calls its QuickAuth endpoint; we read that
response out of Chrome's network log and return the ``susertoken`` (jKey).
"""
import json
import time

LOGIN_URL = "https://trade.shoonya.com/"


def _make_driver(headless=True):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--window-size=1400,1000")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def _glass_shadow(driver, By):
    glass = driver.find_element(By.CSS_SELECTOR, "flt-glass-pane")
    return glass.shadow_root


def _enable_semantics(driver, By):
    """Flutter only builds its accessibility tree after a trusted click on the
    hidden 'Enable accessibility' placeholder. Report its position, then click
    it through CDP so the event is trusted."""
    shadow = _glass_shadow(driver, By)
    ph = shadow.find_element(By.CSS_SELECTOR, "flt-semantics-placeholder")
    driver.execute_script(
        "arguments[0].style.cssText='position:absolute;left:100px;top:100px;"
        "width:40px;height:40px;';",
        ph,
    )
    for kind in ("mousePressed", "mouseReleased"):
        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": kind, "x": 120, "y": 120, "button": "left", "clickCount": 1},
        )
    # wait until the semantics tree exposes the login field
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(1)
        try:
            shadow = _glass_shadow(driver, By)
            if shadow.find_elements(By.CSS_SELECTOR, 'input[aria-label="User ID"]'):
                return True
        except Exception:
            pass
    return False


def _trusted_click(driver, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", element
    )
    rect = driver.execute_script(
        "var r=arguments[0].getBoundingClientRect();"
        "return {x:r.left+r.width/2, y:r.top+r.height/2};",
        element,
    )
    for kind in ("mousePressed", "mouseReleased"):
        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {
                "type": kind,
                "x": int(rect["x"]),
                "y": int(rect["y"]),
                "button": "left",
                "clickCount": 1,
            },
        )


def _fill(driver, element, text):
    # The semantic inputs are transparent overlays, so Selenium refuses to type
    # into them. Instead we give the field a trusted click (Flutter then routes
    # focus to its canvas field) and insert the text through CDP.
    _trusted_click(driver, element)
    time.sleep(0.4)
    driver.execute_cdp_cmd("Input.insertText", {"text": text})
    time.sleep(0.3)


def _scan_for_token(driver, timeout):
    """Poll Chrome's network log for a response body carrying susertoken."""
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            logs = driver.get_log("performance")
        except Exception:
            logs = []
        for entry in logs:
            try:
                msg = json.loads(entry["message"]).get("message", {})
            except Exception:
                continue
            if msg.get("method") != "Network.responseReceived":
                continue
            params = msg.get("params", {})
            rid = params.get("requestId")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            try:
                body = driver.execute_cdp_cmd(
                    "Network.getResponseBody", {"requestId": rid}
                )
                text = body.get("body", "")
            except Exception:
                continue
            if "susertoken" not in text:
                continue
            try:
                data = json.loads(text)
            except Exception:
                continue
            token = data.get("susertoken") or ""
            if token:
                return token
    return ""


def fetch_jkey(uid, pwd, otp, headless=True, timeout=60, log=None):
    """Log into the Shoonya web terminal and return (ok, message, jkey)."""
    def _log(m):
        if log:
            log(m)

    try:
        from selenium.webdriver.common.by import By
    except Exception as e:  # pragma: no cover
        return False, f"Selenium not installed: {e}", ""

    uid = (uid or "").strip()
    pwd = pwd or ""
    otp = (otp or "").strip()
    if not uid or not pwd or not otp:
        return False, "uid/pwd/otp required", ""

    driver = None
    try:
        _log("Launching headless browser...")
        driver = _make_driver(headless=headless)
        driver.execute_cdp_cmd("Network.enable", {})
        driver.get(LOGIN_URL)
        time.sleep(12)

        _log("Enabling accessibility tree...")
        if not _enable_semantics(driver, By):
            return False, "Could not enable the login form (accessibility tree empty)", ""

        shadow = _glass_shadow(driver, By)
        _log("Filling credentials...")
        _fill(driver, shadow.find_element(By.CSS_SELECTOR, 'input[aria-label="User ID"]'), uid)
        _fill(driver, shadow.find_element(By.CSS_SELECTOR, 'input[aria-label="Password"]'), pwd)
        _fill(driver, shadow.find_element(By.CSS_SELECTOR, 'input[aria-label="OTP/TOTP"]'), otp)
        time.sleep(1)

        _log("Submitting login...")
        btn = shadow.find_element(
            By.CSS_SELECTOR, 'flt-semantics[aria-label="Login"][role="button"]'
        )
        _trusted_click(driver, btn)

        _log("Waiting for jKey in network traffic...")
        token = _scan_for_token(driver, timeout)
        if token:
            _log("jkey captured.")
            return True, "ok", token
        return False, "Login failed or jkey not found (check OTP / page changed)", ""
    except Exception as e:
        return False, f"Browser login error: {e}", ""
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
