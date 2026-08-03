#!/usr/bin/env bash
# Pre-flight check for all 7 token sets. Reports which are wired, which are missing.
# Usage: token-status.sh [--verbose]

VERBOSE=0
[ "${1:-}" = "--verbose" ] && VERBOSE=1

ENV_FILE="/root/.hermes/.env"

echo "=== Token status ($(date '+%Y-%m-%d %H:%M:%S')) ==="
echo ""

check_env() {
  local VAR="$1"
  local VAL
  VAL=$(grep "^${VAR}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)
  if [ -n "$VAL" ]; then
    local PREFIX=$(echo "$VAL" | head -c 8)
    local LEN=${#VAL}
    if [ "$VERBOSE" = "1" ]; then
      echo "  ✓ $VAR (${LEN} chars: ${PREFIX}...)"
    else
      echo "  ✓ $VAR (${LEN} chars)"
    fi
  else
    echo "  ✗ $VAR MISSING"
  fi
}

check_file() {
  local DESC="$1"
  local PATH="$2"
  if [ -f "$PATH" ]; then
    echo "  ✓ $DESC exists at $PATH"
  else
    echo "  ✗ $DESC missing at $PATH"
  fi
}

check_dir() {
  local DESC="$1"
  local PATH="$2"
  if [ -d "$PATH" ]; then
    echo "  ✓ $DESC exists at $PATH"
  else
    echo "  ✗ $DESC missing at $PATH"
  fi
}

check_cmd() {
  local CMD="$1"
  if command -v "$CMD" >/dev/null 2>&1; then
    echo "  ✓ $CMD installed"
  else
    echo "  ✗ $CMD not installed"
  fi
}

echo "--- Meta (Facebook/Instagram) ---"
check_env META_APP_ID
check_env META_APP_SECRET
check_env META_PAGE_TOKEN
check_env META_PAGE_ID
check_env META_IG_USER_ID

echo ""
echo "--- Email (Himalaya) ---"
check_env HIMALAYA_CONFIG_PATH
check_file "himalaya config.toml" "${HIMALAYA_CONFIG_PATH:-/root/.config/himalaya/config.toml}"
check_cmd himalaya

echo ""
echo "--- Google Drive / Workspace ---"
check_env GOOGLE_CLIENT_ID
check_env GOOGLE_CLIENT_SECRET
check_file "google_token.json" "/root/.hermes/google_token.json"
check_cmd himalaya  # placeholder

echo ""
echo "--- Obsidian vault ---"
check_env OBSIDIAN_VAULT_PATH
check_dir "vault dir" "${OBSIDIAN_VAULT_PATH:-/root/obsidian-vault}"

echo ""
echo "--- 1Password ---"
check_env OP_SERVICE_ACCOUNT_TOKEN
check_cmd op

echo ""
echo "--- Atlassian ---"
check_env JIRA_URL
check_env JIRA_USERNAME
check_env JIRA_API_TOKEN
check_env CONFLUENCE_URL
check_env CONFLUENCE_USERNAME
check_env CONFLUENCE_API_TOKEN

echo ""
echo "--- Stripe ---"
check_env STRIPE_SECRET_KEY
STRIPE_KEY=$(grep "^STRIPE_SECRET_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)
if echo "$STRIPE_KEY" | grep -q "sk_live_"; then
  echo "  mode: LIVE"
elif echo "$STRIPE_KEY" | grep -q "sk_test_"; then
  echo "  mode: TEST"
elif [ -n "$STRIPE_KEY" ]; then
  echo "  mode: UNKNOWN (key doesn't match expected prefixes)"
else
  echo "  mode: (no key)"
fi

echo ""
echo "=== End of report ==="