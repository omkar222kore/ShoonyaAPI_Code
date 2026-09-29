#!/usr/bin/env bash
set -u
LOG=/mnt/d/AlgoRepo/ShoonyaAPI_Code/Android_BOT/build2.log

for p in $(pgrep -f "[b]uildozer"); do kill "$p" 2>/dev/null; done
sleep 1

rm -rf /root/phone-server-apk/.buildozer/android/platform/build-arm64-v8a/build/venv

cp /mnt/d/AlgoRepo/ShoonyaAPI_Code/Android_BOT/buildozer.spec /root/phone-server-apk/buildozer.spec

export DEBIAN_FRONTEND=noninteractive
export PIP_BREAK_SYSTEM_PACKAGES=1
export PIP_ROOT_USER_ACTION=ignore
export CLOUDFLARED_BIN_PATH=/root/phone-server-apk/bot/assets/cloudflared.bin

echo "=== BUILD START $(date -u) ===" > "$LOG"
cd /root/phone-server-apk

buildozer android debug >> "$LOG" 2>&1
echo "=== BUILD EXIT $? $(date -u) ===" >> "$LOG"