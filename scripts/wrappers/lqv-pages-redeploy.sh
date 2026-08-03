#!/usr/bin/env bash
# LQV site auto-redeployer — runs on demand or via cron.
# Reuses the persisted Cloudflare token at /root/.cloudflare-env.

set -euo pipefail
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Pull the token out of the env file (no shell-history leakage).
TOK=$(awk -F= '/^CLOUDFLARE_API_TOKEN=/ { gsub(/["'\'']/,"",$2); print $2; exit }' /root/.cloudflare-env)
ACCT=$(awk -F= '/^CLOUDFLARE_ACCOUNT_ID=/ { gsub(/["'\'']/,"",$2); print $2; exit }' /root/.cloudflare-env)
[ -z "${ACCT}" ] && ACCT="9eb1832f3e42a1dbd6ba854f8d6a1cb2"  # fallback from CF verify

export CF_API_TOKEN="${TOK}"
export CLOUDFLARE_API_TOKEN="${TOK}"
export CLOUDFLARE_ACCOUNT_ID="${ACCT}"

# Preflight check
echo "[lqv-pages] running preflight checks"
bash "$(dirname "$0")/lqv-preflight.sh" 2>&1 | head -30 || true

# Find the buyer page web/ directory: prefer canonical /root/la-quebrada-viva
# fall back to /root/.hermes/lqv-splat, then /tmp/lqv-scan
WEB_DIR="/root/la-quebrada-viva/splats/exports/web"
[ ! -d "$WEB_DIR" ] && WEB_DIR="/root/.hermes/lqv-splat/exports/web"
[ ! -d "$WEB_DIR" ] && WEB_DIR="/tmp/lqv-scan/splats/exports/web"
if [ ! -d "$WEB_DIR" ]; then
  echo "[lqv-pages] no buyer page web/ dir found — nothing to deploy"
  exit 0
fi

cd "$WEB_DIR"
echo "[lqv-pages] deploying ${STAMP}  account=${ACCT:0:8}…  dir=$WEB_DIR"

wrangler pages deploy . \
  --project-name lqv-walkthrough \
  --branch main \
  --commit-dirty=true 2>&1 | head -20
