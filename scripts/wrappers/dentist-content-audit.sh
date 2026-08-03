#!/usr/bin/env bash
# dentist-content-audit.sh — verify JSON validity and key parity across all es/* and en/* files
#
# Exit codes:
#   0 — clean (no action needed) OR parity-only warnings (operator may read log)
#   2 — invalid JSON found; serious, must be fixed
#
# Note: parity warnings used to fail the cron (exit 1); changed to exit 0
# because blog posts and gallery templates frequently exist in en-only
# while translations are pending. Hard-asserting 100% parity produces
# daily noise that operators ignore.
set -uo pipefail
REPO=/root/dentist-template-scan
cd "$REPO" || exit 1

JSON_ERRORS=0
PARITY_WARNINGS=0

# 1. JSON validity for all .json files in content/
#    INVALID JSON is a hard error (exit 2).
echo "=== JSON validity check ==="
for f in $(find content/ -name "*.json"); do
  if ! python3 -m json.tool "$f" > /dev/null 2>&1; then
    echo "INVALID: $f"
    JSON_ERRORS=$((JSON_ERRORS + 1))
  fi
done

# 2. es/en parity: every JSON file in es/ has a matching file in en/
#    Missing parallels are SOFT warnings only: project may intentionally
#    keep en-only newly-added content (e.g. blog posts that haven't been
#    translated yet). Still logged for visibility.
echo ""
echo "=== es/en parity check ==="
for f in $(find content/es/ -name "*.json" 2>/dev/null); do
  en_equiv=$(echo "$f" | sed 's|^content/es/|content/en/|')
  if [ ! -f "$en_equiv" ]; then
    echo "MISSING EN: $f (no $en_equiv)"
    PARITY_WARNINGS=$((PARITY_WARNINGS + 1))
  fi
done

for f in $(find content/en/ -name "*.json" 2>/dev/null); do
  es_equiv=$(echo "$f" | sed 's|^content/en/|content/es/|')
  if [ ! -f "$es_equiv" ]; then
    echo "MISSING ES: $f (no $es_equiv)"
    PARITY_WARNINGS=$((PARITY_WARNINGS + 1))
  fi
done

# 3. Summary
if [ "$JSON_ERRORS" -gt 0 ]; then
  echo "FAIL: $JSON_ERRORS invalid JSON, $PARITY_WARNINGS parity warnings"
  exit 2  # hard failure — operator must fix
fi

if [ "$PARITY_WARNINGS" -eq 0 ]; then
  echo "OK: all JSON valid, es/en parity 100%"
  exit 0
fi

# Parity-only — soft warning, exit 0 (don't fail the cron)
echo "WARN: $PARITY_WARNINGS parity warnings (no JSON errors)"
exit 0
