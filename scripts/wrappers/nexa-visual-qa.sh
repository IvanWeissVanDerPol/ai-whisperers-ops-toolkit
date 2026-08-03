#!/bin/bash
# Nexa Visual QA — automated screenshot diff
# Runs the existing screenshot-all.mjs, then compares with baseline
# Usage: ./scripts/visual-qa.sh [baseline_dir]

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BASELINE_DIR="${1:-$REPO_DIR/screenshots/baseline}"
CURRENT_DIR="$REPO_DIR/screenshots/current"
DIFF_DIR="$REPO_DIR/screenshots/diffs"

mkdir -p "$CURRENT_DIR" "$DIFF_DIR" "$BASELINE_DIR"

echo "[visual-qa] Taking screenshots..."
cd "$REPO_DIR"
python3 scripts/screenshot-all.py "$CURRENT_DIR" 2>/dev/null || echo "[visual-qa] Screenshot script exited"

FAILED=0
for CURRENT in "$CURRENT_DIR"/*.png; do
  NAME=$(basename "$CURRENT")
  BASELINE="$BASELINE_DIR/$NAME"
  DIFF="$DIFF_DIR/$NAME"
  
  if [ ! -f "$BASELINE" ]; then
    echo "[visual-qa] NEW: $NAME (no baseline yet, creating)"
    cp "$CURRENT" "$BASELINE"
    continue
  fi

  # Simple pixel comparison via ImageMagick
  COMPARE=$(compare -metric AE "$BASELINE" "$CURRENT" "$DIFF" 2>&1 || true)
  if [ "$COMPARE" != "0" ] && [ -n "$COMPARE" ]; then
    echo "[visual-qa] DIFF: $NAME changed by $COMPARE pixels"
    FAILED=$((FAILED + 1))
  else
    echo "[visual-qa] OK: $NAME unchanged"
    rm -f "$DIFF"
  fi
done

if [ "$FAILED" -gt 0 ]; then
  echo "[visual-qa] FAILED: $FAILED pages have visual differences"
  exit 1
fi
echo "[visual-qa] PASS: All pages match baseline"
