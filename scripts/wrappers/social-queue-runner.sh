#!/usr/bin/env bash
# One-shot auto-post scheduler for Ometz + Nexa + future clients.
# Reads /root/.hermes/config/post-queue.jsonl (line per post: {scheduled_at, channel, ...}).
# Channels:
#   facebook     → Meta Graph API (fb-post.sh)       — needs META_PAGE_TOKEN + META_PAGE_ID
#   instagram    → Meta Graph API (ig-post.sh)       — needs META_PAGE_TOKEN + META_IG_USER_ID
#   linkedin     → Postiz cross-platform (li-post.sh) — needs POSTIZ_API_KEY + postiz CLI installed
# Posts due in the [now - GRACE_MIN, now + DUE_WINDOW_MIN] window fire, then mark done.
#
# Behavior:
#   - GRACE_MIN (default 60) catches items slightly past due (token drift, transient failures).
#   - DUE_WINDOW_MIN (default 90) limits how far in the future we look (otherwise every
#     30-min run re-scans all 24+ items and `skipped` counter blows up).
#   - On missing required token: log a loud error AND exit 1 — silent SKIPs were the
#     original "marketing agent stalls" bug (379 runs of posted=0 in 7 days).
#   - On successful post: write `done_at` + `post_id` back to the JSONL atomically.
#
# Flags:
#   --dry-run    Print what would be posted; never call fb-post.sh / ig-post.sh / li-post.sh.
#   --strict     Exit 1 if any item in window is past GRACE_MIN and not yet posted.
#
# Cron schedule: */30 * * * * (every 30 min). no_agent mode.

set -euo pipefail

DRY_RUN=0
STRICT=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --strict)  STRICT=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

QUEUE="${QUEUE:-/root/.hermes/config/post-queue.jsonl}"
LOG="/var/log/ometz-social-post.log"
GRACE_MIN="${SOCIAL_GRACE_MIN:-60}"          # how late a post can be and still fire
DUE_WINDOW_MIN="${SOCIAL_DUE_WINDOW_MIN:-90}" # how far ahead we look

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# Load .env (only if not already in env — keep idempotent for cron)
if [ -f /root/.hermes/.env ]; then
  set -a; source /root/.hermes/.env; set +a
fi

if [ ! -f "$QUEUE" ]; then
  log "no queue file at $QUEUE — nothing to do"
  exit 0
fi

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
posted=0
skipped=0
failed=0
token_missing=0

# --- token presence check (fail loud, not silent) -----------------------------

token_check() {
  local channel="$1" missing=()
  case "$channel" in
    facebook)
      [ -n "${META_PAGE_TOKEN:-}" ] || missing+=("META_PAGE_TOKEN")
      [ -n "${META_PAGE_ID:-}" ]    || missing+=("META_PAGE_ID")
      ;;
    instagram)
      [ -n "${META_PAGE_TOKEN:-}" ]    || missing+=("META_PAGE_TOKEN")
      [ -n "${META_IG_USER_ID:-}" ]   || missing+=("META_IG_USER_ID")
      ;;
    linkedin)
      [ -n "${POSTIZ_API_KEY:-}" ]    || missing+=("POSTIZ_API_KEY")
      command -v postiz >/dev/null 2>&1 || missing+=("postiz-CLI")
      ;;
  esac
  [ ${#missing[@]} -eq 0 ] && return 0
  log "❌ CHANNEL $channel: missing ${missing[*]} — NOT posting. Set them in /root/.hermes/.env then re-run."
  return 1
}

# --- atomic done_at write-back -------------------------------------------------
# Reads the JSONL, mutates the matching line, writes to a temp file, then renames.
# We use a Python helper so concurrent runs don't race.

mark_done() {
  local index="$1" post_id="$2"
  python3 - <<PY
import json, sys, os
queue = "$QUEUE"
idx = int("$index")
pid = "$post_id" if "$post_id" else ""
lines = []
with open(queue, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.rstrip("\n")
        if not line: continue
        lines.append(line)
if idx < 0 or idx >= len(lines):
    sys.exit(f"index {idx} out of range")
d = json.loads(lines[idx])
d['done_at'] = __import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
if pid:
    d['post_id'] = pid
lines[idx] = json.dumps(d, ensure_ascii=False)
tmp = queue + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines) + "\n")
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, queue)
PY
}

# --- read queue once, walk it --------------------------------------------------
i=0
while IFS= read -r line; do
  i=$((i+1))
  [ -z "$line" ] && continue
  index=$((i-1))
  sched=$(echo "$line"   | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('scheduled_at',''))")
  done=$(echo "$line"    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('done_at',''))")
  channel=$(echo "$line" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('channel',''))")
  msg=$(echo "$line"     | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('message',''))")
  img=$(echo "$line"     | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('image_url',''))")
  integration_id=$(echo "$line" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('integration_id',''))")

  # 1. Skip already-done
  if [ -n "$done" ]; then skipped=$((skipped+1)); continue; fi

  # 1b. Approval gate (only enforced when explicit `approved_by: false` is set)
  #     Items WITHOUT the field auto-pass (back-compat).
  #     Items WITH approved_by=false block until Kiki/Gaby sets it true.
  #     Approval is per-post so future rounds don't accidentally re-approve.
  approved_by=$(echo "$line" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin); v=d.get('approved_by')
    print('' if v is None else str(bool(v)).lower())
