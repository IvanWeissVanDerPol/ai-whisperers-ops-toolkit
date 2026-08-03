#!/usr/bin/env bash
# gateway-rss-watchdog
# Restart hermes-gateway.service if the gateway RSS exceeds the threshold (default 1.5GB).
# This addresses the upstream gateway memory-leak pattern that took 491 gateway merges
# in 3 months to keep patching. We can patch the symptom (RSS growth) without waiting
# for upstream fixes.
#
# Usage:
#   gateway-rss-watchdog.sh [rss_threshold_mb] [cooldown_seconds]
# Defaults: 1536 MB threshold, 600s cooldown between restarts.
set -eo pipefail

# HOME may be unset in cron context; default to /root
HOME="${HOME:-/root}"
export HOME

THRESHOLD_MB="${1:-1536}"
COOLDOWN_SECONDS="${2:-600}"
SERVICE="hermes-gateway.service"
STATE_DIR="${HOME}/.hermes/state"
LOG="${STATE_DIR}/gateway-watchdog.log"
LAST_RESTART_FILE="${STATE_DIR}/gateway-watchdog.last-restart"

mkdir -p "${STATE_DIR}"

# Find the gateway main process. systemd has the canonical one; orphan user-systemd
# ones should not exist (we stop them at the source via user@0.service being stopped).
PID="$(systemctl show -p MainPID --value "${SERVICE}" 2>/dev/null || true)"
if [[ -z "${PID}" || "${PID}" == "0" ]]; then
  echo "[$(date -Is)] service not running, skipping" | tee -a "${LOG}"
  exit 0
fi

# Read RSS in KB, convert to MB
if ! [[ -r "/proc/${PID}/status" ]]; then
  echo "[$(date -Is)] cannot read /proc/${PID}/status" | tee -a "${LOG}"
  exit 0
fi
RSS_KB="$(awk '/^VmRSS:/ {print $2}' "/proc/${PID}/status" 2>/dev/null || echo 0)"
RSS_MB=$((RSS_KB / 1024))

echo "[$(date -Is)] gateway PID=${PID} RSS=${RSS_MB}MB threshold=${THRESHOLD_MB}MB"

if (( RSS_MB < THRESHOLD_MB )); then
  exit 0
fi

# Cooldown
if [[ -f "${LAST_RESTART_FILE}" ]]; then
  LAST="$(cat "${LAST_RESTART_FILE}")"
  NOW="$(date +%s)"
  ELAPSED=$((NOW - LAST))
  if (( ELAPSED < COOLDOWN_SECONDS )); then
    echo "[$(date -Is)] above threshold but cooldown not elapsed (${ELAPSED}s < ${COOLDOWN_SECONDS}s)" | tee -a "${LOG}"
    exit 0
  fi
fi

# Restart
echo "[$(date -Is)] RESTARTING ${SERVICE} (RSS ${RSS_MB}MB >= ${THRESHOLD_MB}MB)" | tee -a "${LOG}"
date +%s > "${LAST_RESTART_FILE}"
systemctl restart "${SERVICE}" 2>&1 | tee -a "${LOG}"
