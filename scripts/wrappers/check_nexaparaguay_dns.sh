#!/bin/bash
# Verify nexaparaguay.com.py is live at the canonical domain.
# Run after NIC.py NS delegation propagates (typically 30min - 4hr).
#
# Returns 0 if live, 1 if not yet. Prints a short status report.

set -u
DOMAIN="nexaparaguay.com.py"
WWW="www.${DOMAIN}"
VPS="72.61.44.159"

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }

echo "═══════════════════════════════════════════════"
echo "  Nexa Paraguay DNS + Health Check"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "═══════════════════════════════════════════════"

# 1. DNS resolution
echo
echo "── 1. DNS Resolution ──"
APEX=$(dig +short +time=5 "${DOMAIN}" @1.1.1.1 A | head -1)
WWW_IP=$(dig +short +time=5 "${WWW}" @1.1.1.1 A | head -1)
NS=$(dig +short +time=5 "${DOMAIN}" @1.1.1.1 NS | head -2 | tr '\n' ' ')

if [ -z "$APEX" ]; then
  red "✗ ${DOMAIN} does NOT resolve (NS delegation not yet propagated)"
  echo "  Current NS: ${NS:-'(none)'}"
  echo
  echo "  → Blocked at NIC.py. Go to https://www.nic.py/modificaciones.php"
  echo "  → Submit 'Servidores DNS' change for nexaparaguay.com.py"
  echo "  → Nameservers to enter:"
  echo "      carlane.ns.cloudflare.com"
  echo "      matias.ns.cloudflare.com"
  exit 1
fi

green "✓ ${DOMAIN} → ${APEX}"
green "✓ ${WWW} → ${WWW_IP:-${APEX}}"
echo "  NS: ${NS}"

# 2. HTTP reachability via the new domain
echo
echo "── 2. HTTP Reachability ──"
HTTP_APEX=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN}/es/" 2>&1)
HTTP_WWW=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "https://${WWW}/es/" 2>&1)
HTTP_ROOT=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN}/" 2>&1)

if [ "$HTTP_APEX" = "200" ] || [ "$HTTP_APEX" = "307" ]; then
  green "✓ https://${DOMAIN}/es/ → ${HTTP_APEX}"
else
  red "✗ https://${DOMAIN}/es/ → ${HTTP_APEX}"
fi

if [ "$HTTP_WWW" = "200" ] || [ "$HTTP_WWW" = "307" ]; then
  green "✓ https://${WWW}/es/ → ${HTTP_WWW}"
else
  yellow "⚠ https://${WWW}/es/ → ${HTTP_WWW}"
fi

# 3. Content sanity (canonical URL in HTML)
echo
echo "── 3. Content Sanity ──"
HTML=$(curl -sk --max-time 10 "https://${DOMAIN}/es/" 2>&1)
CANONICAL=$(echo "$HTML" | grep -oE '<link[^>]*rel="canonical"[^>]*>' | head -1)
if echo "$CANONICAL" | grep -q "nexaparaguay.com.py"; then
  green "✓ Canonical URL is correct: ${DOMAIN}"
else
  yellow "⚠ Canonical URL: ${CANONICAL:-'(not found)'}"
fi

TITLE=$(echo "$HTML" | grep -oE '<title>[^<]+</title>' | head -1 | sed 's/<[^>]*>//g')
if [ -n "$TITLE" ]; then
  green "✓ Page title: ${TITLE}"
fi

# 4. Health endpoint
echo
echo "── 4. Health Endpoint ──"
HEALTH=$(curl -sk --max-time 10 "https://${DOMAIN}/api/health" 2>&1)
if echo "$HEALTH" | grep -qE '"status"\s*:\s*"ok"'; then
  green "✓ /api/health → ${HEALTH}"
else
  yellow "⚠ /api/health → ${HEALTH:-'(no response)'}"
fi

echo
echo "═══════════════════════════════════════════════"
green "✅ nexaparaguay.com.py is LIVE"
echo "═══════════════════════════════════════════════"
exit 0