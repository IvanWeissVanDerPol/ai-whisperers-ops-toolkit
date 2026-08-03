#!/usr/bin/env bash
# Generate Jira tickets for every broken fleet site from the latest audit.
# Reads /root/.hermes/backups/fleet-audit-*.json, creates one ticket per broken domain.
# Requires: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

set -euo pipefail
AUDIT="/root/.hermes/backups/fleet-audit-2026-07-07.json"
[ -f "$AUDIT" ] || { echo "❌ $AUDIT not found. Run fleet audit first."; exit 1; }

set -a; source /root/.hermes/.env; set +a
: "${JIRA_URL:?JIRA_URL not set — token paste pending}"
: "${JIRA_USERNAME:?JIRA_USERNAME not set}"
: "${JIRA_API_TOKEN:?JIRA_API_TOKEN not set}"

# Extract broken domains
python3 << 'EOF' > /tmp/broken-sites.json
import json
d = json.load(open('/root/.hermes/backups/fleet-audit-2026-07-07.json'))
broken = []
for r in d['results']:
    if r['code'] in ('404', '502', '000'):
        # Find canonical name from comments if possible
        broken.append({
            'domain': r['domain'],
            'code': r['code'],
            'time_s': r['time_s']
        })
print(json.dumps(broken, indent=2))
EOF

echo "Broken sites to ticket:"
cat /tmp/broken-sites.json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f\"  {x['code']} {x['domain']}\") for x in d]"
echo ""
echo "Total: $(jq length /tmp/broken-sites.json 2>/dev/null || cat /tmp/broken-sites.json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') broken sites"
echo ""

# Auto-create tickets
PROJECT="${JIRA_PROJECT:-OMETZ}"
created=0
failed=0

cat /tmp/broken-sites.json | python3 -c "
import json, sys
for site in json.load(sys.stdin):
    code = site['code']
    domain = site['domain']
    title = f'Fleet audit: {code} on {domain}'
    if code == '404':
        desc = f'Subdomain returns 404. May be: (1) DNS-only alias that needs A record, (2) canonical name differs, (3) service offboarded. Investigate and either redirect, fix, or decommission per the fleet-offboarding pattern.'
    elif code == '502':
        desc = f'502 Bad Gateway. Docker service on VPS likely down or Traefik label mismatch. Check ssh root@72.61.44.159 docker service ls for the site.'
    elif code == '000':
        desc = f'DNS empty / connection timeout. Domain has no A record or nameservers dead. Verify in Cloudflare and either add A→72.61.44.159 or decommission.'
    print(f'{title}|{desc}|{domain}|{code}')
" | while IFS='|' read -r title desc domain code; do
  if bash /root/.hermes/scripts/jira-create.sh "$PROJECT" "$title" "$desc" "Bug" 2>&1 | grep -q "Created"; then
    echo "  ✓ $domain"
    created=$((created+1))
  else
    echo "  ✗ $domain — manual ticket needed"
    failed=$((failed+1))
  fi
done

echo ""
echo "Summary: $created tickets created, $failed failed"