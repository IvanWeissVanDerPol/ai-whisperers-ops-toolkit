#!/usr/bin/env bash
# site-health-with-ntfy.sh — run site-health.sh, alert ntfy if any sites DOWN
# Used by VPS Site Health Check cron (no-agent mode)

set -uo pipefail

HEALTH_SCRIPT="/root/infrastructure/site-health.sh"
NTFY_TOPIC="ai-whisperers-alerts"

OUTPUT=$("${HEALTH_SCRIPT}" 2>&1)
EXIT_CODE=$?

# Count DOWN sites
DOWN_COUNT=$(echo "${OUTPUT}" | grep -c "^\s*\[DOWN\]" || true)

# Save full output to log
LOG_DIR="${HOME}/.hermes/logs"
mkdir -p "${LOG_DIR}"
echo "${OUTPUT}" > "${LOG_DIR}/site-health.log"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | exit=${EXIT_CODE} | down=${DOWN_COUNT}" >> "${LOG_DIR}/site-health-history.log"

# Alert if any sites down
if [ "${DOWN_COUNT}" -gt 0 ]; then
    MSG="⚠️ [sunstein-vps] ${DOWN_COUNT} sitio(s) DOWN. Run 'bash ${HEALTH_SCRIPT}' for details."
    curl -sS -X POST \
        -H "Title: VPS Site Health Alert" \
        -H "Priority: high" \
        -H "Tags: warning,websites" \
        -d "${MSG}" \
        "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null 2>&1
    echo "ALERTED: ${DOWN_COUNT} sites down"
fi

# Exit non-zero if any sites down (so cron delivery is loud)
[ "${DOWN_COUNT}" -eq 0 ] && exit 0 || exit 1
