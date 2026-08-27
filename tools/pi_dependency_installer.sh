#!/usr/bin/env bash
set -euo pipefail
ROOT="${SENTRYBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
FORCE="${FORCE:-0}"
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: this installer must run on Raspberry Pi OS / Linux" >&2
  exit 2
fi
MODEL="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
if [[ "$FORCE" != "1" && "$MODEL" != *"Raspberry Pi"* ]]; then
  echo "ERROR: Raspberry Pi hardware not detected. model='$MODEL'" >&2
  echo "Set FORCE=1 only if you are running a compatible Pi image in a special environment." >&2
  exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run with sudo" >&2
  exit 2
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip python3-dev python3-setuptools python3-wheel \
  python3-picamera2 python3-opencv python3-numpy python3-munkres \
  imx500-all rpicam-apps libcamera-apps \
  alsa-utils pulseaudio-utils espeak-ng ffmpeg curl wget unzip git jq \
  libportaudio2 portaudio19-dev build-essential libatlas-base-dev
python3 -m venv "$ROOT/.venv" --system-site-packages
"$ROOT/.venv/bin/python" -m pip install --upgrade pip wheel setuptools
REQS=(
  "$ROOT/requirements.txt"
  "$ROOT/modules/speak/requirements.txt"
  "$ROOT/modules/wakeword/requirements.txt"
  "$ROOT/modules/speech/requirements.txt"
  "$ROOT/modules/agent_core/requirements.txt"
)
for req in "${REQS[@]}"; do
  if [[ -f "$req" ]]; then
    "$ROOT/.venv/bin/python" -m pip install -r "$req"
  fi
done
"$ROOT/.venv/bin/python" -m pip install SpeechRecognition openwakeword sounddevice soundfile piper-tts requests pyyaml fastapi uvicorn || true
mkdir -p "$ROOT/data/piper_models" "$ROOT/data/logs" "$ROOT/data/runtime"
chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$ROOT/.venv" "$ROOT/data" || true
cat <<EOF
PI_DEPENDENCY_INSTALL_OK
root=$ROOT
model=$MODEL
next=run tools/pi_model_downloader_layout.sh
EOF
