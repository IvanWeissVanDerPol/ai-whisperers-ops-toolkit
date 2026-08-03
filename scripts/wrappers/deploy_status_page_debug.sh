#!/usr/bin/env bash
# deploy_status_page_debug.sh — DEBUG wrapper (will be replaced after verification)
# Found: the cron env inherits a CLOUDFLARE_API_TOKEN from config.yaml that is
# DIFFERENT from the one in ~/.wrangler/config/default.toml. The inherited one
# works for the Hermes internal API but NOT for `wrangler pages deploy` (9109).
# The fix: ALWAYS override CLOUDFLARE_API_TOKEN with the wrangler-config token.
# Still dumps env for future debugging.
env | grep -i -E "claude|cloud|wrangler|openrouter|path|home|user" > /tmp/cron_env_debug.txt 2>&1
echo "CWD: $(pwd)" >> /tmp/cron_env_debug.txt
if [ -f /root/.wrangler/config/default.toml ]; then
  export CLOUDFLARE_API_TOKEN=$(grep 'api_token' /root/.wrangler/config/default.toml | sed -E 's/.*api_token\s*=\s*"([^"]+)".*/\1/')
fi
echo "WRANGLER_TOKEN: ${CLOUDFLARE_API_TOKEN:0:12}...${CLOUDFLARE_API_TOKEN: -4}" >> /tmp/cron_env_debug.txt
exec python3 /root/.hermes/scripts/deploy_status_page.py --project hermes-status
