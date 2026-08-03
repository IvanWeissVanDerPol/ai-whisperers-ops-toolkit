#!/usr/bin/env bash
# Surgically remove the dead @horizondatawave/meta-mcp block from
# ~/.hermes/config.yaml. We can't use 'hermes config set' for top-level keys
# in a list, so we do a precise sed strip and verify afterwards.
#
# Idempotent. Safe to re-run.
set -euo pipefail

CFG="$HOME/.hermes/config.yaml"
BAK_DIR="$HOME/.hermes/backups"
mkdir -p "$BAK_DIR"

stamp=$(date +%Y%m%d%H%M%S)
cp "$CFG" "$BAK_DIR/config.scrubbed-fb-meta.$stamp.yaml"
echo "→ backup: $BAK_DIR/config.scrubbed-fb-meta.$stamp.yaml"

python3 - <<'PY'
import re, sys
from pathlib import Path

p = Path("/root/.hermes/config.yaml")
src = p.read_text()
orig = src

# Delete the entire 'facebook-meta:' top-level block plus blank lines after it.
# The block runs from '  facebook-meta:' through the next non-indented line OR EOF.
pattern = re.compile(
    r"^  facebook-meta:\n(?:    [^\n]*\n|\n)+",
    re.MULTILINE,
)
src2, n = pattern.subn("", src)
if n == 0:
    print("[OK] no facebook-meta block found — nothing to scrub")
    sys.exit(0)

p.write_text(src2)
print(f"[OK] scrubbed {n} facebook-meta block(s) from config.yaml")
PY

echo "---verification---"
if grep -nE "facebook-meta|horizondatawave/meta-mcp" "$CFG" 2>/dev/null; then
  echo "[FAIL] dead references still present — manual review required"
  exit 1
fi
echo "[OK] dead references gone"

# Sanity: count top-level keys before & after; should match expected deltas.
echo "---active MCPs after scrub---"
hermes mcp list 2>&1 | head -20
