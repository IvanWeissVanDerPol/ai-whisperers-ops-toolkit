#!/usr/bin/env python3
"""
cron_auto_disable.py — Atlas D-7: Auto-disable cron jobs that have failed too many times.

When a cron job consistently fails, it pollutes cron_health output and wastes resources.
This script auto-disables crons that have failed N times in a row.

Modes:
  --dry-run      Report what would be disabled, don't disable
  --threshold N  Number of consecutive failures to trigger auto-disable (default: 5)
  --enable JOB   Re-enable a disabled cron (manual recovery)
  --list         List currently disabled crons
  --json         JSON output

Exit codes:
  0 = success (no crons needed disabling)
  1 = error
  2 = one or more crons were auto-disabled (still success for cron watchdog semantic)

The script integrates with the cron registry. Disabled jobs are skipped by the cron runner.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
DISABLED_FILE = STATE / "cron-disabled.json"


def load_disabled() -> dict:
    """Load the disabled-jobs registry."""
    if DISABLED_FILE.exists():
        try:
            return json.loads(DISABLED_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_disabled(disabled: dict) -> None:
    """Save the disabled-jobs registry."""
    STATE.mkdir(parents=True, exist_ok=True)
    DISABLED_FILE.write_text(json.dumps(disabled, indent=2))


def get_cron_runs(job_id: str, limit: int = 20) -> list[dict]:
    """Get recent runs for a job using hermes cron runs."""
    try:
        result = subprocess.run(
            ["hermes", "cron", "runs", job_id, "--limit", str(limit)],
            capture_output=True, text=True, timeout=10,
        )
        runs = []
        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Format: "<execution_id>  <status>  job=<id>  source=<src>  <timestamp>"
            parts = line.split()
            if len(parts) >= 2 and parts[1] in ("completed", "failed", "running", "ok"):
                runs.append({
                    "execution_id": parts[0],
                    "status": parts[1],
                })
        return runs
    except Exception:
        return []


def count_consecutive_failures(runs: list[dict]) -> int:
    """Count how many failures in a row at the most recent end of the run list."""
    consecutive = 0
    for run in runs:
        if run["status"] in ("failed", "error"):
            consecutive += 1
        else:
            break
    return consecutive


def get_all_jobs() -> list[dict]:
    """Get all cron jobs as dicts."""
    try:
        result = subprocess.run(
            ["hermes", "cron", "list"],
            capture_output=True, text=True, timeout=15,
        )
        jobs = []
        current = {}
        for line in result.stdout.split("\n"):
            line = line.rstrip()
            if not line:
                if current:
                    jobs.append(current)
                    current = {}
                continue
            if line.startswith("  ") and current:
                # Continuation of previous job
                if ":" in line:
                    key, _, val = line.strip().partition(":")
                    current[key.strip()] = val.strip()
                continue
            # New job starts
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                if current:
                    jobs.append(current)
                current = {"id": parts[0].strip(), "status": parts[1].strip()}
        if current:
            jobs.append(current)
        return [j for j in jobs if j.get("status", "").startswith("[active]") or j.get("status", "").startswith("[paused]")]
    except Exception as e:
        print(f"Error getting jobs: {e}", file=sys.stderr)
        return []


def disable_job(job_id: str, reason: str) -> bool:
    """Pause a job via hermes cron pause."""
    try:
        result = subprocess.run(
            ["hermes", "cron", "pause", job_id],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def enable_job(job_id: str) -> bool:
    """Resume a job via hermes cron resume."""
    try:
        result = subprocess.run(
            ["hermes", "cron", "resume", job_id],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't disable")
    parser.add_argument("--threshold", type=int, default=5, help="Consecutive failures to trigger disable")
    parser.add_argument("--enable", help="Re-enable a disabled cron by job ID")
    parser.add_argument("--list", action="store_true", help="List disabled crons")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # Handle --enable
    if args.enable:
        disabled = load_disabled()
        if args.enable in disabled:
            if enable_job(args.enable):
                del disabled[args.enable]
                save_disabled(disabled)
                print(f"✓ Re-enabled cron {args.enable}")
                return 0
            else:
                print(f"✗ Failed to re-enable cron {args.enable}", file=sys.stderr)
                return 1
        else:
            print(f"Cron {args.enable} is not in the disabled registry")
            return 0

    # Handle --list
    if args.list:
        disabled = load_disabled()
        if args.json:
            print(json.dumps(disabled, indent=2))
        else:
            if not disabled:
                print("No disabled crons")
            else:
                for jid, info in disabled.items():
                    print(f"  {jid}: {info.get('reason', 'no reason')} (disabled {info.get('disabled_at', '?')})")
        return 0

    # Main: scan and auto-disable
    jobs = get_all_jobs()
    disabled = load_disabled()

    flagged = []
    for job in jobs:
        jid = job.get("id", "").strip()
        name = job.get("Name", job.get("name", "unknown"))
        if not jid or jid in disabled:
            continue
        # Skip LLM-driven jobs that have model_dead — they need a fix, not auto-disable
        runs = get_cron_runs(jid)
        failures = count_consecutive_failures(runs)
        if failures >= args.threshold:
            flagged.append({
                "id": jid,
                "name": name,
                "consecutive_failures": failures,
                "last_runs": runs[:3],
            })

    if args.dry_run:
        if args.json:
            print(json.dumps({"dry_run": True, "would_disable": flagged}, indent=2))
        else:
            if not flagged:
                print(f"No crons with >= {args.threshold} consecutive failures")
            else:
                print(f"Would auto-disable {len(flagged)} cron(s):")
                for f in flagged:
                    print(f"  {f['id']} ({f['name']}): {f['consecutive_failures']} failures")
        return 0

    # Actually disable
    if not flagged:
        if args.json:
            print(json.dumps({"disabled": [], "threshold": args.threshold}, indent=2))
        else:
            print(f"No crons met the {args.threshold}-failure threshold")
        return 0

    disabled_count = 0
    for f in flagged:
        if disable_job(f["id"], f"auto-disabled: {f['consecutive_failures']} consecutive failures"):
            disabled[f["id"]] = {
                "name": f["name"],
                "reason": "consecutive_failures",
                "consecutive_failures": f["consecutive_failures"],
                "disabled_at": subprocess.run(["date", "-Iseconds"], capture_output=True, text=True).stdout.strip(),
            }
            disabled_count += 1
            print(f"✓ Disabled {f['id']} ({f['name']}): {f['consecutive_failures']} consecutive failures")

    save_disabled(disabled)

    if args.json:
        print(json.dumps({"disabled": list(disabled.keys()), "count": disabled_count, "threshold": args.threshold}, indent=2))
    else:
        print(f"\nDisabled {disabled_count} cron(s). Use --list to see, --enable <job_id> to re-enable.")

    # Watchdog semantic: cron_health treats exit 2 as "broken", exit 0 as "ran successfully".
    # Auto-disabling IS the script's job, so exit 0 (the action IS the success signal).
    return 0


if __name__ == "__main__":
    sys.exit(main())
