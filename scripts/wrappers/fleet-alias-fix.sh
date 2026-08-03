#!/usr/bin/env bash
# Auto-add CF CNAME records for alias mismatches detected by fleet-alias-audit.sh.
# Uses Cloudflare API. Requires CLOUDFLARE_API_TOKEN (auto-detects ZONE_ID for paragu-ai.com).
# Reads fleet-alias-audit.sh output, parses, creates missing CNAMEs.
# DRY-RUN by default; pass --apply to actually create records.

set -euo pipefail
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

set -a; source /root/.hermes/.env; set +a
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN not set}"

# Auto-detect zone ID for paragu-ai.com if not set
if [ -z "${CLOUDFLARE_ZONE_ID:-}" ]; then
  CLOUDFLARE_ZONE_ID=$(curl -s "https://api.cloudflare.com/client/v4/zones?name=paragu-ai.com" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result'][0]['id'] if d.get('result') else '')")
  if [ -z "$CLOUDFLARE_ZONE_ID" ]; then
    echo "❌ Could not auto-detect CLOUDFLARE_ZONE_ID for paragu-ai.com"; exit 1
  fi
  echo "✓ Auto-detected zone: $CLOUDFLARE_ZONE_ID"
fi

# Run alias audit
TMP_AUDIT=$(mktemp)
TMP_JSON=$(mktemp)
bash /root/.hermes/scripts/fleet-alias-audit.sh > "$TMP_AUDIT" 2>/dev/null

# Parse to JSON
python3 - "$TMP_AUDIT" "$TMP_JSON" << 'PYEOF'
import sys, json, re
with open(sys.argv[1]) as f:
    text = f.read()
mismatches = []
for block in text.split('❌ ')[1:]:
    lines = block.strip().split('\n')
    if len(lines) >= 2:
        broken = lines[0].strip()
        live = lines[1].replace('✅ ', '').strip().split(' (')[0]
        if live:
            mismatches.append({'broken': broken, 'live': live})
with open(sys.argv[2], 'w') as f:
    json.dump(mismatches, f, indent=2)
PYEOF

COUNT=$(python3 -c "import json; print(len(json.load(open('$TMP_JSON'))))")
rm -f "$TMP_AUDIT"

if [ "$COUNT" = "0" ]; then
  echo "✓ No mismatches to fix"
  rm -f "$TMP_JSON"
  exit 0
fi

echo "=== Mode: $([ $APPLY = 1 ] && echo 'APPLY' || echo 'DRY-RUN') ==="
echo ""
echo "Pending fixes ($COUNT):"
cat "$TMP_JSON" | python3 -c "
import json, sys
for m in json.load(sys.stdin):
    print(f\"  {m['broken']:40s} → {m['live']}\")
"
echo ""

# Process each
python3 - "$TMP_JSON" "$CLOUDFLARE_API_TOKEN" "$CLOUDFLARE_ZONE_ID" "$APPLY" << 'PYEOF'
import sys, json, subprocess
mismatches = json.load(open(sys.argv[1]))
token = sys.argv[2]
zone = sys.argv[3]
apply = sys.argv[4] == "1"

for m in mismatches:
    broken = m['broken']
    live = m['live']
    subdomain = broken.replace('.paragu-ai.com', '')

    # Check if record exists
    r = subprocess.run([
        'curl', '-s',
        f'https://api.cloudflare.com/client/v4/zones/{zone}/dns_records?name={subdomain}.paragu-ai.com&type=CNAME',
        '-H', f'Authorization: Bearer {token}',
        '-H', 'Content-Type: application/json'
    ], capture_output=True, text=True)
    exists = '"id"' in r.stdout and '"CNAME"' in r.stdout

    if exists:
        print(f'  ✓ {broken}: CNAME already exists')
        continue

    target = live.replace('.paragu-ai.com', '')
    if apply:
        cr = subprocess.run([
            'curl', '-s', '-X', 'POST',
            f'https://api.cloudflare.com/client/v4/zones/{zone}/dns_records',
            '-H', f'Authorization: Bearer {token}',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps({
                'type': 'CNAME',
                'name': subdomain,
                'content': f'{target}.paragu-ai.com',
                'proxied': True,
                'comment': 'Auto-created by fleet-alias-fix.sh'
            })
        ], capture_output=True, text=True)
        if '"success":true' in cr.stdout:
            print(f'  ✓ {broken}: CNAME → {target}.paragu-ai.com CREATED')
        else:
            print(f'  ✗ {broken}: {cr.stdout[:200]}')
    else:
        print(f'  → {broken}: would create CNAME → {target}.paragu-ai.com')
PYEOF

rm -f "$TMP_JSON"

[ $APPLY = 0 ] && echo "" && echo "Re-run with --apply to actually create these records."