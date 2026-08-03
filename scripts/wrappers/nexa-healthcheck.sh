#!/bin/bash
# Nexa Healthcheck — curl home page, verify 200, alert on failure
# Usage: ./scripts/nexa-healthcheck.sh

URL="${1:-https://nexa.paragu-ai.com}"
TIMEOUT=10

STATUS=$(curl -sL -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$URL" 2>/dev/null)
CONTENT=$(curl -sL --max-time $TIMEOUT "$URL" 2>/dev/null)

if [ "$STATUS" != "200" ]; then
  echo "DOWN|$URL returned $STATUS (expected 200)"
  exit 1
fi

# Verify key strings in page
if ! echo "$CONTENT" | grep -q "Nexa"; then
  echo "DEGRADED|$URL returned 200 but missing expected content"
  exit 2
fi

echo "OK|$URL responded $STATUS"
exit 0
