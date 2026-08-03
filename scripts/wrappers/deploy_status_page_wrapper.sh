#!/usr/bin/env bash
# deploy_status_page_wrapper.sh — invoke deploy_status_page.py with explicit token
# This avoids the cron environment's stale/empty CLOUDFLARE_API_TOKEN issue.
# The script reads the token from ~/.wrangler/config/default.toml if env is empty,
# but wrangler v4 reads it lazily and the cron env may have an old value in
# process memory that the script's env.copy() doesn't see.
# Solution: explicitly source the token into env before exec.
if [ -z "$CLOUDFLARE_API_TOKEN" ] && [ -f /root/.wrangler/config/default.toml ]; then
  export CLOUDFLARE_API_TOKEN=$(grep 'api_token' /root/.wrangler/config/default.toml | sed -E 's/.*api_token\s*=\s*"([^"]+)".*/\1/')
fi
exec python3 /root/.hermes/scripts/deploy_status_page.py --project hermes-status
