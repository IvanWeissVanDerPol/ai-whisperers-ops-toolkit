#!/bin/bash
# Watchdog for Hermes Workspace API proxy
# Restarts it if it's not running
if ! pgrep -f "python3 /opt/hermes-workspace-proxy.py" > /dev/null 2>&1; then
    python3 /opt/hermes-workspace-proxy.py &
    echo "[$(date)] Workspace proxy restarted (bind 0.0.0.0:8788)"
fi
