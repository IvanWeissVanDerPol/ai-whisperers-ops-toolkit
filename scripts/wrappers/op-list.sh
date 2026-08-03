#!/usr/bin/env bash
# List 1Password secrets in a vault (for audit).
# Usage: op-list.sh [vault_name]
# Requires: OP_SERVICE_ACCOUNT_TOKEN in /root/.hermes/.env

set -euo pipefail
VAULT="${1:-}"

set -a; source /root/.hermes/.env; set +a
: "${OP_SERVICE_ACCOUNT_TOKEN:?OP_SERVICE_ACCOUNT_TOKEN not set}"

if ! command -v op >/dev/null; then
  echo "❌ op CLI not installed"; exit 1
fi

if [ -n "$VAULT" ]; then
  op item list --vault "$VAULT" --format json | python3 -c "
import json, sys
items = json.load(sys.stdin)
print(f\"{'ID':<30} {'TITLE':<50} {'CATEGORY':<20}\")
print('-' * 100)
for i in items:
    cat = i.get('category', 'UNKNOWN')[:20]
    title = i.get('title', i.get('id', '?'))[:48]
    print(f\"{i['id']:<30} {title:<50} {cat:<20}\")
print(f'\\nTotal: {len(items)} items')
"
else
  op vault list --format json | python3 -c "
import json, sys
vaults = json.load(sys.stdin)
for v in vaults:
    print(f\"  {v['id']:<30} {v['name']}\")
"
fi