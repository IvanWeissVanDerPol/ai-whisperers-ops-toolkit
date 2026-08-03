#!/bin/bash
# SEO Monthly Report — Ai-Whisperers Client Sites
# Run: bash /root/.hermes/scripts/seo-report.sh
# Sends report to ntfy.sh/ai-whisperers-alerts

NTFY_TOPIC="${NTFY_TOPIC:-ai-whisperers-alerts}"
REPORT_DATE=$(date '+%Y-%m')
REPORT_FILE="/root/infrastructure/seo-logs/seo-report-${REPORT_DATE}.md"
mkdir -p "$(dirname "$REPORT_FILE")"

echo "=========================================="
echo " SEO Monthly Report — ${REPORT_DATE}"
echo "=========================================="

# Check if site-health.sh exists and run it
if [ -f /root/infrastructure/site-health.sh ]; then
  bash /root/infrastructure/site-health.sh > /tmp/health-check.log 2>&1
  HEALTH_UP=$(grep "UP:" /tmp/health-check.log | awk '{print $2}')
  HEALTH_DOWN=$(grep "DOWN:" /tmp/health-check.log | awk '{print $2}')
  echo "Health: UP=$HEALTH_UP DOWN=$HEALTH_DOWN"
fi

# Check Pagefind index if available
PAGEFIND_INDEX=""
for dir in /root/elviajero/.next /root/nexa-paraguay/.next /root/superspuma/.next; do
  if [ -d "$dir/server/pagefind" ]; then
    PAGEFIND_INDEX="$dir/server/pagefind"
    break
  fi
done

# Try to get Google Search Console data via curl (requires GSC API key)
GSC_DATA=""
if [ -n "$GSC_API_KEY" ]; then
  echo "Fetching Google Search Console data..."
  # This would call the GSC API
  GSC_DATA="[Requires GSC API configured]"
fi

# Check each client's site for basic SEO signals
CLIENT_SITES=(
  "tiendaelviajero.com.py"
  "nexa.paragu-ai.com"
  "superspuma.paragu-ai.com"
  "depiflash.paragu-ai.com"
)

echo ""
echo "=== Site SEO Signals ==="
SEO_REPORT=""
for site in "${CLIENT_SITES[@]}"; do
  # Check SSL
  ssl_ok=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 "https://$site" 2>/dev/null || echo "000")
  
  # Check robots.txt
  robots_ok=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 "https://$site/robots.txt" 2>/dev/null || echo "000")
  
  # Check sitemap
  sitemap_ok=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 "https://$site/sitemap.xml" 2>/dev/null || echo "000")
  
  if [ "$ssl_ok" = "200" ]; then
    ssl_status="OK"
  else
    ssl_status="SSL ERROR ($ssl_ok)"
  fi
  
  if [ "$robots_ok" = "200" ]; then
    robots_status="OK"
  else
    robots_status="MISSING ($robots_ok)"
  fi
  
  if [ "$sitemap_ok" = "200" ]; then
    sitemap_status="OK"
  else
    sitemap_status="MISSING ($sitemap_ok)"
  fi
  
  echo "  $site | SSL: $ssl_status | robots.txt: $robots_status | sitemap: $sitemap_status"
  SEO_REPORT="${SEO_REPORT}\n- **$site**: SSL=$ssl_status, robots.txt=$robots_status, sitemap=$sitemap_status"
done

# Generate markdown report
cat > "$REPORT_FILE" << EOF
# SEO Report — ${REPORT_DATE}

Generated: $(date '+%Y-%m-%d %H:%M')

## Site Health Summary
- Sites UP: $HEALTH_UP
- Sites DOWN: $HEALTH_DOWN

## SEO Signals
$SEO_REPORT

## Pagefind Index
$([ -n "$PAGEFIND_INDEX" ] && echo "Found at: $PAGEFIND_INDEX" || echo "Not configured")

## Google Search Console
$(if [ -n "$GSC_DATA" ]; then echo "$GSC_DATA"; else echo "_Not configured. Set GSC_API_KEY env var._"; fi)

## Action Items
1. Fix any DOWN sites immediately
2. Ensure all sites have sitemap.xml
3. Verify robots.txt allows crawlers
4. Check SSL certificates expiry dates

---
ParaguAI Growth OS — Automated SEO Report
EOF

echo ""
echo "Report saved to: $REPORT_FILE"

# Send summary to ntfy
SUMMARY="SEO Report $REPORT_DATE | UP: $HEALTH_UP | DOWN: $HEALTH_DOWN | Sites: ${#CLIENT_SITES[@]}"
curl -s -X POST "https://ntfy.sh/$NTFY_TOPIC" \
  -H "Tags: chart_with_upwards_trend" \
  -H "Priority: default" \
  -d "$SUMMARY" > /dev/null 2>&1

echo "Done."