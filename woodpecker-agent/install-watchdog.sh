#!/usr/bin/env bash
# Install the Woodpecker agent watchdog as a systemd timer (every 5 min).
#
# Usage: sudo ./install-watchdog.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

chmod +x "$SCRIPT_DIR/watchdog.sh"
cp "$SCRIPT_DIR/woodpecker-watchdog.service" /etc/systemd/system/
cp "$SCRIPT_DIR/woodpecker-watchdog.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now woodpecker-watchdog.timer

echo "Installed. Status:"
systemctl status woodpecker-watchdog.timer --no-pager | head -5
echo
echo "Logs: journalctl -u woodpecker-watchdog.service -n 20"
