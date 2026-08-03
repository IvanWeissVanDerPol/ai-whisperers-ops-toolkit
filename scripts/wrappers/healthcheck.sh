#!/usr/bin/env bash
# Ometz site healthcheck — probe live site + Docker service + DNS.
# Cron-friendly. Outputs single-line summary + structured detail.
# Exit 0 = healthy, 1 = degraded, 2 = down.

set -euo pipefail
APP="dra-gabriela"
VPS="root@72.61.44.159"
SERVICE="${APP}_web"
DOMAINS=("ometzdental.com" "dragabriela.paragu-ai.com")
LOCALES=("es" "en")
PAGES=("/" "/servicios" "/filosofia" "/contacto")

# Probe each domain × locale × page
results=""
status=0
for domain in "${DOMAINS[@]}"; do
  for locale in "${LOCALES[@]}"; do
    code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 8 "https://${domain}/${locale}" 2>/dev/null || echo "000")
    if [ "$code" != "200" ]; then
      results="${results}${domain}/${locale}=${code} "
      status=1
    fi
  done
done

# Docker service health
replicas=$(ssh "$VPS" "docker service ls --format '{{.Replicas}}' --filter name=$SERVICE" 2>/dev/null | head -1)
if [ -z "$replicas" ] || [[ "$replicas" != *"1/1"* && "$replicas" != *"2/2"* ]]; then
  results="${results}service=${replicas:-none} "
  status=2
fi

# Pricing leak gate (the 4-tier was deleted 2026-06-15)
leak=$(curl -sL --max-time 8 https://ometzdental.com/es 2>/dev/null | grep -oE "USD 2\.900|USD 4\.400|USD 6\.900|Paraguay Base" | head -1 || true)
if [ -n "$leak" ]; then
  results="${results}pricing-leak='$leak' "
  status=1
fi

# Format summary
if [ -z "$results" ]; then
  echo "OK ometz | 4 domains healthy | service $replicas | no pricing leak"
  exit 0
else
  echo "FAIL ometz | issues: $results"
  exit $status
fi