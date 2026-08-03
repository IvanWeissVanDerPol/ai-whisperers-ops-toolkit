#!/usr/bin/env bash
# Get Stripe account balance + recent charges.
# Usage: stripe-status.sh [count]
# Requires: STRIPE_SECRET_KEY in /root/.hermes/.env

set -euo pipefail
COUNT="${1:-5}"

set -a; source /root/.hermes/.env; set +a
: "${STRIPE_SECRET_KEY:?STRIPE_SECRET_KEY not set}"

# Check key mode (test vs live)
MODE=$(echo "$STRIPE_SECRET_KEY" | grep -q "sk_live_" && echo "LIVE" || echo "TEST")
echo "=== Stripe account status (mode: $MODE) ==="

# Balance
echo ""
echo "--- Balance ---"
curl -sf -u "${STRIPE_SECRET_KEY}:" https://api.stripe.com/v1/balance | python3 -c "
import json, sys
d = json.load(sys.stdin)
for bal in d.get('available', []):
    print(f\"  Available: {bal['amount']/100:.2f} {bal['currency'].upper()}\")
for bal in d.get('pending', []):
    print(f\"  Pending:   {bal['amount']/100:.2f} {bal['currency'].upper()}\")
print(f\"  Livemode:  {d.get('livemode', False)}\")
"

# Recent charges
echo ""
echo "--- Recent charges (last $COUNT) ---"
curl -sf -u "${STRIPE_SECRET_KEY}:" "https://api.stripe.com/v1/charges?limit=${COUNT}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('data', []):
    print(f\"  {c['created']:>10}  {c['amount']/100:>9.2f} {c['currency'].upper():<3} {c['status']:<10} {c.get('description', c['id'])}\")
"