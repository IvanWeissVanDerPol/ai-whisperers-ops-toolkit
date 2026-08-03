#!/usr/bin/env bash
# LQV daily status — reads PLAN.md + the lqv-pipeline kanban board
# and emits a one-line summary suitable for no_agent cron delivery.
#
# Schedule intent: 0 9 * * * America/Asuncion → Telegram home channel
# Mode: no_agent (script's stdout IS the delivery content)

set -uo pipefail

PLAN="/tmp/lqv-scan/splats/PLAN.md"
TODAY=$(date -u +%Y-%m-%d)
PLY_DIR="/tmp/lqv-scan/splats/exports/ply"
PLY_COUNT=$(ls -1 "${PLY_DIR}"/*.ply 2>/dev/null | wc -l)
WEB_EXISTS="no"
[[ -f /tmp/lqv-scan/splats/exports/web/index.html ]] && WEB_EXISTS="yes"
KANBAN_OPEN=$(hermes kanban list 2>/dev/null | grep -cE 'ready|blocked|running' || echo 0)

cat <<EOF
📅 LQV status — ${TODAY}

• Splat PLYs in exports/: ${PLY_COUNT}
• Buyer URL ready: ${WEB_EXISTS}
• Open kanban tasks: ${KANBAN_OPEN}

Plan: ${PLAN:-(not mounted)}
EOF
