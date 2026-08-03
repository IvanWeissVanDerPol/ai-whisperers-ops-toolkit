#!/usr/bin/env bash
# trace_cleanup.sh — R17: Prevent traces/ from growing unbounded
# Keeps last 30 days of trace files; deletes older.
# Watchdog semantic (R16): exit 0 even if nothing was deleted.
set -u

TRACES_DIR=/root/.hermes/state/traces
RETAIN_DAYS=${TRACE_RETAIN_DAYS:-30}

if [ ! -d "$TRACES_DIR" ]; then
  echo "trace_cleanup: $TRACES_DIR does not exist (nothing to do)"
  exit 0
fi

BEFORE=$(du -sk "$TRACES_DIR" 2>/dev/null | awk '{print $1}')
DELETED=$(find "$TRACES_DIR" -type f -name "*.jsonl" -mtime +$RETAIN_DAYS -print -delete | wc -l)
AFTER=$(du -sk "$TRACES_DIR" 2>/dev/null | awk '{print $1}')

if [ -z "$BEFORE" ]; then BEFORE=0; fi
if [ -z "$AFTER" ]; then AFTER=0; fi
SAVED=$((BEFORE - AFTER))

echo "trace_cleanup: deleted=$DELETED retained_size=${AFTER}KB freed=${SAVED}KB (retention=${RETAIN_DAYS}d)"
exit 0
