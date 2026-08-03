#!/usr/bin/env bash
# Post to LinkedIn (Page) via Postiz cross-platform scheduler.
# Usage: li-post.sh "<message>" <integration_id> [image_url]
#
# Requires:
#   - POSTIZ_API_KEY in /root/.hermes/.env (Postiz device-flow OAuth also works:
#     `postiz auth:login`)
#   - `postiz` CLI installed (`npm install -g postiz`)
#   - <integration_id> from `postiz integrations:list | jq '.[] | select(.identifier=="linkedin-page") | .id'`
#
# Note: Postiz CLI requires `-s <ISO date>` even though we want "post now".
# Caller passes the post via `social-queue-runner.sh`, which knows the scheduled_at.
# This script just calls Postiz with the scheduled_at embedded as `-s`.
# Per Postiz rules (SKILL), media files must be uploaded via `postiz upload` first.

set -euo pipefail
MSG="${1:?usage: li-post.sh <message> <integration_id> [image_url] [scheduled_at]}"
INTEGRATION="${2:?usage: li-post.sh <message> <integration_id> [image_url] [scheduled_at]}"
IMG="${3:-}"
SCHED="${4:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

if [ -f /root/.hermes/.env ]; then
  set -a; source /root/.hermes/.env; set +a
fi

if [ -z "${POSTIZ_API_KEY:-}" ] && ! postiz auth:status >/dev/null 2>&1; then
  echo "❌ li-post: POSTIZ_API_KEY unset AND no Postiz OAuth credentials. Set POSTIZ_API_KEY or run `postiz auth:login`."
  exit 1
fi

# LinkedIn has a 3000-char hard limit on post body.
if [ "${#MSG}" -gt 3000 ]; then
  echo "❌ li-post: message is ${#MSG} chars; LinkedIn max is 3000. Truncate upstream."
  exit 1
fi

# Resolve media: if local file path, upload first via postiz (per Postiz rule).
MEDIA_ARGS=""
if [ -n "$IMG" ]; then
  case "$IMG" in
    http://*|https://*)
      # Already a URL — Postiz will reject non-Postiz URLs for IG/TT/YT but accepts
      # them for LinkedIn. Pass through.
      MEDIA_ARGS="-m \"$IMG\""
      ;;
    *)
      # Local file → upload first, then use the returned Postiz path
      uploaded=$(postiz upload "$IMG" 2>&1) || { echo "❌ li-post: postiz upload failed: $uploaded"; exit 1; }
      path=$(echo "$uploaded" | python3 -c "import json,sys; print(json.load(sys.stdin).get('path',''))")
      [ -z "$path" ] && { echo "❌ li-post: postiz upload returned no path: $uploaded"; exit 1; }
      MEDIA_ARGS="-m \"$path\""
      ;;
  esac
fi

# Build postiz command. Use -t schedule so Postiz publishes at the scheduled time
# (NOT immediately, even if scheduled_at is "now"). This lets us batch.
# shellcheck disable=SC2086
postiz posts:create \
  -c "$MSG" \
  $MEDIA_ARGS \
  -s "$SCHED" \
  -t schedule \
  -i "$INTEGRATION" \
  | python3 -c "
import json, sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
    # Postiz returns {id: '...', status: 'schedule', ...}
    pid = d.get('id', '')
    status = d.get('status', 'unknown')
    print(f'✓ Posted to LinkedIn (via Postiz). id={pid} status={status}')
except Exception:
    print(raw.strip())
"