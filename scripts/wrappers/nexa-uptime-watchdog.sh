#!/usr/bin/env bash
set -euo pipefail

URLS=(
  "https://nexa.paragu-ai.com/en"
  "https://nexa.paragu-ai.com/es"
  "https://dev.nexa.paragu-ai.com/en"
)

fails=()
for u in "${URLS[@]}"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$u" || echo "000")
  if [[ "$code" != "200" ]]; then
    fails+=("$u -> $code")
  fi
done

if (( ${#fails[@]} > 0 )); then
  echo "Nexa uptime alert"
  printf '%s\n' "${fails[@]}"
fi
