#!/usr/bin/env bash
# LQV preflight check — runs before every deploy.
#
# Verifies:
# 1. All key data files exist + non-zero
# 2. v6 hero composite exists and is >500 KB
# 3. lqv-map.js has no syntax errors
# 4. index.html has all the new sections
# 5. No 0-byte files in the public path
# 6. Streams overlay SVG is valid

set -e
# Canonical: /root/la-quebrada-viva (the production repo). Legacy fallbacks
# below kept in case the script is invoked from an older checkout.
WEB_DIR="/root/la-quebrada-viva/splats/exports/web"
[ ! -d "$WEB_DIR" ] && WEB_DIR="/root/.hermes/lqv-splat/exports/web"
[ ! -d "$WEB_DIR" ] && WEB_DIR="/tmp/lqv-scan/splats/exports/web"
cd "$WEB_DIR"

err() { echo "✗ FAIL: $*" 1>&2; }
ok()  { echo "✓ OK:   $*"; }

echo "=== LQV preflight check ==="
echo

# 1. All key data files
for f in data/canopy_classes.geojson data/hydrography_dem_v2.geojson data/osm_buildings_near.geojson \
         data/osm_roads_near.geojson data/osm_water_v2.geojson data/gbif_-25.6073_-57.0355_30km.csv \
         data/soil_actual.json data/lqv_bundle.geojson data/lqv-map.js; do
  if [ -f "$f" ] && [ -s "$f" ]; then
    ok "$f exists ($(stat -c %s "$f") bytes)"
  else
    err "$f missing or empty"
  fi
done
if [ -f "index.html" ] && [ -s "index.html" ]; then
  ok "index.html exists ($(stat -c %s "index.html") bytes)"
else
  err "index.html missing or empty"
fi

# 2. v6 hero
if [ -f "data/preview/lqv_composite_v6.webp" ]; then
  sz=$(stat -c %s "data/preview/lqv_composite_v6.webp")
  if [ "$sz" -gt 500000 ]; then
    ok "v6 hero composite is $sz bytes (>$500K expected)"
  else
    err "v6 hero composite is $sz bytes, expected >500K"
  fi
else
  err "v6 hero composite missing"
fi

# 3. lqv-map.js syntax
if node --check data/lqv-map.js 2>&1 | grep -q error; then
  err "lqv-map.js has syntax errors"
  node --check data/lqv-map.js
else
  ok "lqv-map.js has no syntax errors"
fi

# 4. index.html has all key sections (current build, post-unified-viewer rewrite)
# These are the 5 main page sections in the current index.html (the page was
# rebuilt in 2026-07 around the unified /mapa viewer; the previous
# "lqv_composite_v6.webp" / "compare-panel" / "lqv_4up_poster" / "map-reset"
# / "external-links" names are from the OLD pre-unified build and have been
# deliberately retired).
for section in "La Quebrada Viva" "The Land" "The Water" "The Forest" "The Build" "The Layers" "What this data" "Come see it"; do
  if grep -qF "$section" index.html 2>/dev/null; then
    ok "index.html has '$section' section"
  else
    err "index.html missing '$section' section"
  fi
done

# 4b. All <img src=./data/preview/*> files referenced by index.html actually
# exist (the unified-viewer rewrite kept image references but stopped
# generating the previews; the lqv-splat-pipeline skill calls this out as the
# "DEPLOY PIPELINE ONLY SHIPS splats/exports/web/" gotcha combined with the
# "data/preview/ directory is gitignored from the deploy" gotcha).
imgdir="data/preview"
[ -d "$imgdir" ] || mkdir -p "$imgdir"
# extract src attributes starting with ./data/preview/ or data/preview/
# (use a for-loop on a subshell so [ -f ] is evaluated in the right cwd —
#  pipes to `while` break exit-status propagation when -e is set).
for rel in $(grep -oE 'src=["\x27](\./)?data/preview/[^"\x27]+["\x27]' index.html \
              | sed -E 's/^src=["\x27](\.\/)?//; s/["\x27]$//' | sort -u); do
  if [ -f "$rel" ] && [ -s "$rel" ]; then
    sz=$(stat -c %s "$rel")
    ok "preview '$rel' present ($sz b)"
  else
    err "preview '$rel' missing or empty"
  fi
done

# 5. No 0-byte files
empty_files=$(find . -type f -size 0 | wc -l)
if [ "$empty_files" -gt 0 ]; then
  err "Found $empty_files 0-byte files"
  find . -type f -size 0
else
  ok "No 0-byte files in public path"
fi

# 6. Streams overlay SVG
if [ -f "data/preview/streams_overlay.svg" ]; then
  sz=$(stat -c %s "data/preview/streams_overlay.svg")
  if [ "$sz" -gt 1000 ]; then
    ok "streams_overlay.svg is $sz bytes (>$1K expected)"
  else
    err "streams_overlay.svg is $sz bytes, expected >1K"
  fi
  # XML well-formedness check
  if python3 -c "import xml.etree.ElementTree as ET; ET.parse('data/preview/streams_overlay.svg')" 2>&1; then
    ok "streams_overlay.svg is well-formed XML"
  else
    err "streams_overlay.svg is NOT well-formed XML"
  fi
else
  err "streams_overlay.svg missing"
fi

echo
echo "=== Pre-flight check complete ==="
