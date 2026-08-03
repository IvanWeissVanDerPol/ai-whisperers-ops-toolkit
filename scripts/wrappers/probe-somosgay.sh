#!/usr/bin/env bash
# Probe somosgay.paragu-ai.com and emit a status line.
# Used by cronjob (no_agent mode) — the cron runner handles Telegram delivery.
#
# Watchdog pattern: stay silent when healthy, alert when broken.
# Output contract:
#   - exit 0 + no stdout  → healthy (silent)
#   - exit 1 + 🚨 message  → unhealthy (delivered by cron)

set -u

SITE="https://somosgay.paragu-ai.com"
HEALTH="${SITE}/api/healthz"
TIMEOUT=10

status=$(curl -sS -o /tmp/probe-somosgay.body -w "%{http_code}" --max-time "$TIMEOUT" "$HEALTH" 2>/dev/null || echo "000")

if [[ "$status" == "200" ]] && grep -q '"status":"ok"' /tmp/probe-somosgay.body 2>/dev/null; then
  exit 0  # healthy — silent
fi

body_preview=$(head -c 200 /tmp/probe-somosgay.body 2>/dev/null | tr '\n' ' ')
echo "🚨 somosgay.paragu-ai.com DOWN — HTTP $status — body: ${body_preview:-<empty>} — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit 1