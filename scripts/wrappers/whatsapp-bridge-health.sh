#!/usr/bin/env bash
# WhatsApp Bridge Health Monitor
# Checks bridge connectivity on port 3007.
# Only restarts if bridge is truly down — does NOT kill the gateway-managed bridge.
# Called by Hermes cron every 5 minutes.
set -euo pipefail

BRIDGE_URL="http://127.0.0.1:3007"
BRIDGE_DIR="/root/.hermes/hermes-agent/scripts/whatsapp-bridge"
LOG="/root/.hermes/whatsapp/bridge.log"
SESSION_DIR="/root/.hermes/whatsapp/session"

# Check if bridge responds
STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$BRIDGE_URL/health" 2>/dev/null || echo "000")
CONNECTED=$(curl -sf "$BRIDGE_URL/status" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('connected','unknown'))" 2>/dev/null || echo "unknown")

if [ "$STATUS" = "000" ]; then
    echo "BRIDGE DOWN - no response from $BRIDGE_URL. Attempting recovery via gateway restart..."
    # Do NOT pkill bridge — the gateway owns the bridge process.
    # Restart the gateway which will respawn the bridge correctly on port 3007.
    hermes gateway restart 2>/dev/null || true
    sleep 8
    # Verify it came back
    NEW_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$BRIDGE_URL/health" 2>/dev/null || echo "000")
    if [ "$NEW_STATUS" = "200" ]; then
        echo "BRIDGE RECOVERED - gateway restarted, bridge back on 3007."
    else
        # Fallback: start bridge manually ONLY if gateway didn't spawn one
        BRIDGE_PID=$(ss -tlnp | grep ':3007 ' | grep -oP 'pid=\K[0-9]+' | head -1)
        if [ -z "$BRIDGE_PID" ]; then
            echo "BRIDGE STILL DOWN - gateway didn't recover. Starting bridge manually..."
            cd "$BRIDGE_DIR"
            nohup node bridge.js --port 3007 >> "$LOG" 2>&1 &
            sleep 5
            FINAL_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$BRIDGE_URL/health" 2>/dev/null || echo "000")
            if [ "$FINAL_STATUS" = "200" ]; then
                echo "BRIDGE RECOVERED (manual start) on port 3007."
            else
                echo "BRIDGE RECOVERY FAILED - manual start also failed (status=$FINAL_STATUS). Needs human intervention."
            fi
        else
            echo "BRIDGE RECOVERY FAILED - port 3007 occupied but not healthy (PID=$BRIDGE_PID). Manual intervention needed."
        fi
    fi
elif [ "$CONNECTED" = "false" ]; then
    echo "BRIDGE WARNING - bridge process alive but WhatsApp disconnected. May need QR re-scan."
else
    echo "BRIDGE OK - status=$STATUS, connected=$CONNECTED"
fi
