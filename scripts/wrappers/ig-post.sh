#!/usr/bin/env bash
# Post to Instagram Business account via Meta Graph API.
# Usage: ig-post.sh "<caption>" <image_url> [image_url2...]
# Requires: META_PAGE_TOKEN, META_IG_USER_ID in /root/.hermes/.env
# Note: IG requires PUBLIC image URL (not local file) + 2-step publish flow.

set -euo pipefail
CAPTION="${1:?usage: ig-post.sh <caption> <image_url>}"
IMG_URL="${2:?usage: ig-post.sh <caption> <image_url>}"

set -a; source /root/.hermes/.env; set +a
: "${META_PAGE_TOKEN:?META_PAGE_TOKEN not set}"
: "${META_IG_USER_ID:?META_IG_USER_ID not set}"

# Step 1: Create media container
CONTAINER_ID=$(curl -sf -X POST "https://graph.facebook.com/v20.0/${META_IG_USER_ID}/media" \
  -d "image_url=${IMG_URL}" \
  -d "caption=${CAPTION}" \
  -d "access_token=${META_PAGE_TOKEN}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")

if [ -z "$CONTAINER_ID" ]; then
  echo "❌ Failed to create media container"; exit 1
fi
echo "✓ container: $CONTAINER_ID"

# Step 2: Publish
curl -sf -X POST "https://graph.facebook.com/v20.0/${META_IG_USER_ID}/media_publish" \
  -d "creation_id=${CONTAINER_ID}" \
  -d "access_token=${META_PAGE_TOKEN}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"✓ Published to IG. id={d.get('id')}\"); exit(0 if 'id' in d else 1)"