import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CRED = os.path.join(ROOT, "cred.yml")
DEFAULT_TOKEN = os.path.join(ROOT, "super_token.txt")
LOGIN_URL = "https://trade.shoonya.com/"

yaml = None
pyotp = None


def _err(message):
    print(message, file=sys.stderr)


def _ensure_deps():
    global yaml, pyotp
    missing = []
    try:
        import yaml as loaded_yaml

        yaml = loaded_yaml
    except Exception:
        missing.append("PyYAML")
    try:
        import pyotp as loaded_pyotp

        pyotp = loaded_pyotp
    except Exception:
        missing.append("pyotp")
    try:
        import selenium
    except Exception:
        missing.append("selenium")
    if missing:
        _err(f"Installing dependencies: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        import yaml as loaded_yaml
        import pyotp as loaded_pyotp

        yaml = loaded_yaml
        pyotp = loaded_pyotp


def _load_cred(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=yaml.FullLoader) or {}


def _otp(cred, override):
    if override and override.isdigit() and len(override) == 6:
        return override
    env_otp = os.environ.get("SHOONYA_OTP", "")
    if env_otp.isdigit() and len(env_otp) == 6:
        return env_otp
    saved = str(cred.get("otp", "")).strip()
    if saved.isdigit() and len(saved) == 6:
        return saved
    factor2 = str(os.environ.get("SHOONYA_FACTOR2") or cred.get("factor2") or "").strip()
    if not factor2:
        return ""
    try:
        return pyotp.TOTP(factor2.replace(" ", "")).now()
    except Exception as exc:
        _err(f"TOTP error: {exc}")
        return ""


def _make_driver(headless):
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
    return driver.find_element(By.CSS_SELECTOR, "flt-glass-pane").shadow_root


def _enable_semantics(driver, By):
    shadow = _glass_shadow(driver, By)
    placeholder = shadow.find_element(By.CSS_SELECTOR, "flt-semantics-placeholder")
    driver.execute_script(
        "arguments[0].style.cssText='position:absolute;left:100px;top:100px;"
        "width:40px;height:40px;';",
        placeholder,
    )
    for kind in ("mousePressed", "mouseReleased"):
        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": kind, "x": 120, "y": 120, "button": "left", "clickCount": 1},
        )
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
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
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
    _trusted_click(driver, element)
    time.sleep(0.4)
    driver.execute_cdp_cmd("Input.insertText", {"text": text})
    time.sleep(0.3)


def _scan_for_token(driver, timeout):
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
                message = json.loads(entry["message"]).get("message", {})
            except Exception:
                continue
            if message.get("method") != "Network.responseReceived":
                continue
            request_id = message.get("params", {}).get("requestId")
            if not request_id or request_id in seen:
                continue
            seen.add(request_id)
            try:
                body = driver.execute_cdp_cmd(
                    "Network.getResponseBody", {"requestId": request_id}
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


def _login(uid, pwd, otp, headless, timeout):
    from selenium.webdriver.common.by import By

    driver = _make_driver(headless)
    driver.execute_cdp_cmd("Network.enable", {})
    driver.get(LOGIN_URL)
    time.sleep(12)

    _err("Enabling accessibility tree...")
    if not _enable_semantics(driver, By):
        _err("Login form could not be enabled.")
        return driver, ""

    shadow = _glass_shadow(driver, By)
    _err("Filling credentials...")
    _fill(driver, shadow.find_element(By.CSS_SELECTOR, 'input[aria-label="User ID"]'), uid)
    _fill(driver, shadow.find_element(By.CSS_SELECTOR, 'input[aria-label="Password"]'), pwd)
    _fill(driver, shadow.find_element(By.CSS_SELECTOR, 'input[aria-label="OTP/TOTP"]'), otp)
    time.sleep(1)

    _err("Submitting login...")
    button = shadow.find_element(
        By.CSS_SELECTOR, 'flt-semantics[aria-label="Login"][role="button"]'
    )
    _trusted_click(driver, button)

    _err("Waiting for super token...")
    return driver, _scan_for_token(driver, timeout)


def main():
    parser = argparse.ArgumentParser(description="Automatically log in to Shoonya and save the super token.")
    parser.add_argument("--cred", default=DEFAULT_CRED, help="Path to cred.yml")
    parser.add_argument("--otp", default="", help="Optional 6-digit OTP override")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--save", nargs="?", const=DEFAULT_TOKEN, default=DEFAULT_TOKEN)
    args = parser.parse_args()

    try:
        _ensure_deps()
    except Exception as exc:
        _err(f"Dependency setup failed: {exc}")
        return 1

    cred_path = os.path.abspath(args.cred)
    cred = _load_cred(cred_path)
    if not cred:
        _err(f"Missing or empty credential file: {cred_path}")
        return 2

    uid = os.environ.get("SHOONYA_USER") or cred.get("user", "")
    pwd = os.environ.get("SHOONYA_PASSWORD") or os.environ.get("SHOONYA_PWD") or cred.get("pwd", "")
    otp = _otp(cred, args.otp)

    if not all([uid, pwd, otp]):
        _err("Missing user/pwd/factor2. Fill cred.yml beside this script or use SHOONYA_* env vars.")
        return 2

    driver = None
    try:
        driver, token = _login(uid, pwd, otp, args.headless, args.timeout)
    except Exception as exc:
        _err(f"Login error: {exc}")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        return 1

    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass

    if not token:
        _err("Login completed but no super token was captured.")
        return 1

    token = token.strip()
    if args.save:
        path = os.path.abspath(args.save)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        _err(f"Token saved to {path}")
    print(token)
    _err("Login completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
