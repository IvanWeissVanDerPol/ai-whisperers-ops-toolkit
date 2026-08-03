#!/usr/bin/env bash
# validate-meta-stack.sh
# Pre-flight validation of the Ai-Whisperers Meta stack.
#
# Checks the 3 vendor tokens (Composio, Pipeboard, Postiz) plus the
# underlying Meta Graph API token if a fallback MCP is enabled.
#
# Exit code:
#   0 = all green (or all vendors disabled — nothing to validate)
#   1 = one or more vendors returned HTTP errors or have missing credentials
#
# Designed to run from cron and ad-hoc. Outputs both human-readable (default)
# and JSON (--json) for programmatic parsing.

set -uo pipefail

JSON_MODE=0
[[ "${1:-}" == "--json" ]] && JSON_MODE=1

ENV_FILE="${HOME:-/root}/.hermes/.env"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE" 2>/dev/null || true

# --- helpers ----------------------------------------------------------------

# Read a key from .env without exporting it (safer).
env_get() {
  local k="$1"
  [[ -f "$ENV_FILE" ]] || { echo ""; return; }
  grep -E "^${k}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'\'']//;s/["'\'']$//'
}

# Emit JSON or human line depending on mode.
emit() {
  if [[ $JSON_MODE -eq 1 ]]; then
    return 0  # caller composes JSON at end
  else
    local status="$1"; shift
    printf "  %s %s\n" "$status" "$*"
  fi
}

# --- vendor checks ----------------------------------------------------------

check_composio() {
  local key="${MCP_COMPOSIO_API_KEY:-$(env_get MCP_COMPOSIO_API_KEY)}"
  if [[ -z "$key" ]]; then
    echo "DISABLED"
    return
  fi
  local r
  r=$(curl -m 8 -s -o /dev/null -w "%{http_code}" \
        -H "x-consumer-api-key: $key" \
        "https://backend.composio.dev/api/v1/apps" 2>/dev/null) || r="000"
  case "$r" in
    200) echo "OK" ;;
    401|403) echo "AUTH_FAILED" ;;
    410) echo "DEPRECATED_v3_REQUIRED" ;;
    000) echo "NETWORK_ERROR" ;;
    *) echo "HTTP_${r}" ;;
  esac
}

check_pipeboard() {
  local tok="${PIPEBOARD_API_TOKEN:-$(env_get PIPEBOARD_API_TOKEN)}"
  if [[ -z "$tok" ]]; then
    echo "DISABLED"
    return
  fi
  local r
  r=$(curl -m 8 -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $tok" \
        "https://meta-ads.mcp.pipeboard.co/" 2>/dev/null) || r="000"
  case "$r" in
    200|401) echo "OK" ;;  # 401 = token wrong but server reachable
    000) echo "NETWORK_ERROR" ;;
    *) echo "HTTP_${r}" ;;
  esac
}

check_postiz() {
  local key="${POSTIZ_API_KEY:-$(env_get POSTIZ_API_KEY)}"
  if [[ -z "$key" ]]; then
    echo "DISABLED"
    return
  fi
  local r
  r=$(curl -m 8 -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $key" \
        "https://api.postiz.com/v1/integrations" 2>/dev/null) || r="000"
  case "$r" in
    200) echo "OK" ;;
    401|403) echo "AUTH_FAILED" ;;
    000) echo "NETWORK_ERROR" ;;
    *) echo "HTTP_${r}" ;;
  esac
}

check_meta_graph() {
  local token="${META_PAGE_TOKEN:-$(env_get META_PAGE_TOKEN)}"
  if [[ -z "$token" ]]; then
    echo "DISABLED"
    return
  fi
  local r
  r=$(curl -m 8 -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $token" \
        "https://graph.facebook.com/v21.0/me?fields=id,name" 2>/dev/null) || r="000"
  case "$r" in
    200) echo "OK" ;;
    401|403) echo "AUTH_FAILED" ;;
    000) echo "NETWORK_ERROR" ;;
    *) echo "HTTP_${r}" ;;
  esac
}

# --- run all checks ---------------------------------------------------------

c_status=$(check_composio)
p_status=$(check_pipeboard)
z_status=$(check_postiz)
g_status=$(check_meta_graph)

# --- emit -------------------------------------------------------------------

severity() {
  case "$1" in
    OK) echo "✓" ;;
    DISABLED) echo "—" ;;
    AUTH_FAILED) echo "✗ auth" ;;
    NETWORK_ERROR) echo "✗ net" ;;
    HTTP_*) echo "✗ http" ;;
    *) echo "?" ;;
  esac
}

is_failing() {
  case "$1" in
    OK|DISABLED) return 1 ;;
    *) return 0 ;;
  esac
}

if [[ $JSON_MODE -eq 1 ]]; then
  cat <<JSON
{
  "composio":  "$(severity "$c_status") | $c_status",
  "pipeboard": "$(severity "$p_status") | $p_status",
  "postiz":    "$(severity "$z_status") | $z_status",
  "graph_api": "$(severity "$g_status") | $g_status"
}
JSON
else
  cat <<HDR
═══════════════════════════════════════════════════════════════
  Meta stack validation — $(date -u +%Y-%m-%dT%H:%M:%SZ)
═══════════════════════════════════════════════════════════════
HDR
  printf "  composio   (organic FB/IG/DMs)        %s  %s\n" \
    "$(severity "$c_status")" "$c_status"
  printf "  pipeboard  (Meta Ads)                 %s  %s\n" \
    "$(severity "$p_status")" "$p_status"
  printf "  postiz     (cross-platform)           %s  %s\n" \
    "$(severity "$z_status")" "$z_status"
  printf "  graph_api  (fallback direct)          %s  %s\n" \
    "$(severity "$g_status")" "$g_status"

  echo
  echo "  Legend: ✓=ok  —=not configured  ✗=failing"
  echo
  echo "  To enable a vendor:"
  echo "    composio  → https://dashboard.composio.dev  (API Key)"
  echo "    pipeboard → https://pipeboard.co            (API Token)"
  echo "    postiz    → https://postiz.com              (Settings → API Key)"
  echo "    graph_api → developers.facebook.com         (System User Token)"
fi

# Non-zero exit only if a configured vendor is failing.
any_fail=0
for s in "$c_status" "$p_status" "$z_status" "$g_status"; do
  if is_failing "$s"; then any_fail=1; fi
done
exit $any_fail
