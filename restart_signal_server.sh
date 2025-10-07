#!/usr/bin/env bash
set -euo pipefail

REMOTE_BASE="$1"
PORT="$2"

# Kill any existing peerconnection_server running on this port
# Using lsof to find processes listening on the port
pids=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [ -n "$pids" ]; then
    echo "Killing existing peerconnection_server on port $PORT: $pids"
    kill -9 $pids
fi

# Start server in background, detached from terminal
nohup "$REMOTE_BASE/peerconnection_server" --port="$PORT" >"$REMOTE_BASE/server.log" 2>&1 &
echo "peerconnection_server restarted on port $PORT (pid=$!)"
