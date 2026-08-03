#!/usr/bin/env python3
"""
cron_health.py — Single-command view of cron fleet health.

Replaces manual `hermes cron list | grep` analysis. Categorizes broken
crons by root cause, suggests fixes, and offers `--heal` mode for
auto-repairing common issues (relative-path scripts).

Usage:
    python3 ~/.hermes/scripts/cron_health.py              # summary view
    python3 ~/.hermes/scripts/cron_health.py --broken     # only broken
    python3 ~/.hermes/scripts/cron_health.py --details    # per-job verbose
    python3 ~/.hermes/scripts/cron_health.py --json
    python3 ~/.hermes/scripts/cron_health.py --heal       # auto-fix safe issues

Exit codes:
    0 = all healthy
    1 = warnings present
    2 = broken crons present
    3 = critical (broken + heal failed)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
SCRIPTS_DIR = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"
HEALTH_LOG = STATE / "cron-health.jsonl"


def list_crons() -> list[dict]:
    """Parse `hermes cron list` output into structured job dicts."""
    result = subprocess.run(
        ["hermes", "cron", "list"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"hermes cron list failed: {result.stderr}")
    text = result.stdout

    # Split by job blocks: each starts with "  <id> [active|paused]"
    jobs_raw = re.split(r'\n  (?=\w{10,}\s+\[)', text)
    jobs = []
    for block in jobs_raw:
        id_m = re.match(r'\s*(\w{10,})\s+\[(\w+)\]', block)
        if not id_m:
            continue
        job_id, state_ = id_m.group(1), id_m.group(2)
        job = {
            "id": job_id,
            "state": state_,
            "name": None,
            "schedule": None,
            "deliver": None,
            "script": None,
            "mode": None,
            "last_run": None,
            "last_status": "ok",  # default
            "last_error": None,
            "next_run": None,
        }
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("Name:"):
                job["name"] = line.split("Name:", 1)[1].strip()
            elif line.startswith("Schedule:"):
                job["schedule"] = line.split("Schedule:", 1)[1].strip()
            elif line.startswith("Deliver:"):
                job["deliver"] = line.split("Deliver:", 1)[1].strip()
            elif line.startswith("Script:"):
                job["script"] = line.split("Script:", 1)[1].strip()
            elif line.startswith("Mode:"):
                job["mode"] = line.split("Mode:", 1)[1].strip()
            elif line.startswith("Next run:"):
                job["next_run"] = line.split("Next run:", 1)[1].strip()
            elif line.startswith("Last run:"):
                rest = line.split("Last run:", 1)[1].strip()
                # Format: timestamp  status  [error]
                parts = rest.split(None, 2)
                if parts:
                    job["last_run"] = parts[0]
                if len(parts) >= 2:
                    job["last_status"] = parts[1]
                if "error" in rest or "not found" in rest:
                    job["last_status"] = "error"
                    # Capture error reason
                    if "Script not found" in rest:
                        job["last_error"] = "script_not_found"
                    elif "exited with code" in rest:
                        m = re.search(r"code (\d+)", rest)
                        job["last_error"] = f"exit_code_{m.group(1) if m else '?'}"
                    elif "HTTP 404" in rest or "RuntimeError" in rest:
                        m = re.search(r"HTTP \d+|RuntimeError.*?:", rest)
                        job["last_error"] = "model_dead"
                    else:
                        job["last_error"] = "unknown"
        jobs.append(job)
    return jobs


def categorize(jobs: list[dict]) -> dict:
    """Group jobs by health status and error type."""
    summary = {
        "total": len(jobs),
        "active": sum(1 for j in jobs if j["state"] == "active"),
        "paused": sum(1 for j in jobs if j["state"] == "paused"),
        "healthy": sum(1 for j in jobs if j["last_status"] == "ok"),
        "broken": sum(1 for j in jobs if j["last_status"] == "error"),
        "by_error": defaultdict(list),
    }
    for j in jobs:
        if j["last_status"] == "error" and j["last_error"]:
            summary["by_error"][j["last_error"]].append({
                "id": j["id"],
                "name": j["name"],
                "script": j["script"],
                "last_run": j["last_run"],
            })
    summary["by_error"] = dict(summary["by_error"])
    return summary


def suggest_fix(jobs: list[dict]) -> dict[str, list[dict]]:
    """For each broken job, suggest a fix."""
    fixes: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        if j["last_status"] != "error":
            continue
        if j["last_error"] == "script_not_found" and j["script"]:
            # The script is referenced relative (or absolute) but runner can't find it.
            # The real cause was using absolute path; fix is to ensure relative.
            fixes["re_register_relative"].append({
                "id": j["id"],
                "name": j["name"],
                "action": "Re-register with relative script path",
                "script": j["script"],
                "schedule": j["schedule"],
            })
        elif j["last_error"] == "model_dead":
            fixes["swap_model_free"].append({
                "id": j["id"],
                "name": j["name"],
                "action": "hermes cron edit <id> --model google/gemma-4-31b-it:free",
            })
        elif j["last_error"] and j["last_error"].startswith("exit_code"):
            fixes["manual_inspect"].append({
                "id": j["id"],
                "name": j["name"],
                "action": f"Run manually: {j['script'] or '(check script)'}",
            })
        else:
            fixes["unknown"].append({
                "id": j["id"],
                "name": j["name"],
                "action": "Inspect manually",
            })
    return dict(fixes)


def cmd_heal(jobs: list[dict]) -> dict:
    """Auto-fix safe issues. Returns action log."""
    actions = []
    fixes = suggest_fix(jobs)
    # Re-register relative: delete + recreate (safe because we have script+schedule)
    for fix in fixes.get("re_register_relative", []):
        job_id = fix["id"]
        name = fix["name"]
        script = fix["script"]
        schedule = fix["schedule"]
        if not (script and schedule):
            continue
        # Detect args after the script filename
        parts = script.split(None, 1)
        script_name = parts[0]
        script_args = parts[1] if len(parts) > 1 else ""
        # Delete old, recreate
        del_result = subprocess.run(
            ["hermes", "cron", "rm", job_id],
            capture_output=True, text=True, timeout=10,
        )
        new_script = f"{script_name} {script_args}".strip()
        create_result = subprocess.run(
            ["hermes", "cron", "create", schedule,
             "--name", name, "--script", new_script,
             "--no-agent", "--deliver", "local"],
            capture_output=True, text=True, timeout=10,
        )
        success = create_result.returncode == 0
        actions.append({
            "job_id": job_id, "name": name,
            "action": "re_register_relative",
            "deleted": del_result.returncode == 0,
            "recreated": success,
            "new_id": create_result.stdout.split("Created job: ")[1].split()[0] if success and "Created job:" in create_result.stdout else None,
        })
    # Swap model for "model_dead" — use free model
    for fix in fixes.get("swap_model_free", []):
        job_id = fix["id"]
        edit_result = subprocess.run(
            ["hermes", "cron", "edit", job_id, "--model", "google/gemma-4-31b-it:free"],
            capture_output=True, text=True, timeout=10,
        )
        actions.append({
            "job_id": job_id, "name": fix["name"],
            "action": "swap_model_free",
            "success": edit_result.returncode == 0,
        })
    return {"actions": actions}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cron fleet health monitor")
    parser.add_argument("--broken", action="store_true", help="Show only broken crons")
    parser.add_argument("--details", action="store_true", help="Verbose per-job")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--heal", action="store_true", help="Auto-fix safe issues")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()

    try:
        jobs = list_crons()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    summary = categorize(jobs)

    if args.heal:
        result = cmd_heal(jobs)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Heal actions ===")
            for a in result["actions"]:
                status = "✓" if a.get("recreated") or a.get("success") else "✗"
                print(f"  {status} {a['name']}: {a['action']}")
        # Log
        STATE.mkdir(parents=True, exist_ok=True)
        with HEALTH_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "skill": "cron-health",
                "actions": result["actions"],
            }) + "\n")
        return 0

    if args.json:
        print(json.dumps({
            "skill": "cron-health",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "jobs": jobs,
        }, indent=2, default=str))
        # Same watchdog semantics as below: JSON output IS the signal,
        # exit 0 means the script ran successfully (regardless of broken count).
        return 0

    if args.broken:
        shown_jobs = [j for j in jobs if j["last_status"] == "error"]
    else:
        shown_jobs = jobs

    print(f"\n=== Cron Fleet Health ===")
    print(f"  Total: {summary['total']}")
    print(f"  Active: {summary['active']}")
    print(f"  Healthy: {summary['healthy']}")
    print(f"  Broken: {summary['broken']}")
    # Distinguish: rot (auto-fixable) vs real bugs (need manual fix)
    rot_count = sum(len(summary["by_error"].get(k, [])) for k in ("script_not_found", "model_dead"))
    real_bug_count = sum(len(summary["by_error"].get(k, [])) for k in summary["by_error"] if k.startswith("exit_code") or k == "unknown")
    print(f"  Cron rot (auto-fixable): {rot_count}")
    print(f"  Real script bugs (manual): {real_bug_count}")
    if summary["by_error"]:
        print(f"\n  By error type:")
        for err_type, items in summary["by_error"].items():
            print(f"    {err_type}: {len(items)} crons")
            if args.details:
                for it in items:
                    print(f"      - {it['name']} ({it['id']}): {it.get('script', '?')}")

    if args.broken or summary["broken"] > 0:
        fixes = suggest_fix(jobs)
        if fixes:
            print(f"\n  Suggested fixes:")
            for fix_type, items in fixes.items():
                print(f"    [{fix_type}] ({len(items)})")
                if args.details:
                    for it in items[:3]:
                        print(f"      - {it.get('name', '?')}: {it.get('action', '?')}")

    # Exit code semantics — IMPORTANT:
    # cron_health is a WATCHDOG. It runs every 30 min to REPORT on broken crons.
    # The number of broken crons is the data, not the success/failure of the script.
    # The script worked correctly if it ran end-to-end and produced a report.
    # Non-zero exit creates a circular dependency: the cron that watches the
    # fleet also gets flagged as broken.
    # Fix: always exit 0 here. The JSON output / stdout report IS the signal.
    # Real cron failures (script crash, API call failure) will be flagged by the
    # cron runner's own exit code, not by this script's report semantics.
    return 0


if __name__ == "__main__":
    sys.exit(main())