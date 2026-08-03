#!/bin/bash
# Erebus Site Health Monitor
# Checks all active client sites — silent when all up, WhatsApp alert on failures
# Run: every 15m via cron job erebus-site-health

SITES=(
  "https://paragu-ai.com"
  "https://30vcs.paragu-ai.com"
  "https://brahm.paragu-ai.com"
  "https://dayah.paragu-ai.com"
  "https://depiflash.paragu-ai.com"
  "https://tiendaelviajero.com.py"
  "https://goldenvisa.paragu-ai.com"
  "https://magnolia-peluqueria.paragu-ai.com"
  "https://maiyu.paragu-ai.com"
  "https://nicolas-duarte.paragu-ai.com"
  "https://ozmontania.paragu-ai.com"
  "https://superspuma.paragu-ai.com"
  "https://villamayor.paragu-ai.com"
)

DOWN=()
for site in "${SITES[@]}"; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "$site" 2>/dev/null)
  if [[ "$code" != "200" ]]; then
    DOWN+=("$(echo $site | sed 's|https://||') ($code)")
  fi
done

if [ ${#DOWN[@]} -gt 0 ]; then
  echo "Sites Down:"
  for d in "${DOWN[@]}"; do echo "  $d"; done
  exit 1
fi
