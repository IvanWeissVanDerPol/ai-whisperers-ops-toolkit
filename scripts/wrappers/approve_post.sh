#!/usr/bin/env bash
# approve_post.sh — flip approved_by on a queued post.
#
# Usage:
#   bash approve_post.sh <post_number>           # approve one
#   bash approve_post.sh --all                   # approve everything not-yet-done
#   bash approve_post.sh --round <n>             # approve a whole round (e.g. --round 2)
#   bash approve_post.sh --preview               # dry-run: show approval state per channel/round
#
# Stamps approver name + timestamp when flipping false → true.
# Writes atomic (tmp + os.replace) via python3 helper.
#
# Examples:
#   bash /root/.hermes/scripts/approve_post.sh 25           # approve Ometz post #25
#   bash /root/.hermes/scripts/approve_post.sh --round 2     # approve all Ometz round-2 FB
#   bash /root/.hermes/scripts/approve_post.sh --preview     # see current state
#
# Requires:
#   python3 (already on this host)
#
# Author: Erebus 2026-07-28 (per kanban task t_b4e05b10 follow-up)

set -euo pipefail
QUEUE="${QUEUE:-/root/.hermes/config/post-queue.jsonl}"
APPROVER="${APPROVER:-$(whoami)}"

if [ ! -f "$QUEUE" ]; then
  echo "no queue at $QUEUE" >&2; exit 1
fi

case "${1:-}" in
  --preview)
    python3 - "$QUEUE" <<'PY'
import json, sys, collections
q = sys.argv[1]
by_chan = collections.defaultdict(lambda: collections.Counter())
rows = []
for ln in open(q, encoding='utf-8'):
    if not ln.strip(): continue
    d = json.loads(ln)
    ab = d.get('approved_by')
    state = 'unset' if ab is None else ('true' if ab else 'false')
    by_chan[d['channel']][state] += 1
    rows.append((d.get('post_number', '?'), d['channel'], d.get('round', '?'), d.get('scheduled_at','?')[:10], state, d.get('approved_by_name','') or ''))
print(f"{'#':>4}  {'channel':<10} {'rnd':>3} {'scheduled':<10} {'state':<6} approved_by_name")
for r in sorted(rows, key=lambda r:(r[2] if isinstance(r[2],int) else 0, r[3])):
    print(f"{str(r[0]):>4}  {r[1]:<10} {str(r[2]):>3} {r[3]:<10} {r[4]:<6} {r[5]}")
print()
print("by channel × state:")
for c, sc in sorted(by_chan.items()):
    print(f"  {c:<10} {dict(sc)}")
PY
    ;;
  --all)
    python3 - "$QUEUE" "$APPROVER" <<'PY'
import json, sys, datetime
q, approver = sys.argv[1], sys.argv[2]
out = []
flipped = 0
for ln in open(q, encoding='utf-8'):
    if not ln.strip():
        out.append(ln); continue
    d = json.loads(ln)
    if d.get('approved_by') is False and not d.get('done_at'):
        d['approved_by'] = True
        d['approved_by_name'] = approver
        d['approved_at'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        flipped += 1
        out.append(json.dumps(d, ensure_ascii=False))
    else:
        out.append(ln)
import os
tmp = q + '.tmp'
open(tmp, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
os.replace(tmp, q)
print(f"approved {flipped} items (approver={approver})")
PY
    ;;
  --round)
    round_n="${2:-}"
    if [ -z "$round_n" ]; then echo "--round needs a number" >&2; exit 2; fi
    python3 - "$QUEUE" "$APPROVER" "$round_n" <<'PY'
import json, sys, datetime
q, approver, rnd = sys.argv[1], sys.argv[2], int(sys.argv[3])
out = []; flipped = 0
for ln in open(q, encoding='utf-8'):
    if not ln.strip(): out.append(ln); continue
    d = json.loads(ln)
    if d.get('round') == rnd and d.get('approved_by') is False and not d.get('done_at'):
        d['approved_by'] = True
        d['approved_by_name'] = approver
        d['approved_at'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        flipped += 1
        out.append(json.dumps(d, ensure_ascii=False))
    else:
        out.append(ln)
import os
tmp = q + '.tmp'
open(tmp, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
os.replace(tmp, q)
print(f"approved {flipped} items in round {rnd} (approver={approver})")
PY
    ;;
  '')
    echo "Usage: approve_post.sh <post_number> | --all | --round <n> | --preview" >&2
    exit 2
    ;;
  *)
    post_num="$1"
    python3 - "$QUEUE" "$APPROVER" "$post_num" <<'PY'
import json, sys, datetime
q, approver, pn = sys.argv[1], sys.argv[2], sys.argv[3]
out = []; flipped = 0; seen = False
for ln in open(q, encoding='utf-8'):
    if not ln.strip(): out.append(ln); continue
    d = json.loads(ln)
    if str(d.get('post_number')) == pn:
        seen = True
        if d.get('approved_by') is False:
            d['approved_by'] = True
            d['approved_by_name'] = approver
            d['approved_at'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            flipped += 1
            print(f"approved post #{pn} (channel={d['channel']}, scheduled={d.get('scheduled_at','')[:10]})")
        elif d.get('done_at'):
            print(f"post #{pn} already done_at={d['done_at']} — not modifying")
        else:
            print(f"post #{pn} already approved_by={d.get('approved_by')} (name={d.get('approved_by_name','-')})")
    out.append(json.dumps(d, ensure_ascii=False) if d.get('approved_by') or d.get('done_at') or str(d.get('post_number'))==pn else ln)
import os
if flipped:
    tmp = q + '.tmp'
    open(tmp, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    os.replace(tmp, q)
if not seen:
    print(f"post #{pn} not found in queue", file=sys.stderr); sys.exit(1)
PY
    ;;
esac
