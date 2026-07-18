#!/usr/bin/env bash
set -euo pipefail
ROOT="${SENTRYBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VOSK_TR_URL="${VOSK_TR_URL:-https://alphacephei.com/vosk/models/vosk-model-small-tr-0.3.zip}"
VOSK_EN_URL="${VOSK_EN_URL:-https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip}"
PIPER_TR_MODEL_URL="${PIPER_TR_MODEL_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx}"
PIPER_TR_CONFIG_URL="${PIPER_TR_CONFIG_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx.json}"
DOWNLOAD_EN="${DOWNLOAD_EN:-0}"
mkdir -p "$ROOT/data/piper_models/tr_TR-dfki-medium" "$ROOT/modules/speech/models" "$ROOT/data/downloads"
fetch() {
  local url="$1" dest="$2"
  if [[ -s "$dest" ]]; then
    echo "EXISTS $dest"
    return 0
  fi
  echo "DOWNLOAD $url -> $dest"
  curl -L --fail --retry 3 --connect-timeout 20 -o "$dest.tmp" "$url"
  mv "$dest.tmp" "$dest"
}
fetch "$PIPER_TR_MODEL_URL" "$ROOT/data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx"
fetch "$PIPER_TR_CONFIG_URL" "$ROOT/data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx.json"
if [[ ! -d "$ROOT/modules/speech/models/vosk-tr" || -z "$(find "$ROOT/modules/speech/models/vosk-tr" -mindepth 1 -maxdepth 1 2>/dev/null || true)" ]]; then
  fetch "$VOSK_TR_URL" "$ROOT/data/downloads/vosk-tr.zip"
  rm -rf "$ROOT/data/downloads/vosk-tr-unpack"
  mkdir -p "$ROOT/data/downloads/vosk-tr-unpack"
  unzip -q "$ROOT/data/downloads/vosk-tr.zip" -d "$ROOT/data/downloads/vosk-tr-unpack"
  first_dir="$(find "$ROOT/data/downloads/vosk-tr-unpack" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  rm -rf "$ROOT/modules/speech/models/vosk-tr"
  mv "$first_dir" "$ROOT/modules/speech/models/vosk-tr"
fi
if [[ "$DOWNLOAD_EN" == "1" ]]; then
  if [[ ! -d "$ROOT/modules/speech/models/vosk-en" || -z "$(find "$ROOT/modules/speech/models/vosk-en" -mindepth 1 -maxdepth 1 2>/dev/null || true)" ]]; then
    fetch "$VOSK_EN_URL" "$ROOT/data/downloads/vosk-en.zip"
    rm -rf "$ROOT/data/downloads/vosk-en-unpack"
    mkdir -p "$ROOT/data/downloads/vosk-en-unpack"
    unzip -q "$ROOT/data/downloads/vosk-en.zip" -d "$ROOT/data/downloads/vosk-en-unpack"
    first_dir="$(find "$ROOT/data/downloads/vosk-en-unpack" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    rm -rf "$ROOT/modules/speech/models/vosk-en"
    mv "$first_dir" "$ROOT/modules/speech/models/vosk-en"
  fi
fi
python_bin="$ROOT/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then python_bin="python3"; fi
"$python_bin" "$ROOT/tools/pi_runtime_readiness.py"
cat <<EOF
PI_MODEL_LAYOUT_OK
piper=$ROOT/data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx
vosk_tr=$ROOT/modules/speech/models/vosk-tr
imx500=/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk
EOF
