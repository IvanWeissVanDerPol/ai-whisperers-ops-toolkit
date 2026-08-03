#!/usr/bin/env bash
# dentist-a11y-scan.sh — basic WCAG checks (placeholder until axe-core wired)
# Exit codes:
#   0 = scan complete, no warnings
#   1 = scan complete, warnings found (this is OK, not a failure)
#   2 = scan itself failed (couldn't run, missing deps, etc.)
#
# IMPORTANT: cron_health.py treats exit_code_1 as "broken cron". This script
# intentionally returns 0 even with warnings — the warning IS the output, not
# the failure. Warnings are emitted to stdout for log capture.
set -u  # NOT using -e or -o pipefail because grep | wc -l pipelines can spuriously fail
REPO=/root/dentist-template-scan
cd "$REPO" || { echo "ERROR: cannot cd to $REPO" >&2; exit 2; }

# Check for inline hex colors (should use tokens)
INLINE_HEX=$(grep -rE '#[0-9a-fA-F]{6}' app/ components/ 2>/dev/null | grep -v "tokens.json" | wc -l) || INLINE_HEX=0
if [ "$INLINE_HEX" -gt 0 ]; then
  echo "WARNING: $INLINE_HEX inline hex colors found (should use tokens)"
fi

# Check for missing alt text on img tags
MISSING_ALT=$(grep -rE '<img[^>]+>' app/ components/ 2>/dev/null | grep -v "alt=" | wc -l) || MISSING_ALT=0
if [ "$MISSING_ALT" -gt 0 ]; then
  echo "WARNING: $MISSING_ALT img tags without alt attribute"
fi

# Summary line — always print
echo "A11Y scan complete. Inline hex: $INLINE_HEX, missing alt: $MISSING_ALT"

# Exit 0 even with warnings — warnings go to stdout, NOT a cron failure
exit 0
