#!/usr/bin/env bash
# Ometz auto-deploy — full pipeline: git → pnpm build → docker → service update → verify
# Usage: bash auto-deploy.sh [--skip-build] [--no-verify]
# Cron-safe. Idempotent. Returns 0 on success, 1 on failure (with reason logged).

set -euo pipefail

APP="dra-gabriela"
APP_DIR="/root/paragu-ai-platform/apps/${APP}"
REPO_ROOT="/root/paragu-ai-platform"
VPS="root@72.61.44.159"
SERVICE="${APP}_web"
LOG="/var/log/ometz-deploy.log"

mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

SKIP_BUILD=0
NO_VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --no-verify)  NO_VERIFY=1 ;;
  esac
done

cd "$APP_DIR" || { log "FAIL: cd $APP_DIR"; exit 1; }

# 1. git status check — abort if dirty (only the target app's dir, not the whole repo)
if [ -n "$(git status --porcelain -- "$APP_DIR" 2>/dev/null)" ]; then
  log "FAIL: working tree dirty in $APP_DIR — commit/stash before deploy"
  git status --porcelain -- "$APP_DIR"
  exit 1
fi

# 2. pull latest
log "git pull..."
git pull --ff-only 2>&1 | tee -a "$LOG"

# 3. build (unless skipped)
if [ "$SKIP_BUILD" = "0" ]; then
  log "pnpm build..."
  NEXT_BUILD_WORKERS=1 pnpm run build 2>&1 | tail -20 | tee -a "$LOG" || {
    log "FAIL: pnpm build failed"
    exit 1
  }
fi

# 4. docker image
VERSION=$(git rev-parse --short HEAD)
DATE=$(date +%Y%m%d-%H%M)
TAG="${APP}:prod-${VERSION}-${DATE}"

log "docker build: $TAG"
docker build -f "$APP_DIR/Dockerfile" -t "$TAG" -t "${APP}:prod" "$REPO_ROOT" 2>&1 | tail -10 | tee -a "$LOG" || {
  log "FAIL: docker build failed"
  exit 1
}

# 5. service update (rolling)
log "service update: $SERVICE → $TAG"
ssh "$VPS" "docker service update --image $TAG $SERVICE" 2>&1 | tee -a "$LOG" || {
  log "FAIL: docker service update failed"
  exit 1
}

# 6. verify
if [ "$NO_VERIFY" = "0" ]; then
  log "verify..."
  sleep 8
  HTTP=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 https://ometzdental.com/ || echo 000)
  if [ "$HTTP" != "200" ]; then
    log "FAIL: live site returned $HTTP (expected 200)"
    exit 1
  fi
  log "✓ deploy OK — live site $HTTP"
else
  log "deploy OK — verify skipped"
fi