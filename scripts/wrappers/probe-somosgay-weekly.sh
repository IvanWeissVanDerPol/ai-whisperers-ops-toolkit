#!/usr/bin/env bash
# Weekly audit of somosgay.paragu-ai.com — checks critical endpoints + JSON-LD validity.
# Watchdog pattern: silent when healthy, alert when broken.

set -uo pipefail

SITE="https://somosgay.paragu-ai.com"
ERRORS=0
TIMEOUT=8

# Check each critical route
ROUTES=(
  "/"
  "/clinica-kunuu"
  "/donar"
  "/memoria-108"
  "/auditoria"
  "/equipo"
  "/cuidado"
  "/ayudar"
  "/transferencia"
  "/prensa"
  "/noticias"
  "/noticias/guia-completa-prep-2026"
  "/api/healthz"
  "/sitemap.xml"
  "/robots.txt"
  "/images-sitemap.xml"
  "/feed.xml"
  "/events-ics"
)

for r in "${ROUTES[@]}"; do
  status=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "${SITE}${r}" 2>/dev/null || echo "000")
  if [[ "$status" != "200" ]]; then
    echo "⚠️ Route ${r} → HTTP ${status}" >&2
    ERRORS=$((ERRORS + 1))
  fi
done

# Check JSON-LD on key pages
for page in "/" "/clinica-kunuu" "/donar"; do
  body=$(curl -sS --max-time "$TIMEOUT" "${SITE}${page}" 2>/dev/null || true)
  # Each page should have 3 JSON-LD blocks (NGO, MedicalClinic, WebSite)
  count=$(echo "$body" | grep -o 'application/ld+json' | wc -l | tr -d ' ')
  if [[ "$count" -lt "3" ]]; then
    echo "⚠️ ${page} has only ${count} JSON-LD blocks (expected 3)" >&2
    ERRORS=$((ERRORS + 1))
  fi
done

if [[ "$ERRORS" -gt 0 ]]; then
  echo "🚨 somosgay-site WEEKLY AUDIT failed — ${ERRORS} issue(s) detected — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 1
fi

exit 0  # silent when healthy
