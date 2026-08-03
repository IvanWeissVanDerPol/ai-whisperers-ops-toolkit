#!/usr/bin/env python3
"""
anomaly_auto_pause.py — R19-3: Auto-pause crons identified by anomaly detection.

Reads trace_anomaly_detector output. If any HIGH severity anomaly is found AND
the cost spike is from a specific cron, pause that cron automatically.

Strategy:
  1. Run trace_anomaly_detector — get anomalies
  2. Use trace_skill_analytics to find the top cost driver
  3. If the top driver is a known cron AND has daily cost > $5 AND severity is high,
     pause the cron

Safety:
  - Only pauses crons that exist in the registry
  - Logs every action to /root/.hermes/state/anomaly-auto-pause.log
  - Dry-run mode shows what would be paused
  - Watchdog semantic (R16): exit 0 when script ran successfully

Usage:
  python3 anomaly_auto_pause.py              # default: threshold $5
  python3 anomaly_auto_pause.py --dry-run    # show what would happen
  python3 anomaly_auto_pause.py --threshold 10   # custom spend threshold
  python3 anomaly_auto_pause.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path("/root/.hermes/state/anomaly-auto-pause.log")


def log_action(action: str, details: dict) -> None:
    """Append an action to the log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_anomaly_detector() -> dict:
    """Run trace_anomaly_detector and return parsed JSON."""
    r = subprocess.run(
        ["python3", "/root/.hermes/scripts/trace_anomaly_detector.py", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.stdout.strip():
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {}
    return {}


def run_skill_analytics(days: int = 7) -> list[dict]:
    """Run trace_skill_analytics and return per-skill stats."""
    r = subprocess.run(
        ["python3", "/root/.hermes/scripts/trace_skill_analytics.py",
         "--days", str(days), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    if r.stdout.strip():
        try:
            d = json.loads(r.stdout)
            return d.get("by_skill", [])
        except json.JSONDecodeError:
            return []
    return []


def list_cron_jobs() -> dict:
    """Get all cron jobs as a dict {id: name}."""
    jobs_path = Path("/root/.hermes/cron/jobs.json")
    if not jobs_path.exists():
        return {}
    data = json.loads(jobs_path.read_text())
    return {j.get("id"): j.get("name") for j in data.get("jobs", [])}


def pause_cron(job_id: str, reason: str, dry_run: bool) -> dict:
    """Pause a cron job. Returns {ok, ...}."""
    if dry_run:
        return {"ok": True, "dry_run": True, "job_id": job_id, "reason": reason}
    r = subprocess.run(
        ["hermes", "cron", "pause", job_id],
        capture_output=True, text=True, timeout=15,
    )
    return {
        "ok": r.returncode == 0,
        "job_id": job_id,
        "reason": reason,
        "stdout": r.stdout.strip()[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=5.0,
                        help="Daily cost threshold to trigger pause (default $5)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # 1. Run anomaly detection
    anomalies_data = run_anomaly_detector()
    anomalies = anomalies_data.get("anomalies", [])
    high_anomalies = [a for a in anomalies if a.get("severity") == "high"]
    cost_anomalies = [a for a in anomalies if a.get("type") == "cost"]

    # 2. Find top cost drivers
    skills = run_skill_analytics(days=7)
    top_cost_drivers = sorted(
        [s for s in skills if s.get("cost_usd", 0) > 0],
        key=lambda x: x["cost_usd"],
        reverse=True,
    )

    # 3. Build a list of crons to pause
    crons_to_pause = []
    if high_anomalies and cost_anomalies:
        # High severity anomaly + cost spike → check top drivers
        for driver in top_cost_drivers[:3]:
            if driver["cost_usd"] >= args.threshold:
                skill_name = driver["skill"]
                # Only pause if it looks like a cron name (not user_session)
                if "cron" in skill_name or any(
                    k in skill_name.lower()
                    for k in ["weekly", "daily", "hourly", "monthly", "nexa", "dojo"]
                ):
                    crons_to_pause.append({
                        "skill": skill_name,
                        "cost_usd": round(driver["cost_usd"], 3),
                        "calls": driver["calls"],
                        "reason": f"high cost anomaly: ${driver['cost_usd']:.2f} over {driver['calls']} calls",
                    })

    # 4. Map skill names to cron IDs
    cron_jobs = list_cron_jobs()
    actions = []
    for cp in crons_to_pause:
        target_id = None
        cron_name = None
        # Handle "unknown_cron:XXXXXXXXXX" format from trace_skill_analytics
        if cp["skill"].startswith("unknown_cron:"):
            partial_id = cp["skill"].split(":", 1)[1]
            for jid, name in cron_jobs.items():
                if jid and jid.startswith(partial_id):
                    target_id = jid
                    cron_name = name
                    break
        else:
            # Match by cron name
            for jid, name in cron_jobs.items():
                if name and cp["skill"].lower() in name.lower():
                    target_id = jid
                    cron_name = name
                    break
        if target_id:
            reason = f"R19-3 auto-pause: {cp['reason']}"
            result = pause_cron(target_id, reason, args.dry_run)
            actions.append({
                "cron_id": target_id,
                "cron_name": cron_name,
                "skill": cp["skill"],
                **result,
            })
            log_action("pause", {
                "cron_id": target_id,
                "cron_name": cron_name,
                "skill": cp["skill"],
                "cost_usd": cp["cost_usd"],
                "dry_run": args.dry_run,
                "result": result,
            })

    result = {
        "anomaly_summary": {
            "total_anomalies": len(anomalies),
            "high_severity": len(high_anomalies),
            "cost_anomalies": len(cost_anomalies),
        },
        "threshold": args.threshold,
        "dry_run": args.dry_run,
        "crons_to_pause_found": len(crons_to_pause),
        "actions_taken": actions,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=== Anomaly Auto-Pause ===")
        print(f"  Anomalies: {len(anomalies)} total, {len(high_anomalies)} high severity")
        print(f"  Cost anomalies: {len(cost_anomalies)}")
        print(f"  Threshold: ${args.threshold:.2f}")
        print(f"  Dry-run: {args.dry_run}")
        print(f"  Crons found: {len(crons_to_pause)}")
        if actions:
            print(f"\n  Actions taken:")
            for a in actions:
                print(f"    {'(dry-run)' if a.get('dry_run') else '✓'} {a['cron_name']} ({a['cron_id'][:12]}): {a.get('reason', '')[:80]}")
        else:
            print(f"  ✓ No crons exceeded threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
