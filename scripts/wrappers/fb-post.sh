#!/usr/bin/env bash
# Post to Facebook Page via Meta Graph API.
# Usage: fb-post.sh "<message>" [image_url]
# Requires: META_PAGE_TOKEN, META_PAGE_ID in /root/.hermes/.env

set -euo pipefail
MSG="${1:?usage: fb-post.sh <message> [image_url]}"
IMG="${2:-}"

# Load tokens
set -a; source /root/.hermes/.env; set +a
: "${META_PAGE_TOKEN:?META_PAGE_TOKEN not set}"
: "${META_PAGE_ID:?META_PAGE_ID not set}"

if [ -n "$IMG" ]; then
  # Photo post with caption
  curl -sf -X POST "https://graph.facebook.com/v20.0/${META_PAGE_ID}/photos" \
    -d "caption=${MSG}" \
    -d "url=${IMG}" \
    -d "access_token=${META_PAGE_TOKEN}" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"✓ Posted photo. id={d.get('id')}\"); exit(0 if 'id' in d else 1)"
else
  # Text-only post
  curl -sf -X POST "https://graph.facebook.com/v20.0/${META_PAGE_ID}/feed" \
    -d "message=${MSG}" \
    -d "access_token=${META_PAGE_TOKEN}" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"✓ Posted. id={d.get('id')}\"); exit(0 if 'id' in d else 1)"
fi