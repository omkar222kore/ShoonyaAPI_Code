#!/usr/bin/env bash
set -euo pipefail
echo ">>> Installing buildozer build dependencies (Ubuntu/WSL)..."
sudo apt-get update
sudo apt-get install -y \
  python3-pip python3-venv python3-dev \
  zip unzip openjdk-17-jdk \
  autoconf libtool pkg-config \
  zlib1g-dev libffi-dev libssl-dev \
  cmake git curl wget ccache build-essential
echo ">>> Installing buildozer..."
pip3 install --user --upgrade buildozer
echo ">>> Done. Now run:"
echo "      cd /mnt/d/AlgoRepo/ShoonyaAPI_Code/Android_BOT"
echo "      buildozer android debug"
echo "    First build downloads Android SDK/NDK (several GB) and takes a while."