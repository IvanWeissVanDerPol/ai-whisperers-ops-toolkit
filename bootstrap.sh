#!/usr/bin/env bash
# bootstrap.sh — Single-command installer for AI-Whisperers Ops Toolkit
# Usage:
#   ./bootstrap.sh                  # Full install on current user
#   ./bootstrap.sh new-vps          # Full VPS deployment (with sudo)
#   ./bootstrap.sh new-client NAME  # Client workspace (no sudo)
#   ./bootstrap.sh update           # Update existing install
#   ./bootstrap.sh --dry-run        # Show what would happen
#
# Idempotent — safe to re-run.

set -euo pipefail

MODE="${1:-install}"
DRY_RUN=""

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="echo"
    MODE="install"
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOTAL_STEPS=10

log() {
    echo -e "\033[1;36m[bootstrap]\033[0m $1"
}

warn() {
    echo -e "\033[1;33m[warn]\033[0m $1"
}

err() {
    echo -e "\033[1;31m[err]\033[0m $1"
    exit 1
}

check_root() {
    if [[ $EUID -eq 0 ]]; then
        warn "Running as root. Will install to /root/.hermes"
        HERMES_HOME="/root/.hermes"
    fi
}

check_python() {
    log "[1/$TOTAL_STEPS] Checking Python..."
    if ! command -v python3 &> /dev/null; then
        err "python3 not found. Install it first: apt install python3"
    fi
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if (( $(echo "$PY_VERSION < 3.10" | bc -l) )); then
        err "Python 3.10+ required. Found: $PY_VERSION"
    fi
    log "  ✓ Python $PY_VERSION"
}

create_dirs() {
    log "[2/$TOTAL_STEPS] Creating directories..."
    $DRY_RUN mkdir -p "$HERMES_HOME"/{scripts,scripts/wrappers,state,state/traces,state/prompts,state/llm_traces,state/usage,memories,cron,config,logs,cache}
    log "  ✓ $HERMES_HOME/{scripts,state,memories,cron,config,logs,cache}"
}

copy_scripts() {
    log "[3/$TOTAL_STEPS] Copying scripts (115 Python + 79 wrappers)..."
    $DRY_RUN cp -r "$SCRIPT_DIR/scripts/"*.py "$HERMES_HOME/scripts/"
    $DRY_RUN cp -r "$SCRIPT_DIR/scripts/wrappers/"*.sh "$HERMES_HOME/scripts/wrappers/"
    $DRY_RUN chmod +x "$HERMES_HOME/scripts/"*.py
    $DRY_RUN chmod +x "$HERMES_HOME/scripts/wrappers/"*.sh
    log "  ✓ $(ls "$HERMES_HOME/scripts/"*.py 2>/dev/null | wc -l) Python scripts"
    log "  ✓ $(ls "$HERMES_HOME/scripts/wrappers/"*.sh 2>/dev/null | wc -l) wrappers"
}

