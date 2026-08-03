#!/usr/bin/env bash
# Weekly cron: re-detect alias mismatches + auto-apply Traefik labels for new ones
# Idempotent: skips if label already exists

set -euo pipefail

bash /root/.hermes/scripts/fleet-alias-traefik.sh 2>&1 | tail -20