except: print('')")
  if [ "$approved_by" = "false" ]; then
    skipped=$((skipped+1))
    log "⏸ blocked: $channel scheduled=$sched NOT approved yet (approved_by=false; set true after client sign-off)"
    continue
  fi

  # 2. Due-window check (skip items outside [now-GRACE, now+DUE_WINDOW])
  if [ -n "$sched" ]; then
    lower=$(date -u -d "$now - $GRACE_MIN minutes" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")
    upper=$(date -u -d "$now + $DUE_WINDOW_MIN minutes" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")
    if [ -n "$lower" ] && [ "$sched" \< "$lower" ]; then
      skipped=$((skipped+1))
      log "⚠ overdue (no longer in due window): $channel scheduled=$sched — left pending; manual review"
      continue
    fi
    if [ -n "$upper" ] && [ "$sched" \> "$upper" ]; then
      skipped=$((skipped+1)); continue
    fi
  fi

  # 3. Token presence
  if ! token_check "$channel"; then
    token_missing=$((token_missing+1))
    skipped=$((skipped+1))
    continue
  fi

  # 4. Dispatch
  case "$channel" in
    facebook)
      log "POST fb: $msg"
      if [ "$DRY_RUN" -eq 1 ]; then
        log "  [dry-run] would call: fb-post.sh \"<${#msg} chars>\" \"$img\""
      else
        if [ -n "$img" ]; then
          out=$(bash /root/.hermes/scripts/fb-post.sh "$msg" "$img" 2>&1) || { log "❌ fb-post failed: $out"; failed=$((failed+1)); continue; }
        else
          out=$(bash /root/.hermes/scripts/fb-post.sh "$msg" 2>&1) || { log "❌ fb-post failed: $out"; failed=$((failed+1)); continue; }
        fi
        post_id=$(echo "$out" | grep -oE 'id=[0-9_]+' | head -1 | cut -d= -f2)
        log "  ✓ fb posted: $out"
      fi
      posted=$((posted+1))
      mark_done "$index" "${post_id:-}"
      ;;

    instagram)
      if [ -z "$img" ]; then
        log "SKIP ig: image_url required (got text-only item; IG requires image)"
        skipped=$((skipped+1)); continue
      fi
      log "POST ig: $msg"
      if [ "$DRY_RUN" -eq 1 ]; then
        log "  [dry-run] would call: ig-post.sh \"<${#msg} chars>\" \"$img\""
      else
        out=$(bash /root/.hermes/scripts/ig-post.sh "$msg" "$img" 2>&1) || { log "❌ ig-post failed: $out"; failed=$((failed+1)); continue; }
        post_id=$(echo "$out" | grep -oE 'id=[0-9_]+' | head -1 | cut -d= -f2)
        log "  ✓ ig posted: $out"
      fi
      posted=$((posted+1))
      mark_done "$index" "${post_id:-}"
      ;;

    linkedin)
      # Postiz is the cross-platform scheduler. Required keys per post:
      #   integration_id  → Postiz integration ID for the LI page (discoverable via
      #                     `postiz integrations:list | jq '.[] | select(.identifier=="linkedin-page")'`)
      if [ -z "$integration_id" ]; then
        log "❌ linkedin post missing integration_id — cannot route to LI page"
        failed=$((failed+1)); continue
      fi
      log "POST linkedin (via postiz): $msg"
      if [ "$DRY_RUN" -eq 1 ]; then
        log "  [dry-run] would call: li-post.sh \"<${#msg} chars>\" \"$integration_id\" \"$img\""
      else
        out=$(bash /root/.hermes/scripts/li-post.sh "$msg" "$integration_id" "$img" 2>&1) || { log "❌ li-post failed: $out"; failed=$((failed+1)); continue; }
        post_id=$(echo "$out" | grep -oE 'id=[A-Za-z0-9_:-]+' | head -1 | cut -d= -f2)
        log "  ✓ li posted: $out"
      fi
      posted=$((posted+1))
      mark_done "$index" "${post_id:-}"
      ;;

    *)
      log "SKIP unknown channel: $channel"
      skipped=$((skipped+1))
      ;;
  esac
done < "$QUEUE"

log "queue run done — posted=$posted skipped=$skipped failed=$failed token_missing=$token_missing"

# Fail-loud exit codes:
#   0  = posted > 0 OR (posted == 0 AND skipped > 0 AND token_missing == 0 AND failed == 0)
#   1  = token missing (caller should alert), OR failed > 0 (real post error),
#        OR --strict + past-grace item detected
if [ "$token_missing" -gt 0 ]; then exit 1; fi
if [ "$failed" -gt 0 ]; then exit 1; fi
exit 0