#!/usr/bin/env bash
# SentryBOT otomatik gereksinim kurucu (uv destekli)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# uv aracını bulabilmesi için PATH'i tanımla
export PATH="$HOME/.local/bin:$PATH"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Depo kökü: $REPO_ROOT"

# Ekstra parametre verilmediyse otomatik olarak depo kökündeki .venv sanal ortamını kullan
if [[ "$*" == *"--use-venv"* ]]; then
    "$PYTHON_BIN" "$REPO_ROOT/scripts/install_all_requirements.py" "$@"
else
    "$PYTHON_BIN" "$REPO_ROOT/scripts/install_all_requirements.py" --use-venv --venv-path .venv "$@"
fi