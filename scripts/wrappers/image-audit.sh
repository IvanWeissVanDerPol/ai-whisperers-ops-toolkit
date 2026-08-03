#!/usr/bin/env bash
# Image library audit — what's in /root/.hermes/images, by category, by size.
# Helps me pick the right image for a content slot quickly.

set -euo pipefail
ROOT="/root/.hermes/images"

echo "=== Image Library Audit ($(date '+%Y-%m-%d')) ==="
echo ""

# Top-level categories
echo "--- Top-level categories ---"
du -sh "$ROOT"/*/ 2>/dev/null | sort -hr | head -20
echo ""

# Total counts
TOTAL=$(find "$ROOT" -type f \( -name "*.png" -o -name "*.webp" -o -name "*.jpg" \) | wc -l)
TOTAL_SIZE=$(du -sh "$ROOT" 2>/dev/null | cut -f1)
echo "Total: $TOTAL files · $TOTAL_SIZE"
echo ""

# PNG vs WebP counts
PNG=$(find "$ROOT" -name "*.png" | wc -l)
WEBP=$(find "$ROOT" -name "*.webp" | wc -l)
JPG=$(find "$ROOT" -name "*.jpg" | wc -l)
echo "Format breakdown: PNG=$PNG · WebP=$WEBP · JPG=$JPG"
echo ""

# Largest 10 files (potential bloat)
echo "--- Top 10 largest files ---"
find "$ROOT" -type f -name "*.png" -o -name "*.webp" -o -name "*.jpg" 2>/dev/null | \
  xargs -I{} stat -c '%s %n' {} 2>/dev/null | sort -rn | head -10 | \
  awk '{ printf "  %8.1f MB  %s\n", $1/1024/1024, $2 }'
echo ""

# Manifests
echo "--- Manifests present ---"
find "$ROOT" -name "manifest.json" -exec dirname {} \;