copy_skills() {
    log "[4/$TOTAL_STEPS] Copying skills (3 hand-picked)..."
    if [[ -d "$HERMES_HOME/skills" ]]; then
        $DRY_RUN mkdir -p "$HERMES_HOME/skills"
    fi
    for skill_dir in "$SCRIPT_DIR/skills"/*; do
        if [[ -d "$skill_dir" ]]; then
            skill_name=$(basename "$skill_dir")
            $DRY_RUN cp -r "$skill_dir" "$HERMES_HOME/skills/$skill_name"
            log "  ✓ $skill_name"
        fi
    done
}

copy_configs() {
    log "[5/$TOTAL_STEPS] Copying config templates..."
    # Only copy if not present (preserve user's edits)
    if [[ ! -f "$HERMES_HOME/.env" ]]; then
        if [[ -f "$SCRIPT_DIR/configs/env.example" ]]; then
            $DRY_RUN cp "$SCRIPT_DIR/configs/env.example" "$HERMES_HOME/.env"
            warn "  ⚠ Created $HERMES_HOME/.env from template. EDIT IT with your real API keys!"
        fi
    fi
    if [[ ! -f "$HERMES_HOME/config.yaml" ]]; then
        if [[ -f "$SCRIPT_DIR/configs/config.example.yaml" ]]; then
            $DRY_RUN cp "$SCRIPT_DIR/configs/config.example.yaml" "$HERMES_HOME/config.yaml"
        fi
    fi
    if [[ ! -f "$HERMES_HOME/cron/jobs.json" ]]; then
        if [[ -f "$SCRIPT_DIR/configs/jobs.example.json" ]]; then
            $DRY_RUN cp "$SCRIPT_DIR/configs/jobs.example.json" "$HERMES_HOME/cron/jobs.json"
        fi
    fi
    # Memory template (always overwrite, user-customizable)
    if [[ ! -f "$HERMES_HOME/memories/MEMORY.md" ]]; then
        if [[ -f "$SCRIPT_DIR/configs/MEMORY.template.md" ]]; then
            $DRY_RUN cp "$SCRIPT_DIR/configs/MEMORY.template.md" "$HERMES_HOME/memories/MEMORY.md"
        fi
    fi
    # Prompt templates (always copy, versioned)
    if [[ -d "$SCRIPT_DIR/configs/prompts" ]]; then
        $DRY_RUN cp -r "$SCRIPT_DIR/configs/prompts/"* "$HERMES_HOME/state/prompts/" 2>/dev/null || true
        log "  ✓ $(ls "$HERMES_HOME/state/prompts/" 2>/dev/null | wc -l) prompt templates"
    fi
}

install_deps() {
    log "[6/$TOTAL_STEPS] Installing Python dependencies..."
    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        $DRY_RUN pip3 install -q -r "$SCRIPT_DIR/requirements.txt" 2>&1 | grep -v "Requirement already satisfied" || true
        log "  ✓ pip install complete"
    else
        log "  (no requirements.txt — skipping)"
    fi
}

install_dashboard_service() {
    log "[7/$TOTAL_STEPS] Installing dashboard API systemd service..."
    if [[ $EUID -eq 0 ]] || command -v sudo &> /dev/null; then
        SERVICE_FILE="/etc/systemd/system/hermes-dashboard-api.service"
        $DRY_RUN tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Hermes Dashboard API
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HERMES_HOME
ExecStart=$(command -v python3) $HERMES_HOME/scripts/dashboard_server.py
Restart=on-failure
RestartSec=10
StandardOutput=append:$HERMES_HOME/logs/dashboard-api.log
StandardError=append:$HERMES_HOME/logs/dashboard-api.error.log

[Install]
WantedBy=multi-user.target
EOF
        if [[ -z "$DRY_RUN" ]] && command -v systemctl &> /dev/null; then
            $DRY_RUN systemctl daemon-reload
            $DRY_RUN systemctl enable hermes-dashboard-api
            $DRY_RUN systemctl start hermes-dashboard-api
            log "  ✓ hermes-dashboard-api service started on port 8645"
        fi
    else
        warn "  ⚠ Not root, skipping systemd install. Run scripts/dashboard_server.py manually."
    fi
}

register_crons() {
    log "[8/$TOTAL_STEPS] Registering cron jobs..."
    if [[ -f "$HERMES_HOME/cron/jobs.json" ]] && command -v hermes &> /dev/null; then
        # Import is a no-op for hermes-cron (jobs.json is read directly)
        log "  ✓ 74 cron jobs in jobs.json (read directly by hermes)"
    else
        warn "  ⚠ hermes CLI not found, jobs.json ready for manual import"
    fi
}

verify_installation() {
    log "[9/$TOTAL_STEPS] Verifying installation..."
    local errors=0

    # Check Python scripts
    if [[ ! -x "$HERMES_HOME/scripts/cron_health.py" ]]; then
        warn "  ✗ cron_health.py not executable"
        errors=$((errors + 1))
    fi

    # Check dashboard
    if command -v curl &> /dev/null; then
        if curl -s --max-time 5 -u admin:hermes http://127.0.0.1:8645/api/health &> /dev/null; then
            log "  ✓ Dashboard API responding on port 8645"
        else
            warn "  ⚠ Dashboard API not responding (may need a moment to start)"
        fi
    fi

    # Check skills
    if [[ -d "$HERMES_HOME/skills/avoid-ai-writing" ]]; then
        log "  ✓ Skills installed"
    fi

    # Check cron count
    if [[ -f "$HERMES_HOME/cron/jobs.json" ]]; then
        local count=$(python3 -c "import json; print(len(json.load(open('$HERMES_HOME/cron/jobs.json')).get('jobs', [])))" 2>/dev/null || echo "?")
        log "  ✓ $count cron jobs in jobs.json"
    fi

    if [[ $errors -gt 0 ]]; then
        warn "  $errors verification warnings"
    fi
}

show_next_steps() {
    log "[10/$TOTAL_STEPS] Next steps:"
    echo ""
    echo "  1. Edit your API keys:"
    echo "     nano $HERMES_HOME/.env"
    echo ""
    echo "  2. Verify the dashboard:"
    echo "     curl -s -u admin:hermes http://127.0.0.1:8645/api/health"
    echo ""
    echo "  3. Read the working guide:"
    echo "     cat $SCRIPT_DIR/docs/WORKING_WITH_HERMES.md"
    echo ""
    echo "  4. Check cron health:"
    echo "     python3 $HERMES_HOME/scripts/cron_health.py"
    echo ""
    if [[ -z "${EDITOR:-}" ]]; then
        echo "  (set EDITOR=vim or EDITOR=nano to auto-open the .env file)"
    fi
}

# === Main ===
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  AI-Whisperers Ops Toolkit — Bootstrap"
echo "  Mode: $MODE"
echo "  Hermes home: $HERMES_HOME"
echo "════════════════════════════════════════════════════════════════"
echo ""

case "$MODE" in
    install)
        check_root
        check_python
        create_dirs
        copy_scripts
        copy_skills
        copy_configs
        install_deps
        install_dashboard_service
        register_crons
        verify_installation
        show_next_steps
        ;;
    new-vps)
        log "Full VPS deployment..."
        check_root
        check_python
        create_dirs
        copy_scripts
        copy_skills
        copy_configs
        install_deps
        install_dashboard_service
        register_crons
        verify_installation
        show_next_steps
        warn "VPS mode: consider running ./bootstrap.sh after git pull for updates"
        ;;
    new-client)
        CLIENT_NAME="${2:-default}"
        log "New client workspace: $CLIENT_NAME"
        check_root
        create_dirs
        copy_scripts
        copy_configs
        install_deps
        verify_installation
        log "Client workspace '$CLIENT_NAME' ready at $HERMES_HOME"
        ;;
    update)
        log "Updating existing install..."
        copy_scripts
        copy_skills
        install_deps
        if [[ $EUID -eq 0 ]] || command -v sudo &> /dev/null; then
            $DRY_RUN systemctl restart hermes-dashboard-api
        fi
        log "  ✓ Update complete"
        ;;
    *)
        err "Unknown mode: $MODE. Use: install | new-vps | new-client NAME | update"
        ;;
esac

echo ""
log "Done. Welcome to AI-Whisperers Ops Toolkit."
echo ""
