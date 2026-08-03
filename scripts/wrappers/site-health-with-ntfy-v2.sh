#!/usr/bin/env bash
# site-health-with-ntfy-v2.sh — smart health check with severity filtering
#
# Severity classification:
#   200-399  = UP (no alert)
#   404      = No origin configured (Cloudflare-only, not a real failure)
#   5xx      = DOWN — origin configured but erroring (ALERT)
#   0        = DOWN — connection timeout/refused (ALERT)
#
# Used by VPS Site Health Check cron (no-agent mode)

set -uo pipefail

# Cron no_agent runs without login env — explicitly set HOME
export HOME="/root"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

HEALTH_SCRIPT="/root/infrastructure/site-health.sh"
NTFY_TOPIC="ai-whisperers-alerts"
LOG_DIR="${HOME}/.hermes/logs"

mkdir -p "${LOG_DIR}"

OUTPUT=$("${HEALTH_SCRIPT}" 2>&1)
EXIT_CODE=$?

# Count by severity
DOWN_5XX=$(echo "${OUTPUT}" | grep -E "\[DOWN\].*\(5[0-9][0-9]\)" | wc -l)
DOWN_000=$(echo "${OUTPUT}" | grep -E "\[DOWN\].*\(0\)" | wc -l)
DOWN_404=$(echo "${OUTPUT}" | grep -E "\[DOWN\].*\(404\)" | wc -l)
DOWN_REAL=$((DOWN_5XX + DOWN_000))

# Save full output
echo "${OUTPUT}" > "${LOG_DIR}/site-health.log"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | exit=${EXIT_CODE} | 5xx=${DOWN_5XX} 0=${DOWN_000} 404=${DOWN_404}" \
    >> "${LOG_DIR}/site-health-history.log"

# Alert ONLY for real failures (5xx, 0)
if [ "${DOWN_REAL}" -gt 0 ]; then
    FAILING=$(echo "${OUTPUT}" | grep -E "\[DOWN\].*(\(5[0-9][0-9]\)|\(0\))" | head -20)

    MSG="🚨 VPS Site Health — ${DOWN_REAL} REAL failure(s)
5xx: ${DOWN_5XX} | timeouts: ${DOWN_000} | 404 (no origin): ${DOWN_404}

Failing:
${FAILING}"

    # Truncate to 3800 chars (ntfy limit)
    MSG_TRUNC="${MSG:0:3800}"

    curl -sS -X POST \
        -H "Title: VPS Site Health — Real Failures" \
        -H "Priority: urgent" \
        -H "Tags: rotating_light,websites" \
        -d "${MSG_TRUNC}" \
        "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null 2>&1

    echo "ALERTED: ${DOWN_REAL} real failures (5xx/timeout)"
fi

# Exit 0 if no real failures, 1 if any (so cron delivery is loud)
[ "${DOWN_REAL}" -eq 0 ] && exit 0 || exit 1
