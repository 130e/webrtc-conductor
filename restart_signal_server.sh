#!/usr/bin/env bash
set -euo pipefail

REMOTE_BASE="$1"

# Kill any existing peerconnection_server
pkill -f "$REMOTE_BASE/peerconnection_server" || true

# Restart server under systemd-inhibit in background
nohup systemd-inhibit --what=handle-lid-switch:sleep \
    "$REMOTE_BASE/peerconnection_server" \
    >"$REMOTE_BASE/server.log" 2>&1 &

echo "peerconnection_server restarted with systemd-inhibit (pid=$!)"
