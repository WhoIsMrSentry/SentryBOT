#!/usr/bin/env bash
# SentryBOT otomatik gereksinim kurucu (uv destekli)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# uv aracını bulabilmesi için PATH'i tanımla
export PATH="$HOME/.local/bin:$PATH"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Geçerli dizin: $SCRIPT_DIR"

# Ekstra parametre verilmediyse otomatik olarak uv sanal ortamını kullan
if [[ "$*" == *"--use-venv"* ]]; then
    $PYTHON_BIN install_all_requirements.py "$@"
else
    $PYTHON_BIN install_all_requirements.py --use-venv --venv-path scripts/venv "$@"
fi