#!/usr/bin/env bash
# Append a post to the social queue.
# Usage:
#   queue-post.sh <channel> "<message>" <scheduled_at_iso> [image_url]
#   queue-post.sh linkedin "<message>" <scheduled_at_iso> "" <integration_id>
#
# Channels:
#   facebook   → Meta Graph API (fb-post.sh). image_url optional.
#   instagram  → Meta Graph API (ig-post.sh). image_url REQUIRED.
#   linkedin   → Postiz (li-post.sh). Pass integration_id in IMG slot OR via
#                --integration-id flag. image_url optional (LI accepts images).
#
# Examples:
#   queue-post.sh facebook "Hello" "2026-08-01T15:00:00Z"
#   queue-post.sh instagram "Hello" "2026-08-01T15:00:00Z" "https://x.com/i.jpg"
#   queue-post.sh linkedin "Hello" "2026-08-01T15:00:00Z" "" "postiz-li-integration-id"
#   queue-post.sh linkedin "Hello" "2026-08-01T15:00:00Z" "https://x.com/i.jpg" "postiz-li-id"

set -euo pipefail

# Parse args: allow --integration-id flag at any position.
CHANNEL=""
MSG=""
SCHED=""
IMG=""
INTEGRATION_ID=""

args=("$@")
i=0
while [ $i -lt ${#args[@]} ]; do
  arg="${args[$i]}"
  case "$arg" in
    --integration-id)
      INTEGRATION_ID="${args[$((i+1))]}"
      i=$((i+2))
      ;;
    -*)
      echo "unknown flag: $arg" >&2; exit 2 ;;
    *)
      if   [ -z "$CHANNEL" ]; then CHANNEL="$arg"
      elif [ -z "$MSG" ];     then MSG="$arg"
      elif [ -z "$SCHED" ];   then SCHED="$arg"
      elif [ -z "$IMG" ];     then IMG="$arg"
      fi
      i=$((i+1))
      ;;
  esac
done

: "${CHANNEL:?usage: queue-post.sh <channel> <message> <scheduled_at> [image_url] [--integration-id ID]}"
: "${MSG:?usage: queue-post.sh <channel> <message> <scheduled_at> [image_url] [--integration-id ID]}"
SCHED="${SCHED:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

case "$CHANNEL" in
  facebook|instagram) ;;
  linkedin)
    [ -z "$INTEGRATION_ID" ] && { echo "❌ linkedin requires --integration-id (Postiz integration ID for the LinkedIn page)" >&2; exit 1; }
    ;;
  *) echo "❌ unknown channel: $CHANNEL (expected: facebook|instagram|linkedin)" >&2; exit 1 ;;
esac

QUEUE="${QUEUE:-/root/.hermes/config/post-queue.jsonl}"
mkdir -p "$(dirname "$QUEUE")"

# Append as JSONL — use Python to escape the message safely.
SCHED="$SCHED" MSG="$MSG" IMG="$IMG" CHANNEL="$CHANNEL" INTEGRATION_ID="$INTEGRATION_ID" python3 - <<'PY'
import json, os
from datetime import datetime, timezone
queue = os.environ.get('QUEUE_OVERRIDE') or "/root/.hermes/config/post-queue.jsonl"
item = {
    'scheduled_at':   os.environ['SCHED'],
    'channel':        os.environ['CHANNEL'],
    'message':        os.environ['MSG'],
    'image_url':      os.environ['IMG'],
    'added_at':       datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
}
iid = os.environ.get('INTEGRATION_ID', '')
if iid:
    item['integration_id'] = iid
with open(queue, 'a', encoding='utf-8') as f:
    f.write(json.dumps(item, ensure_ascii=False) + '\n')
print(f"✓ queued [{item['channel']}] for {item['scheduled_at']}: {item['message'][:50]}...")
PY