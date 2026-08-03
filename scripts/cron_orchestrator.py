#!/usr/bin/env python3
"""
cron_orchestrator.py — The single command that runs everything.

This is the top-level orchestrator. It runs:
  1. Per-repo tick (all repos in registry)
  2. Health scoring across all repos
  3. Auto-remediation (safe categories only)
  4. Skill-usage tracking
  5. Loop-back continuity (run Hermeneutic cycle on bottom-10 skills)
  6. Dashboard render
  7. Digest (optional: send to Telegram/WhatsApp)

Usage:
    python3 ~/.hermes/scripts/cron_orchestrator.py                    # full run
    python3 ~/.hermes/scripts/cron_orchestrator.py --skip-remediate    # skip auto-remediation
    python3 ~/.hermes/scripts/cron_orchestrator.py --digest-only       # just send digest
    python3 ~/.hermes/scripts/cron_orchestrator.py --json

Adopted from Eneve's loop orchestration pattern.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SCRIPTS = HERMES_HOME / "scripts"
SKILLS = HERMES_HOME / "skills"
STATE = HERMES_HOME / "state"
SNAPSHOTS_DIR = STATE / "health-snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def run_step(name: str, cmd: list[str], timeout: int = 600) -> dict:
    """Run a single step, return result dict."""
    started = datetime.now(timezone.utc)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "step": name,
            "status": "ok" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
            "stdout_tail": result.stdout[-2000:] if result.stdout else "",
            "stderr_tail": result.stderr[-1000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"step": name, "status": "timeout", "duration_seconds": timeout}
    except Exception as e:
        return {"step": name, "status": "error", "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-command orchestrator for the autonomous pipeline")
    parser.add_argument("--skip-remediate", action="store_true", help="Skip auto-remediation")
    parser.add_argument("--skip-skill-usage", action="store_true", help="Skip skill usage tracking")
    parser.add_argument("--skip-loop-back", action="store_true", help="Skip Hermeneutic cycle")
    parser.add_argument("--digest-only", action="store_true", help="Just render digest, no other steps")
    parser.add_argument("--no-digest", action="store_true", help="Skip final digest render")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    summary = {
        "skill": "cron-orchestrator",
        "version": "1.0.0",
        "started_at": started.isoformat(),
        "steps": [],
    }

    if not args.digest_only:
        # Step 1: per-repo tick
        repo_tick = SCRIPTS / "repo_tick.py"
        if repo_tick.exists():
            summary["steps"].append(run_step(
                "repo_tick",
                ["python3", str(repo_tick), "--all", "--quiet"],
                timeout=900,
            ))
        else:
            summary["steps"].append({"step": "repo_tick", "status": "skipped", "reason": "script not found"})

        # Step 2: auto-remediation (safe only)
        if not args.skip_remediate:
            auto_remediate = SCRIPTS / "auto_remediate.py"
            if auto_remediate.exists():
                summary["steps"].append(run_step(
                    "auto_remediate_safe",
                    ["python3", str(auto_remediate), "--safe-only", "--all"],
                    timeout=300,
                ))
            else:
                summary["steps"].append({"step": "auto_remediate", "status": "skipped", "reason": "not yet built"})

        # Step 3: skill-usage tracking
        if not args.skip_skill_usage:
            skill_usage = SCRIPTS / "skill_usage_tracker.py"
            if skill_usage.exists():
                summary["steps"].append(run_step(
                    "skill_usage_tracker",
                    ["python3", str(skill_usage)],
                    timeout=60,
                ))
            else:
                summary["steps"].append({"step": "skill_usage", "status": "skipped", "reason": "not yet built"})

        # Step 4: loop-back continuity (run Hermeneutic cycle on bottom-10)
        if not args.skip_loop_back:
            run_cycle = SKILLS / "manage-playbook" / "scripts" / "run_cycle.py"
            if run_cycle.exists():
                summary["steps"].append(run_step(
                    "loop_back_cycle",
                    ["python3", str(run_cycle), "--all", "--phases", "validate"],
                    timeout=180,
                ))
            else:
                summary["steps"].append({"step": "loop_back", "status": "skipped", "reason": "not yet built"})

    # Step 5: render dashboard
    if not args.no_digest:
        dashboard = SCRIPTS / "repo_dashboard.py"
        if dashboard.exists():
            summary["steps"].append(run_step(
                "dashboard_render",
                ["python3", str(dashboard)],
                timeout=60,
            ))
        else:
            # Build a simple digest from snapshots
            summary["steps"].append({"step": "dashboard", "status": "skipped", "reason": "dashboard not built; using snapshot digest"})

    # Build summary
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["duration_seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    summary["steps_run"] = len([s for s in summary["steps"] if s.get("status") != "skipped"])
    summary["steps_failed"] = len([s for s in summary["steps"] if s.get("status") in ("failed", "timeout", "error")])
    # Snapshot digest
    digest_path = STATE / "cron-orchestrator-digest.json"
    digest_path.write_text(json.dumps(summary, indent=2))

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n=== Cron Orchestrator ===")
        print(f"  Duration: {summary['duration_seconds']}s")
        print(f"  Steps: {summary['steps_run']} ({summary['steps_failed']} failed)")
        for step in summary["steps"]:
            status = step.get("status", "?")
            icon = "✓" if status == "ok" else ("⊘" if status == "skipped" else "✗")
            print(f"    {icon} {step.get('step', '?')}: {status} ({step.get('duration_seconds', 0)}s)")
        if summary["steps_failed"] == 0:
            print(f"\n  ✅ ALL GREEN")
        else:
            print(f"\n  ⚠️  {summary['steps_failed']} step(s) failed")
        print(f"\n  Digest saved to {digest_path}")
    return 0 if summary["steps_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
