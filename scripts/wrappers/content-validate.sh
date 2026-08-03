#!/usr/bin/env bash
# Validate that all content JSONs parse cleanly + no orphan keys leak.
# Compares keys in es/en site.json against each other for drift detection.

set -euo pipefail
APP_DIR="/root/paragu-ai-platform/apps/dra-gabriela"

errors=0
warnings=0

# 1. JSON parse
for locale in en es; do
  for f in "$APP_DIR/content/${locale}"/*.json; do
    if ! python3 -m json.tool < "$f" > /dev/null 2>&1; then
      echo "FAIL json: $f"
      errors=$((errors + 1))
    fi
  done
done

# 2. Compare top-level keys in site.json (if exists)
es_site="$APP_DIR/content/es/site.json"
en_site="$APP_DIR/content/en/site.json"
if [ -f "$es_site" ] && [ -f "$en_site" ]; then
  es_keys=$(python3 -c "import json; print('\n'.join(sorted(json.load(open('$es_site')).keys())))")
  en_keys=$(python3 -c "import json; print('\n'.join(sorted(json.load(open('$en_site')).keys())))")
  diff=$(diff <(echo "$es_keys") <(echo "$en_keys") || true)
  if [ -n "$diff" ]; then
    echo "WARN site.json key drift:"
    echo "$diff" | head -10
    warnings=$((warnings + 1))
  fi
fi

# 3. Check for hardcoded locale paths in hrefs (a known anti-pattern)
hardcoded=$(grep -rE 'href[^:]*:[^"]*/(es|en|nl|de)/' "$APP_DIR/content/" 2>/dev/null | head -3 || true)
if [ -n "$hardcoded" ]; then
  echo "WARN hardcoded locale paths in content:"
  echo "$hardcoded"
  warnings=$((warnings + 1))
fi

# 4. Image ref check
if [ -f "$APP_DIR/images.json" ]; then
  refs=$(python3 -c "
import json
d = json.load(open('$APP_DIR/images.json'))
def walk(o):
    if isinstance(o, dict):
        for k,v in o.items():
            if k == 'src' and isinstance(v, str): yield v
            else: yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)
for src in sorted(set(walk(d))):
    if src.startswith('/images/'):
        print(src)
" 2>/dev/null)
  missing=0
  for ref in $refs; do
    if [ ! -f "$APP_DIR/public${ref}" ]; then
      echo "MISSING: public${ref}"
      missing=$((missing + 1))
      errors=$((errors + 1))
    fi
  done
fi

if [ $errors -eq 0 ] && [ $warnings -eq 0 ]; then
  echo "✓ content clean · all JSONs valid · no drift"
  exit 0
fi
echo "result: $errors errors, $warnings warnings"
exit 1