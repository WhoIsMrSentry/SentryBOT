#!/usr/bin/env bash
set -euo pipefail
ROOT="${SENTRYBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-sentrybot.service}"
if [[ "$(uname -s)" != "Linux" ]]; then echo "ERROR: Linux/systemd required" >&2; exit 2; fi
if [[ "${EUID}" -ne 0 ]]; then echo "ERROR: run with sudo" >&2; exit 2; fi
install -d /etc/sentrybot
if [[ ! -f /etc/sentrybot/sentrybot.env ]]; then
  sed "s#__PROJECT_ROOT__#$ROOT#g" "$ROOT/deploy/systemd/sentrybot.env.example" > /etc/sentrybot/sentrybot.env
fi
sed "s#__PROJECT_ROOT__#$ROOT#g" "$ROOT/deploy/systemd/sentrybot.service" > "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
cat <<EOF
SYSTEMD_INSTALL_OK
service=$SERVICE_NAME
env=/etc/sentrybot/sentrybot.env
start=sudo systemctl start $SERVICE_NAME
status=sudo systemctl status $SERVICE_NAME --no-pager
logs=journalctl -u $SERVICE_NAME -f
EOF
