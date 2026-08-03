#!/usr/bin/env bash
# Bulk portfolio screenshot refresh across all major Ai-Whisperers client sites.
# Captures 1 hero shot per site for the showcase/portfolio page.

set -euo pipefail
OUT="/root/.hermes/images/portfolio/ai-whisperers"
mkdir -p "$OUT"

declare -a SITES=(
  "ometzdental|https://ometzdental.com/es"
  "dragabriela-legacy|https://dragabriela.paragu-ai.com/es"
  "nexa-paraguay|https://nexa.paragu-ai.com/en"
  "maskarada|https://maskarada.paragu-ai.com/"
  "reina-de-copas|https://reina-de-copas.paragu-ai.com/"
  "villa-mayor|https://villamayor.paragu-ai.com/"
  "hidrobaby-spa|https://hidrobaby-spa.paragu-ai.com/"
  "paragu-ai-marketing|https://paragu-ai.com/"
  "cronos-academy|https://cronos-academy.paragu-ai.com/"
  "superspuma|https://superspuma.paragu-ai.com/"
  "nosotras-seguras|https://nosotras-seguras.paragu-ai.com/"
  "vivi-estetica|https://viviesteticpy.paragu-ai.com/"
  "magnolia-peluqueria|https://magnolia-peluqueria.paragu-ai.com/"
)

ok=0; fail=0
for entry in "${SITES[@]}"; do
  IFS='|' read -r slug url <<< "$entry"
  outfile="$OUT/${slug}.png"
  printf "  %-25s " "$slug"
  if timeout 30 npx --yes playwright@latest screenshot \
       --viewport-size=1280,800 --wait-for-timeout=2500 \
       "$url" "$outfile" 2>/dev/null; then
    if [ -f "$outfile" ]; then
      size=$(stat -c%s "$outfile")
      printf "✓ %d KB\n" $((size / 1024))
      ok=$((ok+1))
    else
      echo "FAIL (no file)"
      fail=$((fail+1))
    fi
  else
    echo "FAIL (timeout/error)"
    fail=$((fail+1))
  fi
done

echo ""
echo "✓ $ok captured · $fail failed → $OUT"