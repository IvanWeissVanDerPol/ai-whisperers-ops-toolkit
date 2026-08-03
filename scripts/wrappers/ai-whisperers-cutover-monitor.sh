#!/bin/bash
# ai-whisperers.org cutover monitor
# Polls the live mirror at https://ai-whisperers.paragu-ai.com/en/about every 5 min.
# Alerts via the cron when the new VPS site is live (defined as: HTTP 200, body
# contains "2 founder-led" + "Ivan Weiss" + "Kyrian Weiss", AND does NOT contain
# "Jonathan Verdun" or "Kiryan Weiss").
#
# The mirror is live NOW (since the apex DNS is stuck), so this monitor will
# see "new-site-live" immediately. It still polls every 5 min to detect any
# regression or loss of the new content.
#
# Exit codes:
#   0 = new site live
#   1 = still legacy / unexpected content
#   2 = network error
#   3 = apex down

set -u
URL="https://ai-whisperers.paragu-ai.com/en/about"
LOG="/var/log/ai-whisperers-cutover-monitor.log"

mkdir -p "$(dirname "$LOG")"

prev_state_file="/tmp/ai-whisperers-cutover-prev.state"
prev_state=""
[ -f "$prev_state_file" ] && prev_state="$(cat "$prev_state_file")"

# Fetch with timeout
http_code=$(curl -sk -L -o /tmp/aw-body.html -w "%{http_code}" --max-time 10 "$URL" 2>/dev/null)
if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
    if [ "$prev_state" != "network-error" ]; then
        echo "[$(date -Iseconds)] network-error (apex not reachable)" >> "$LOG"
    fi
    echo "network-error" > "$prev_state_file"
    exit 2
fi

# Non-200
if [ "$http_code" != "200" ]; then
    if [ "$prev_state" != "apex-down" ]; then
        echo "[$(date -Iseconds)] apex-down (HTTP $http_code)" >> "$LOG"
    fi
    echo "apex-down" > "$prev_state_file"
    exit 3
fi

body=$(cat /tmp/aw-body.html)

has_ivan=$(echo "$body" | grep -c "Ivan Weiss" || true)
has_kyrian=$(echo "$body" | grep -c "Kyrian Weiss" || true)
has_two_founder=$(echo "$body" | grep -c "2 founder-led" || true)
has_jonathan=$(echo "$body" | grep -ciE "jonathan verdun" || true)
has_kiryan=$(echo "$body" | grep -ciE "kiryan weiss" || true)

state="unknown"
if [ "$has_jonathan" -gt 0 ] || [ "$has_kiryan" -gt 0 ]; then
    state="legacy"
elif [ "$has_ivan" -gt 0 ] && [ "$has_kyrian" -gt 0 ] && [ "$has_two_founder" -gt 0 ]; then
    state="new-site-live"
else
    state="other-200"
fi

if [ "$state" != "$prev_state" ]; then
    echo "[$(date -Iseconds)] state: $prev_state → $state (ivan=$has_ivan kyrian=$has_kyrian two=$has_two_founder jonathan=$has_jonathan kiryan=$has_kiryan http=$http_code)" >> "$LOG"
    echo "$state" > "$prev_state_file"
fi

if [ "$state" = "new-site-live" ]; then
    exit 0
else
    exit 1
fi
