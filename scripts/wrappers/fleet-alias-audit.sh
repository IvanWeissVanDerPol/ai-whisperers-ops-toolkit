#!/usr/bin/env bash
# Detect canonical-vs-alias mismatches in the fleet and report what needs fixing.
# Does NOT modify DNS — that's a human-confirmed action.
# Just reports the action items.
#
# Pattern: <slug>.paragu-ai.com 404 → <slug-with-hyphens>.paragu-ai.com 200
# Likely cause: COMPOSE_PROJECT_NAME differs from public-facing hostname
# Fix per client-site-inventory skill: add /opt/traefik/dynamic/<app>_static.toml

set -euo pipefail
AUDIT="/root/.hermes/backups/fleet-audit-2026-07-07.json"
[ -f "$AUDIT" ] || { echo "❌ $AUDIT not found"; exit 1; }

# Group by base name (strip -paragu-ai.com, .com.py, etc.)
python3 << 'PYEOF'
import json, re
from collections import defaultdict

d = json.load(open('/root/.hermes/backups/fleet-audit-2026-07-07.json'))
results = d['results']

# Build domain→status map
status = {r['domain']: r['code'] for r in results}

# For each 404, find a 200 with same base name (allowing hyphens)
candidates = []
for domain, code in sorted(status.items()):
    if code != '404':
        continue
    # Normalize: strip TLD + remove hyphens
    base = re.sub(r'\.(com\.py|paragu-ai\.com|com)$', '', domain)
    base_compact = base.replace('-', '')
    # Look for live version — exact or with hyphens
    for live_domain, live_code in status.items():
        if live_code != '200' or live_domain == domain:
            continue
        live_base = re.sub(r'\.(com\.py|paragu-ai\.com|com)$', '', live_domain)
        live_compact = live_base.replace('-', '')
        # Match if compact names are equal OR one is a prefix of the other (handles trailing -tattoo, -concept, etc.)
        if live_compact == base_compact or \
           live_compact.startswith(base_compact) or \
           base_compact.startswith(live_compact):
            candidates.append({
                'broken': domain,
                'live_canonical': live_domain,
                'suggested_action': f'Add CF CNAME or A-record redirect from {domain} → {live_domain}'
            })
            break

print("=== Alias mismatches detected ===\n")
for c in candidates:
    print(f"  ❌ {c['broken']}")
    print(f"  ✅ {c['live_canonical']} (canonical works)")
    print(f"  💡 {c['suggested_action']}\n")

print(f"Total: {len(candidates)} mismatches")
PYEOF