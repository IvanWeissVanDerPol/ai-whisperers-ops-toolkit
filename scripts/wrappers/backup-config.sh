#!/usr/bin/env bash
# Hermes Config Backup — backs up skills, profiles, cron jobs, custom hooks
# Runs daily at 03:00 UTC (midnight BRT, before healthcheck)
set -euo pipefail

BACKUP_ROOT="/root/.hermes/backups/daily"
mkdir -p "$BACKUP_ROOT"
TS=$(date +%Y%m%d-%H%M%S)
DEST="$BACKUP_ROOT/$TS"
mkdir -p "$DEST"

# Skills (only custom ones, exclude community/*, repos/*, optional-skills)
echo "Backing up custom skills..."
SKIP_PATTERNS=("community" "repos" "optional-skills" "plugins" "hermes-agent" "wondelai-skills" "superpowers-zh" "autonomous-ai-agents" "autonomous-multi-phase-execution" "wondelai")
for skill_dir in /root/.hermes/skills/*/; do
    name=$(basename "$skill_dir")
    skip=0
    for pat in "${SKIP_PATTERNS[@]}"; do
        if [[ "$name" == "$pat" ]]; then
            skip=1
            break
        fi
    done
    if [[ $skip -eq 1 ]]; then continue; fi
    # Only back up SKILL.md and references, not embedded models/data
    if [[ -f "$skill_dir/SKILL.md" ]]; then
        find "$skill_dir" -maxdepth 2 \( -name "SKILL.md" -o -name "*.md" -o -name "*.py" -o -name "*.sh" -o -name "*.json" -o -name "*.yaml" \) \
            -print0 2>/dev/null | tar czf "$DEST/skill-$name.tar.gz" --null -T - 2>/dev/null || true
    fi
done

# Profiles (only SOUL.md + config.yaml, not the full skill symlink tree)
echo "Backing up profile metadata..."
for profile_dir in /root/.hermes/profiles/*/; do
    name=$(basename "$profile_dir")
    if [[ -d "$profile_dir" ]]; then
        # Just SOUL.md, config.yaml, and any custom files at root level
        tar czf "$DEST/profile-$name.tar.gz" \
            -C "/root/.hermes/profiles" "$name/SOUL.md" "$name/config.yaml" 2>/dev/null || \
        # Fallback: just include whatever non-symlink files exist at root
        find "$profile_dir" -maxdepth 1 -type f -print0 2>/dev/null | \
            tar czf "$DEST/profile-$name.tar.gz" --null -C "/root/.hermes/profiles" -T - 2>/dev/null || true
    fi
done

# Cron jobs (JSON)
echo "Backing up cron jobs..."
crontab -l > "$DEST/crontab.txt" 2>/dev/null || true
hermes cron list 2>/dev/null > "$DEST/hermes-cron-list.txt" || true

# Kanban DBs (SQLite — all boards + default)
# Uses SQLite .backup for safe online copy (handles WAL/SHM correctly)
echo "Backing up kanban databases..."
if command -v sqlite3 &> /dev/null; then
    # Default board lives at <root>/kanban.db (legacy pre-boards path)
    # Note: <root>/kanban/kanban.db is OLDER legacy path that may or may not exist
    if [ -f /root/.hermes/kanban.db ]; then
        sqlite3 /root/.hermes/kanban.db ".backup '$DEST/kanban-default.db'" 2>/dev/null || true
    elif [ -f /root/.hermes/kanban/kanban.db ]; then
        sqlite3 /root/.hermes/kanban/kanban.db ".backup '$DEST/kanban-default.db'" 2>/dev/null || true
    fi
    # Other boards at <root>/kanban/boards/<slug>/kanban.db
    for db in /root/.hermes/kanban/boards/*/kanban.db; do
        [ -f "$db" ] || continue
        slug=$(basename "$(dirname "$db")")
        sqlite3 "$db" ".backup '$DEST/kanban-${slug}.db'" 2>/dev/null || true
    done
else
    # Fallback: just copy the files (less safe with active DBs but workable)
    mkdir -p "$DEST/kanban"
    if [ -f /root/.hermes/kanban.db ]; then
        cp -p /root/.hermes/kanban.db "$DEST/kanban/default.db" 2>/dev/null || true
    elif [ -f /root/.hermes/kanban/kanban.db ]; then
        cp -p /root/.hermes/kanban/kanban.db "$DEST/kanban/default.db" 2>/dev/null || true
    fi
    for db in /root/.hermes/kanban/boards/*/kanban.db; do
        [ -f "$db" ] || continue
        slug=$(basename "$(dirname "$db")")
        cp -p "$db" "$DEST/kanban/${slug}.db" 2>/dev/null || true
    done
fi

# Config
cp /root/.hermes/config.yaml "$DEST/config.yaml" 2>/dev/null || true
cp /root/.hermes/.env "$DEST/env-backup" 2>/dev/null || true  # includes keys, consider encrypting

# Custom hooks
cp -r /root/.hermes/hooks "$DEST/hooks" 2>/dev/null || true

# Prune old backups (keep 7 days)
find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true

# Report
SIZE=$(du -sh "$DEST" | cut -f1)
COUNT=$(ls -1 "$DEST" | wc -l)
echo "✓ Backup complete: $DEST ($SIZE, $COUNT files)"
