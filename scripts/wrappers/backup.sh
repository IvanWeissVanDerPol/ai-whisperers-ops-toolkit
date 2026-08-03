#!/usr/bin/env bash
# Ometz full-site backup — git bundle + content JSONs + site.json snapshot.
# Stores dated tarball in /root/backups/ometz/.

set -euo pipefail
APP_DIR="/root/paragu-ai-platform/apps/dra-gabriela"
BACKUP_DIR="/root/backups/ometz"
DATE=$(date +%Y%m%d-%H%M)

mkdir -p "$BACKUP_DIR"

cd "$(dirname "$APP_DIR")" || exit 1

# 1. git bundle (full history, portable)
git bundle create "${BACKUP_DIR}/${DATE}-paragu-ai-platform.bundle" --all 2>/dev/null

# 2. content JSONs snapshot
tar czf "${BACKUP_DIR}/${DATE}-content-json.tar.gz" \
  -C "$APP_DIR" content/ 2>/dev/null

# 2b. nexa-pages (if it exists, only present on some sites)
if [ -d "$APP_DIR/nexa-pages" ]; then
  tar czf "${BACKUP_DIR}/${DATE}-nexa-pages.tar.gz" \
    -C "$APP_DIR" nexa-pages/ 2>/dev/null || true
fi

# 3. site config snapshot (NOT including secrets — just site.json/tokens.json/images.json)
cp "$APP_DIR/site.json" "$BACKUP_DIR/${DATE}-site.json" 2>/dev/null || true
cp "$APP_DIR/tokens.json" "$BACKUP_DIR/${DATE}-tokens.json" 2>/dev/null || true

# 4. Keep last 10 backups
cd "$BACKUP_DIR" && ls -1t | tail -n +11 | xargs -I{} rm -f "{}"

echo "✓ ometz backup: ${DATE} → $BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -5