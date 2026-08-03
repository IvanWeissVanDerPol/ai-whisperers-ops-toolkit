# Detailed Installation Guide

## Prerequisites

- Linux (Ubuntu 22.04+ recommended, Debian 12+ tested)
- Python 3.10+
- `git`, `curl`, `systemctl`
- sudo / root access
- ~500 MB free disk space

## Step 1: Clone

```bash
git clone https://github.REPLACE_ME.git
cd ai-whisperers-ops-toolkit
```

## Step 2: Run Bootstrap

```bash
./bootstrap.sh
```

The bootstrap script:
1. Creates `~/.hermes/scripts`, `~/.hermes/state`, `~/.hermes/memories`, `~/.hermes/cron`, `~/.hermes/skills`
2. Copies all 115 scripts + 79 wrappers
3. Copies 3 hand-picked skills (others auto-install on first use)
4. Installs Python dependencies from `requirements.txt`
5. Copies sanitized config templates
6. Imports 74 cron jobs
7. Installs systemd service for dashboard API
8. Starts the dashboard API on port 8645

## Step 3: Customize

```bash
# Edit env file with real API keys
cp ~/.hermes/.env.example ~/.hermes/.env
nano ~/.hermes/.env
```

Required env vars (fill these in):
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY` (or `LITELLM_BASE_URL` if using proxy)
- `MINIMAX_API_KEY`
- `TELEGRAM_BOT_TOKEN` (optional, for Telegram delivery)
- `TELEGRAM_HOME_CHANNEL` (optional, your channel ID)

## Step 4: Verify

```bash
# Dashboard should respond
curl -s -u admin:hermes http://127.0.0.1:8645/api/health
# Expected: {"status": "ok", ...}

# Cron health should report 74 jobs
python3 ~/.hermes/scripts/cron_health.py --json
# Expected: {"summary": {"total": 74, "healthy": 68, "broken": 6}}

# Cost router should find a working tier
python3 ~/.hermes/scripts/cost_router.py probe
# Expected: working_tiers: ["cerebras/gpt-oss-120b", ...]
```

## Step 5: Customize Memory

```bash
nano ~/.hermes/memories/MEMORY.md
```

Edit the "R23 user-feedback rules" entry to match your preferences.

## Troubleshooting

### "Script not found" when running a cron

You're trying to register a cron with `--script "foo.py --bar"`. Hermes stores the LITERAL string as the script name. Use a wrapper:

```bash
# Create wrapper.sh
cat > /tmp/wrapper.sh << 'EOF'
#!/usr/bin/env bash
exec python3 /root/.hermes/scripts/foo.py --bar
EOF
chmod +x /tmp/wrapper.sh

# Register with wrapper, not direct args
hermes cron create --script /tmp/wrapper.sh --name "foo-with-args" --schedule "0 5 * * *"
```

### Dashboard not responding

```bash
sudo systemctl restart hermes-dashboard-api
sudo journalctl -u hermes-dashboard-api -n 50
```

### Cron keeps failing

```bash
# Check what's broken
curl -s -u admin:hermes http://127.0.0.1:8645/api/health

# Try cost router probe
python3 ~/.hermes/scripts/cost_router.py probe

# Pause the cron if it's broken
hermes cron pause <id>
```

## New Client / New VPS

Use the bootstrap variants:

```bash
# New VPS (full setup)
./bootstrap.sh new-vps

# New client (workspace-only, not full VPS)
./bootstrap.sh new-client <client-name>

# Dry-run (show what would happen)
./bootstrap.sh --dry-run
```

## Uninstallation

```bash
# Stop services
sudo systemctl stop hermes-dashboard-api
sudo systemctl disable hermes-dashboard-api

# Remove files (BE CAREFUL — this deletes everything)
rm -rf ~/.hermes

# Remove systemd service
sudo rm /etc/systemd/system/hermes-dashboard-api.service
sudo systemctl daemon-reload
```

## Updating

```bash
cd ai-whisperers-ops-toolkit
git pull
./bootstrap.sh update
```

The `update` mode:
- Pulls latest scripts (overwrites local)
- Re-imports any new cron jobs (keeps your modifications)
- Restarts dashboard API
- Does NOT touch your `~/.hermes/.env` or `MEMORY.md`

## What's Auto-Installed vs Manual

| Component | Auto-installed? |
|-----------|-----------------|
| Scripts | ✓ Yes |
| Wrappers | ✓ Yes |
| Skills (3 hand-picked) | ✓ Yes |
| Skills (other 223) | On first use |
| Config templates | ✓ Yes |
| `.env` with API keys | ✗ You fill in |
| Cron jobs | ✓ Yes (74 registered) |
| Dashboard service | ✓ Yes (systemd) |
| Python deps | ✓ Yes (pip install) |

## Tested On

- Ubuntu 22.04 LTS (primary)
- Ubuntu 24.04 LTS
- Debian 12
- macOS 14+ (limited testing; systemd not native)

## See Also

- [`docs/WORKING_WITH_HERMES.md`](docs/WORKING_WITH_HERMES.md) — the canonical "how to work" guide
- [`atlas/hermes-upgrade-atlas.md`](atlas/hermes-upgrade-atlas.md) — strategic roadmap (20 items)
- [`docs/cursor-loop/`](docs/cursor-loop/) — 23 round shipping docs
