#!/usr/bin/env bash
# Basit kılavuz: Python yükleyiciyi çağırır.
# Windows kullanıyorsanız PowerShell'de: py -3 install_all_requirements.py

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Geçerli dizin: $SCRIPT_DIR"
$PYTHON_BIN install_all_requirements.py "$@"
