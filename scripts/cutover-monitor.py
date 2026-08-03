#!/bin/bash
# ai-whisperers.org cutover monitor
# Polls /en/about every 5 min. Alerts via Telegram the moment the new VPS site goes live
# (defined as: HTTP 200, body contains "2 founder-led" + "Ivan Weiss" + "Kyrian Weiss",
# AND does NOT contain "Jonathan Verdun" or "Kiryan Weiss").
#
# Exit codes:
#   0 = new site live (alert sent)
#   1 = still legacy (silent)
#   2 = network error (silent)
#   3 = apex down (silent)

set -u
URL="https://ai-whisperers.org/en/about"
TG_BOT_TOKEN="__TG_BOT_TOKEN__"  # not actually used; we use Hermes send_message
LOG="/var/log/ai-whisperers-cutover-monitor.log"

mkdir -p "$(dirname "$LOG")"

# Quiet logging — only log state changes, not every poll
prev_state_file="/tmp/ai-whisperers-cutover-prev.state"
prev_state=""
[ -f "$prev_state_file" ] && prev_state="$(cat "$prev_state_file")"

# Fetch with timeout
body=""
http_code=""
http_code=$(curl -sk -L -o /tmp/aw-body.html -w "%{http_code}" --max-time 10 "$URL" 2>/dev/null)
if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
    [ "$prev_state" != "network-error" ] && echo "[$(date -Iseconds)] network-error (apex not reachable)" >> "$LOG"
    echo "network-error" > "$prev_state_file"
    exit 2
fi

# Apex down (404, 5xx)
if [ "$http_code" != "200" ]; then
    [ "$prev_state" != "apex-down" ] && echo "[$(date -Iseconds)] apex-down (HTTP $http_code)" >> "$LOG"
    echo "apex-down" > "$prev_state_file"
    exit 3
fi

body=$(cat /tmp/aw-body.html)

# Check the content
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

# Only log on state change
if [ "$state" != "$prev_state" ]; then
    echo "[$(date -Iseconds)] state: $prev_state → $state (ivan=$has_ivan kyrian=$has_kyrian two=$has_two_founder jonathan=$has_jonathan kiryan=$has_kiryan http=$http_code)" >> "$LOG"
    echo "$state" > "$prev_state_file"
fi

# Exit code 0 only when new site is live
if [ "$state" = "new-site-live" ]; then
    exit 0
else
    exit 1
fi
