# Shoonya Bot ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Phone APK (python-for-android)

One Android app: your Shoonya sell-bot **runs on the phone itself** (as the server),
receives Chartink webhooks, places orders, and streams PnL to the dashboard.
Tunnel = free cloudflared quick-tunnel (URL changes on restart).

## Layout

```
main.py              Kivy launcher/status screen (open dashboard, copy URL, start/stop service)
myservice/main.py    Android background service -> runs Flask + tunnel (watchdog restarts both)
bot/                 ported engine (no pandas -> openpyxl; token auth; cloudflared manager)
  templates/ static/ dashboard (index.html + js/css) with login overlay
  assets/            NSE_symbols_filtered.xlsx + cloudflared.bin (arm64)
buildozer.spec       p4a build config (arm64-v8a only)
setup_wsl_build.sh   one-time WSL dependency installer
```

## Build (WSL2)

1. `wsl --install` (admin, once), then reboot.
2. Inside Ubuntu: `bash /mnt/d/AlgoRepo/ShoonyaAPI_Code/Android_BOT/setup_wsl_build.sh`
3. `cd /mnt/d/AlgoRepo/ShoonyaAPI_Code/Android_BOT && buildozer android debug`
   (first build downloads the Android SDK/NDK, several GB, run it with a long `-p` timeout)
4. Copy the artifact: `cp bin/*.apk /mnt/d/AlgoRepo/ShoonyaAPI_Code/Android_BOT/`

APK landing zone on Windows: `D:\AlgoRepo\ShoonyaAPI_Code\Android_BOT\`

## Install / run on the phone

1. Sideload `shoonyabot-0.1.0-arm64-v8a-debug.apk`.
2. Open **Shoonya Bot**, tap **START BOT SERVICE**, keep phone on charge, screen off.
3. Tap **OPEN DASHBOARD** -> enter dashboard password (see `bot/config.py` `AUTH_TOKEN`) ->
   paste SuperToken (+ Shoonya password first time) -> START.
4. Copy the WEBHOOK URL shown in the dashboard into Chartink.
   It ends with `?token=<your dashboard password>` - keep that suffix.

## Notes / limits

- Dashboard password = your Shoonya broker password (from `cred.yml`), set as `AUTH_TOKEN` in `bot/config.py`.
- Free tunnel URL changes on tunnel restart -> re-paste into Chartink (dashboard shows a reminder).
- Bot keeps the screen truly alive: foreground service + wakelock. Phone must stay plugged in.
- `NSE_symbols_filtered.xlsx` is embedded; refresh it before a build if the list changed.
- Broker password is written to app-private storage on first login (not baked into the APK).