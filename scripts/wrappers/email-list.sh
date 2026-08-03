#!/usr/bin/env bash
# Read latest N emails via Himalaya.
# Usage: email-list.sh [count] [--unread]
# Output: structured (id | from | subject | date)

set -euo pipefail
COUNT="${1:-10}"

if ! command -v himalaya >/dev/null; then
  echo "❌ himalaya not installed"; exit 1
fi

himalaya envelope list --page-size "$COUNT" --output plain | \
  awk -F'|' '{
    gsub(/^[ \t]+|[ \t]+$/, "", $0)
    print $0
  }' | column -t -s'|' 2>/dev/null || himalaya envelope list --page-size "$COUNT"