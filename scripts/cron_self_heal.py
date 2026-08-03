#!/usr/bin/env python3
"""
cron_self_heal.py — Auto-repair cron rot at safe hours.

Wraps cron_health.py --heal logic with safety rails:
  - Only runs between 04:00 and 06:00 UTC (low-traffic window)
  - Only auto-fixes safe categories (re_register_relative, swap_model_free)
  - Sends Telegram notification when healing happens
  - Logs every action to cron-heal-log.jsonl
  - Refuses to run if more than 5 actions in last hour (panic-stop)

Usage:
    python3 ~/.hermes/scripts/cron_self_heal.py            # auto-fix safe issues
    python3 ~/.hermes/scripts/cron_self_heal.py --dry-run  # preview actions
    python3 ~/.hermes/scripts/cron_self_heal.py --json
    python3 ~/.hermes/scripts/cron_self_heal.py --force    # ignore time window
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
SCRIPTS = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"
HEAL_LOG = STATE / "cron-heal-log.jsonl"

# Safe action types — auto-fix these
SAFE_ACTIONS = ("re_register_relative", "swap_model_free")

# Window: 04:00-06:00 UTC, only run healing in low-traffic period
HEAL_WINDOW_START_HOUR_UTC = 4
HEAL_WINDOW_END_HOUR_UTC = 6
MAX_ACTIONS_PER_HOUR = 5


def read_log() -> list[dict]:
    """Read heal history."""
    if not HEAL_LOG.exists():
        return []
    out = []
    for line in HEAL_LOG.read_text().split("\n"):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def get_recent_action_count(window_minutes: int = 60) -> int:
    """Count actions in last N minutes."""
    log = read_log()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    count = 0
    for entry in log:
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts >= cutoff:
            count += len(entry.get("actions", []))
    return count


def list_crons() -> list[dict]:
    """Re-use cron_health list logic but inline (to avoid subprocess coupling)."""
    result = subprocess.run(
        ["hermes", "cron", "list"],
        capture_output=True, text=True, timeout=30,
    )
    text = result.stdout
    jobs_raw = re.split(r'\n  (?=\w{10,}\s+\[)', text)
    jobs = []
    for block in jobs_raw:
        id_m = re.match(r'\s*(\w{10,})\s+\[(\w+)\]', block)
        if not id_m:
            continue
        job = {
            "id": id_m.group(1),
            "state": id_m.group(2),
            "name": None,
            "schedule": None,
            "script": None,
            "last_status": "ok",
            "last_error": None,
        }
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("Name:"):
                job["name"] = line.split("Name:", 1)[1].strip()
            elif line.startswith("Schedule:"):
                job["schedule"] = line.split("Schedule:", 1)[1].strip()
            elif line.startswith("Script:"):
                job["script"] = line.split("Script:", 1)[1].strip()
            elif line.startswith("Last run:") and ("error" in line.lower() or "not found" in line.lower()):
                job["last_status"] = "error"
                if "Script not found" in line:
                    job["last_error"] = "script_not_found"
                elif "HTTP 404" in line or "RuntimeError" in line:
                    job["last_error"] = "model_dead"
                elif "exit_code" in line:
                    job["last_error"] = "exit_code"
        jobs.append(job)
    return jobs


def plan_fixes(jobs: list[dict]) -> list[dict]:
    """Generate a list of planned fix actions."""
    actions = []
    for j in jobs:
        if j["last_status"] != "error":
            continue
        if j["last_error"] == "script_not_found" and j["script"] and j["schedule"]:
            parts = j["script"].split(None, 1)
            actions.append({
                "type": "re_register_relative",
                "job_id": j["id"],
                "name": j["name"],
                "schedule": j["schedule"],
                "script_name": parts[0],
                "script_args": parts[1] if len(parts) > 1 else "",
            })
        elif j["last_error"] == "model_dead":
            actions.append({
                "type": "swap_model_free",
                "job_id": j["id"],
                "name": j["name"],
            })
    return actions


def execute_action(action: dict) -> dict:
    """Run a single fix action and return result."""
    if action["type"] == "re_register_relative":
        new_script = f"{action['script_name']} {action['script_args']}".strip()
        del_r = subprocess.run(
            ["hermes", "cron", "rm", action["job_id"]],
            capture_output=True, text=True, timeout=10,
        )
        cr = subprocess.run(
            ["hermes", "cron", "create", action["schedule"],
             "--name", action["name"], "--script", new_script,
             "--no-agent", "--deliver", "local"],
            capture_output=True, text=True, timeout=10,
        )
        success = cr.returncode == 0
        new_id = None
        if success and "Created job:" in cr.stdout:
            m = re.search(r"Created job:\s+(\w+)", cr.stdout)
            new_id = m.group(1) if m else None
        return {
            **action, "deleted": del_r.returncode == 0,
            "recreated": success, "new_id": new_id,
        }
    if action["type"] == "swap_model_free":
        # R18: Use cost_router to find a working model instead of guessing.
        # The old hardcoded google/gemma-4-31b-it:free is itself 404.
        try:
            rec_r = subprocess.run(
                ["python3", "/root/.hermes/scripts/cost_router.py", "recommend"],
                capture_output=True, text=True, timeout=30,
            )
            rec = json.loads(rec_r.stdout) if rec_r.stdout.strip() else {}
        except Exception as e:
            rec = {}
        if not rec.get("provider") or not rec.get("model"):
            return {**action, "success": False, "error": "cost_router failed"}
        # Edit the cron with the recommended provider/model
        er = subprocess.run(
            ["hermes", "cron", "edit", action["job_id"],
             "--provider", rec["provider"],
             "--model", rec["model"]],
            capture_output=True, text=True, timeout=10,
        )
        return {**action, "success": er.returncode == 0,
                "new_provider": rec["provider"], "new_model": rec["model"]}
    return {**action, "success": False}


def send_telegram(text: str) -> bool:
    """Send to Telegram home channel."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        env_path = HERMES_HOME / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    if not token:
        return False
    # Get home channel
    cfg = (HERMES_HOME / "config.yaml").read_text()
    m = re.search(
        r"^telegram:\s*\n(?:\s+.+\n)*?\s+home_channel:\s*['\"]?([^\s'\"]+)",
        cfg, re.MULTILINE,
    )
    chat_id = m.group(1).strip("'\"") if m else os.environ.get("TELEGRAM_HOME_CHANNEL")
    if not chat_id:
        return False
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-heal cron rot at safe hours")
    parser.add_argument("--dry-run", action="store_true", help="Plan but don't execute")
    parser.add_argument("--force", action="store_true", help="Ignore time window")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    in_window = HEAL_WINDOW_START_HOUR_UTC <= now.hour < HEAL_WINDOW_END_HOUR_UTC
    if not (in_window or args.force):
        if not args.json:
            print(f"\n=== Cron Self-Heal ===")
            print(f"  Current time: {now.strftime('%H:%M UTC')}")
            print(f"  Window: {HEAL_WINDOW_START_HOUR_UTC:02d}:00-{HEAL_WINDOW_END_HOUR_UTC:02d}:00 UTC")
            print(f"  Outside heal window. Use --force to override.")
        return 0

    recent = get_recent_action_count(60)
    if recent >= MAX_ACTIONS_PER_HOUR:
        if not args.json:
            print(f"\n=== Cron Self-Heal: PANIC-STOP ===")
            print(f"  Recent actions: {recent}/{MAX_ACTIONS_PER_HOUR} in last hour")
            print(f"  Refusing to heal to prevent thrashing")
            send_telegram(f"🚨 *Cron Self-Heal Panic-Stop*\n\n{recent} actions in last hour. Refusing to heal.")
        return 1

    jobs = list_crons()
    planned = plan_fixes(jobs)

    if args.dry_run:
        if args.json:
            print(json.dumps({
                "skill": "cron-self-heal",
                "version": "1.0.0",
                "timestamp": now.isoformat(),
                "window_ok": True,
                "recent_actions": recent,
                "planned_actions": planned,
            }, indent=2))
        else:
            print(f"\n=== Cron Self-Heal (DRY-RUN) ===")
            print(f"  Window: OK ({now.strftime('%H:%M UTC')})")
            print(f"  Recent actions: {recent}")
            print(f"  Planned actions: {len(planned)}")
            for p in planned:
                print(f"    [{p['type']}] {p['name']}")
        return 0

    executed = []
    for action in planned:
        if action["type"] not in SAFE_ACTIONS:
            continue
        result = execute_action(action)
        executed.append(result)

    # Log
    STATE.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": now.isoformat(),
        "skill": "cron-self-heal",
        "actions": executed,
    }
    with HEAL_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    # Notify if anything happened
    if executed:
        msg = f"🛠️ *Cron Self-Heal*\n\n"
        for e in executed:
            ok = e.get("recreated") or e.get("success")
            icon = "✓" if ok else "✗"
            msg += f"{icon} `{e['name']}` → {e['type']}\n"
        send_telegram(msg)

    if args.json:
        print(json.dumps({
            "skill": "cron-self-heal",
            "version": "1.0.0",
            "timestamp": now.isoformat(),
            "executed_actions": executed,
        }, indent=2, default=str))
    else:
        print(f"\n=== Cron Self-Heal ===")
        print(f"  Executed: {len(executed)} actions")
        for e in executed:
            ok = e.get("recreated") or e.get("success")
            icon = "✓" if ok else "✗"
            print(f"    {icon} {e['name']} ({e['type']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())