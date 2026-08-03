#!/usr/bin/env bash
# Portfolio screenshot refresh — capture all 4 Ometz locales for portfolio showcase.
# Uses Playwright headless via Node.js. Outputs to /root/.hermes/images/portfolio/ometz/.
# Cron-friendly.

set -euo pipefail
APP_DIR="/root/paragu-ai-platform/apps/dra-gabriela"
OUT_DIR="/root/.hermes/images/portfolio/ometz"
mkdir -p "$OUT_DIR"

# Verify playwright is available
if ! command -v npx >/dev/null; then
  echo "FAIL: npx not in PATH"; exit 1
fi

# Locales + key paths to capture
declare -a SHOTS=(
  "es|/"
  "en|/"
  "es|/servicios"
  "es|/filosofia"
  "es|/contacto"
)

cd "$APP_DIR"
for entry in "${SHOTS[@]}"; do
  IFS='|' read -r locale path <<< "$entry"
  url="https://ometzdental.com/${locale}${path}"
  outfile="${OUT_DIR}/${locale}${path//\//_}.png"
  echo "capturing: $url → $outfile"
  npx --yes playwright@latest screenshot --viewport-size=1280,800 --wait-for-timeout=2000 "$url" "$outfile" 2>/dev/null || {
    echo "WARN: capture failed for $url"
  }
done

echo "✓ portfolio refresh complete → $OUT_DIR"
ls -lh "$OUT_DIR"