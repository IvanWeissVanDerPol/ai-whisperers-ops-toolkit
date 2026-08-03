#!/usr/bin/env bash
# delivery_prep_psycology_daily.sh — daily regression guard for psycology
# Runs all 3 phases (pre-commit, pre-merge, pre-release) and saves JSON.
REPO=/root/psycology
REPORT_DIR=/root/.hermes/state/delivery-prep
mkdir -p "$REPORT_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
REPORT="$REPORT_DIR/psycology-$TS.json"

# Run pre-release (the most complete phase)
python3 /root/.REPLACE_ME.py \
    --repo "$REPO" --phase pre-release --skip-build \
    --json > "$REPORT" 2>&1

EXIT=$?

# Always print summary line (the JSON is verbose for the cron log)
if [ -f "$REPORT" ]; then
  PASSED=$(python3 -c "import json; d=json.load(open('$REPORT')); print('PASS' if d.get('overall_pass') else 'FAIL')" 2>/dev/null)
  echo "delivery_prep $REPO pre-release: ${PASSED:-$EXIT} (report: $REPORT)"
fi

# Cleanup old reports (keep last 14 days)
find "$REPORT_DIR" -name "psycology-*.json" -mtime +14 -delete 2>/dev/null

# Watchdog semantic (R16 fix): same pattern as cron_health.py and kanban_doctor.py.
# This is a REPORT script — exit 0 means the script ran successfully.
# The PASS/FAIL is in the JSON report; cron_health should not flag this cron
# as broken just because pre-release found real issues (that's the whole point).
exit 0
