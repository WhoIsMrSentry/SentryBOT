#!/usr/bin/env bash
set -euo pipefail
ROOT="${SENTRYBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PIPER_TR_MODEL_URL="${PIPER_TR_MODEL_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx}"
PIPER_TR_CONFIG_URL="${PIPER_TR_CONFIG_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx.json}"
DOWNLOAD_EN="${DOWNLOAD_EN:-0}"
mkdir -p "$ROOT/data/piper_models/tr_TR-dfki-medium" "$ROOT/data/downloads"
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

python_bin="$ROOT/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then python_bin="python3"; fi
"$python_bin" "$ROOT/tools/pi_runtime_readiness.py"
cat <<EOF
PI_MODEL_LAYOUT_OK
piper=$ROOT/data/piper_models/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx
imx500=/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk
EOF
