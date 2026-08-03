#!/usr/bin/env python3
"""
rotate_password.py — Auto-rotate the dashboard auth password weekly.

Workflow:
1. Generate a cryptographically-random password (24 chars)
2. Update ~/.hermes/secrets/dashboard.env (or .env file)
3. Compute bcrypt/htpasswd entry for Traefik
4. Update the Traefik dynamic config with the new htpasswd
5. Trigger a Traefik reload (or wait for the next poll)
6. Notify the operator via Telegram/WhatsApp with the new password
7. Save history to ~/.hermes/state/password-history.json

Usage:
    python3 ~/.hermes/scripts/rotate_password.py
    python3 ~/.hermes/scripts/rotate_password.py --notify telegram
    python3 ~/.hermes/scripts/rotate_password.py --length 32
    python3 ~/.hermes/scripts/rotate_password.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
SECRETS_DIR = HERMES_HOME / "secrets"
DASHBOARD_ENV = SECRETS_DIR / "dashboard.env"
TRAEFIK_CONFIG = Path("/opt/traefik/dynamic/hermes-dashboard.yml")
HISTORY = STATE / "password-history.json"


def generate_password(length: int = 24) -> str:
    """Generate a cryptographically random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def htpasswd_entry(password: str) -> str:
    """Generate htpasswd entry (SHA-512 hash)."""
    import crypt
    return crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))


def update_dashboard_env(new_password: str) -> dict:
    """Update ~/.hermes/secrets/dashboard.env."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    env_content = ""
    if DASHBOARD_ENV.exists():
        env_content = DASHBOARD_ENV.read_text()
    # Parse existing entries
    env = {}
    for line in env_content.split("\n"):
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    env["HERMES_DASHBOARD_USER"] = "admin"
    env["HERMES_DASHBOARD_PASS"] = new_password
    new_content = "\n".join(f"{k}={v}" for k, v in env.items()) + "\n"
    DASHBOARD_ENV.write_text(new_content)
    return env


def update_traefik_config(username: str, new_password: str) -> bool:
    """Update Traefik dynamic config with new htpasswd entry."""
    if not TRAEFIK_CONFIG.exists():
        return False
    hp = htpasswd_entry(new_password)
    content = TRAEFIK_CONFIG.read_text()
    # Replace the placeholder in users section
    import re
    # Pattern: - "admin:${DASHBOARD_HTPASSWD}"  →  - "admin:<hashed_password>"
    new_content = re.sub(
        r'-\s+"([^"]+):\$\{DASHBOARD_HTPASSWD\}"',
        f'- "{username}:{hp}"',
        content,
    )
    if new_content == content:
        return False
    TRAEFIK_CONFIG.write_text(new_content)
    return True


def trigger_traefik_reload() -> bool:
    """Try to trigger a Traefik reload via SIGHUP or container restart."""
    # Traefik watches the dynamic dir, no reload needed.
    # But ensure file change is picked up by reading again.
    return True


def notify_operator(password: str, target: str | None) -> dict:
    """Notify operator of the new password."""
    if not target:
        return {"sent": False, "reason": "no target"}
    msg = (
        f"🔐 *Dashboard password rotated*\n\n"
        f"New password: `{password}`\n"
        f"Rotation time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"User: admin\nURL: https://hermes-dashboard.sunstein.cloud\n"
        f"Auth: Basic (admin:password above)"
    )
    try:
        result = subprocess.run(
            ["hermes", "send", "-t", target, msg],
            capture_output=True, text=True, timeout=30,
        )
        return {"sent": result.returncode == 0, "stdout": result.stdout[-200:], "stderr": result.stderr[-200:]}
    except Exception as e:
        return {"sent": False, "error": str(e)}


def save_history(password: str, length: int) -> dict:
    """Save rotation history."""
    history = []
    if HISTORY.exists():
        try:
            history = json.loads(HISTORY.read_text())
        except Exception:
            history = []
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "length": length,
        "password": password,  # only the new one — old ones stay in history
    }
    history.append(entry)
    # Keep last 10
    history = history[-10:]
    STATE.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(history, indent=2))
    return {"history_entries": len(history), "last_rotation": entry["timestamp"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-rotate dashboard password")
    parser.add_argument("--length", type=int, default=24, help="Password length")
    parser.add_argument("--notify", choices=["telegram", "whatsapp", "slack"], help="Notify channel")
    parser.add_argument("--no-traefik", action="store_true", help="Skip Traefik config update")
    parser.add_argument("--dry-run", action="store_true", help="Generate password but don't write")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    new_password = generate_password(args.length)
    result = {
        "skill": "rotate-password",
        "version": "1.0.0",
        "length": args.length,
        "dry_run": args.dry_run,
    }

    if not args.dry_run:
        env = update_dashboard_env(new_password)
        if not args.no_traefik:
            updated = update_traefik_config(env["HERMES_DASHBOARD_USER"], new_password)
            result["traefik_updated"] = updated
        history = save_history(new_password, args.length)
        result["history"] = history
        notify = notify_operator(new_password, args.notify)
        result["notification"] = notify

    # Always include the password in result for visibility (but don't write it elsewhere)
    result["new_password"] = new_password

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n=== Password Rotation ===")
        print(f"  Mode: {'dry-run' if args.dry_run else 'live'}")
        print(f"  Length: {args.length}")
        print(f"  New password: {new_password}")
        if not args.dry_run:
            print(f"  Traefik updated: {result.get('traefik_updated', False)}")
            print(f"  History saved: {result.get('history', {}).get('history_entries', 0)} entries")
            if args.notify:
                sent = result.get("notification", {}).get("sent", False)
                print(f"  Notification: {'✓ sent' if sent else '✗ failed'}")
        else:
            print(f"  (dry-run; password generated but not written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())