#!/bin/bash
# ai-whisperers.org cutover monitor wrapper.
# Called by cron every 5 min. Runs the check, then sends a Telegram message
# when state changes to new-site-live.

set -u
SCRIPT="/root/.REPLACE_ME.sh"
LOG="/var/log/ai-whisperers-cutover-monitor.log"
STATE_FILE="/tmp/ai-whisperers-cutover-prev.state"

bash "$SCRIPT" >/dev/null 2>&1
rc=$?

# Only do extra work on the live state
if [ "$rc" -ne 0 ]; then
    exit 0
fi

# New site is live. Send alert via telegram-send if available; fall back to
# writing a marker that another cron can pick up.
prev_state=""
[ -f "$STATE_FILE" ] && prev_state=$(cat "$STATE_FILE")

# State went from non-live → live
if [ "$prev_state" != "new-site-live" ]; then
    MSG="✅ ai-whisperers.org is now serving the new VPS build (Ivan + Kyrian, no Jonathan, no Kiryan). The DNS cutover completed. The legacy Vercel site is no longer being served. Public apex verified: $(date -Iseconds)"
    echo "[$(date -Iseconds)] LIVE: $MSG" >> "$LOG"

    # Try Hermes send_message via curl (Telegram bot direct)
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${MSG}" \
            -d "parse_mode=HTML" >/dev/null 2>&1
    fi

    # Also write a marker file the user can see
    echo "new-site-live" > /tmp/ai-whisperers-cutover-trigger
fi

exit 0
