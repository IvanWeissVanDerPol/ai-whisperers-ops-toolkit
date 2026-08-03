#!/usr/bin/env python3
"""
self-heal.py — runs after each cron job, attempts known auto-fixes.

Pattern from r/hermesagent "Self-healing heartbeat for cronjobs" thread.

When a known error pattern is matched:
  - Apply the fix
  - Log to ~/.hermes/logs/self-heal.log
  - Continue (don't alert)

When an unknown error is found:
  - Write a clear alert to ~/.hermes/logs/self-heal-alerts.log
  - Non-zero exit (so cron delivery fails loudly)
"""
import os
import sys
import json
import datetime
import subprocess

HERMES_HOME = os.path.expanduser("~/.hermes")
CRON_FILE = os.path.join(HERMES_HOME, "cron/jobs.json")
LOG_DIR = os.path.join(HERMES_HOME, "logs")
HEAL_LOG = os.path.join(LOG_DIR, "self-heal.log")
ALERT_LOG = os.path.join(LOG_DIR, "self-heal-alerts.log")


def log(level, msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.datetime.now().isoformat()
    with open(HEAL_LOG, "a") as f:
        f.write(f"{ts} [{level}] {msg}\n")


def alert(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.datetime.now().isoformat()
    with open(ALERT_LOG, "a") as f:
        f.write(f"{ts} [ALERT] {msg}\n")
    print(f"ALERT: {msg}")


# Known auto-fixes (idempotent)
AUTO_FIXES = [
    {
        "id": "log_disk_full",
        "match": lambda j: "disk" in (j.get("last_delivery_error") or "").lower(),
        "fix": lambda: subprocess.run(
            ["python3", os.path.join(HERMES_HOME, "scripts/cleanup-logs.py")],
            capture_output=True
        ),
        "description": "Log disk full → run cleanup-logs.py"
    },
    {
        "id": "model_unavailable",
        "match": lambda j: "model" in (j.get("last_delivery_error") or "").lower()
                          and "not found" in (j.get("last_delivery_error") or "").lower(),
        "fix": lambda: subprocess.run(
            ["hermes", "auth", "reset"],
            capture_output=True
        ),
        "description": "Model not found → reset auth credentials"
    },
    {
        "id": "config_invalid",
        "match": lambda j: "config" in (j.get("last_delivery_error") or "").lower(),
        "fix": lambda: subprocess.run(
            ["cp", os.path.join(HERMES_HOME, "config.yaml.backup"),
             os.path.join(HERMES_HOME, "config.yaml")],
            capture_output=True
        ),
        "description": "Config invalid → restore from backup"
    },
    {
        "id": "network_timeout",
        "match": lambda j: "timeout" in (j.get("last_delivery_error") or "").lower()
                          or "connection refused" in (j.get("last_delivery_error") or "").lower(),
        "fix": None,  # Network issues need human attention
        "description": "Network timeout → needs human check"
    },
]


def check_and_heal():
    if not os.path.exists(CRON_FILE):
        log("WARN", "cron/jobs.json not found")
        return 0

    with open(CRON_FILE) as f:
        data = json.load(f)

    fixed = 0
    alerted = 0

    for job in data.get("jobs", []):
        if job.get("last_status") != "error":
            continue

        # Check if error was already addressed (last_run_at older than 1 day)
        last_run = job.get("last_run_at")
        if last_run:
            try:
                last_dt = datetime.datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                age = (datetime.datetime.now(last_dt.tzinfo) - last_dt).total_seconds()
                if age > 86400:
                    continue  # Stale error, skip
            except (ValueError, TypeError):
                pass

        err = job.get("last_delivery_error", "")
        matched = False

        for fix_def in AUTO_FIXES:
            try:
                if fix_def["match"](job):
                    matched = True
                    if fix_def["fix"]:
                        log("INFO", f"Applying auto-fix '{fix_def['id']}' to job {job['name']}")
                        fix_def["fix"]()
                        fixed += 1
                    else:
                        alert(f"Job {job['name']}: pattern '{fix_def['id']}' detected. "
                              f"Manual check needed. Error: {err[:200]}")
                        alerted += 1
                    break
            except Exception as e:
                log("ERROR", f"Auto-fix {fix_def['id']} failed: {str(e)[:100]}")

        if not matched and err:
            # Unknown error pattern — alert
            alert(f"Job {job['name']}: unknown error pattern. Error: {err[:200]}")
            alerted += 1

    log("INFO", f"self-heal run complete: {fixed} fixes, {alerted} alerts")
    return 0 if alerted == 0 else 1


if __name__ == "__main__":
    sys.exit(check_and_heal())
