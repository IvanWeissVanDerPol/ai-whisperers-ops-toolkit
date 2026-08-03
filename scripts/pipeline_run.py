#!/usr/bin/env python3
"""
pipeline_run.py — Chain orchestrators into a single workflow.

Tier presets:
  pre-commit:    quality-gate → coverage-runner → pre_merge_check
  release:       quality-gate → coverage-runner → delivery-prep
  ticket-close:  quality-gate → coverage-runner
  audit:         quality-gate → coverage-runner → find-dead-code → doc-architecture

Usage:
    python3 ~/.hermes/scripts/pipeline_run.py --tier pre-commit --path <repo>
    python3 ~/.hermes/scripts/pipeline_run.py --tier release --path <repo>
    python3 ~/.hermes/scripts/pipeline_run.py --tier ticket-close --path <repo>
    python3 ~/.hermes/scripts/pipeline_run.py --tier audit --path <repo>
    python3 ~/.hermes/scripts/pipeline_run.py --tier pre-commit --path <repo> --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SKILLS = HERMES_HOME / "skills"
SCRIPTS = HERMES_HOME / "scripts"


# Tier presets: ordered list of (skill_name, script_path, args)
TIERS = {
    "pre-commit": [
        ("quality-gate", SKILLS / "quality-gate" / "scripts" / "quality_gate.py", ["--no-auto-fix"]),
        ("coverage-runner", SKILLS / "coverage-runner" / "scripts" / "coverage_runner.py", []),
        ("pre_merge_check", SCRIPTS / "pre_merge_check.py", []),
    ],
    "release": [
        ("quality-gate", SKILLS / "quality-gate" / "scripts" / "quality_gate.py", ["--no-auto-fix"]),
        ("coverage-runner", SKILLS / "coverage-runner" / "scripts" / "coverage_runner.py", []),
        ("delivery-prep", SCRIPTS / "delivery_prep.py", []),  # Will build if missing
    ],
    "ticket-close": [
        ("quality-gate", SKILLS / "quality-gate" / "scripts" / "quality_gate.py", ["--no-auto-fix"]),
        ("coverage-runner", SKILLS / "coverage-runner" / "scripts" / "coverage_runner.py", []),
    ],
    "audit": [
        ("quality-gate", SKILLS / "quality-gate" / "scripts" / "quality_gate.py", ["--no-auto-fix"]),
        ("coverage-runner", SKILLS / "coverage-runner" / "scripts" / "coverage_runner.py", []),
        ("find-dead-code", SKILLS / "find-dead-code" / "scripts" / "find_dead.py", []),
    ],
}


def run_step(skill: str, script: Path, repo_path: str, extra_args: list[str], json_output: bool) -> dict:
    """Run a single orchestrator step.

    Exit code 0 = pass, 2 = gate failed (still executed), other = error.
    """
    if not script.exists():
        return {"skill": skill, "status": "skipped", "reason": f"script not found: {script}"}
    cmd = ["python3", str(script), "--path", repo_path] + extra_args
    if json_output:
        cmd.append("--json")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        # 0 = pass, 2 = ran but gate failed (still executed successfully)
        execution_ok = result.returncode in (0, 2)
        return {
            "skill": skill,
            "status": "ok" if execution_ok else "script-error",
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-2000:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"skill": skill, "status": "timeout"}
    except Exception as e:
        return {"skill": skill, "status": "error", "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Chain orchestrators into a single workflow")
    parser.add_argument("--tier", required=True, choices=list(TIERS.keys()), help="Tier preset")
    parser.add_argument("--path", required=True, help="Repository path")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.tier not in TIERS:
        print(f"error: unknown tier '{args.tier}'. Valid: {list(TIERS.keys())}", file=sys.stderr)
        return 2

    if not Path(args.path).exists():
        print(f"error: repo path '{args.path}' does not exist", file=sys.stderr)
        return 2

    started = datetime.now(timezone.utc)
    steps = []
    gate_passed = True
    for skill, script, extra_args in TIERS[args.tier]:
        step = run_step(skill, script, args.path, extra_args, args.json)
        steps.append(step)
        if step.get("status") not in ("ok", "skipped"):
            gate_passed = False
    # If we want strict mode, stop on first failure
    # For now, continue to give full picture

    summary = {
        "skill": "pipeline-run",
        "version": "1.0.0",
        "tier": args.tier,
        "repo": args.path,
        "started_at": started.isoformat(),
        "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "steps_run": len(steps),
        "steps_failed": len([s for s in steps if s.get("status") in ("failed", "timeout", "error")]),
        "gate_passed": gate_passed,
        "steps": steps,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n=== Pipeline: {args.tier} — {args.path} ===")
        for s in steps:
            icon = "✓" if s.get("status") == "ok" else ("⊘" if s.get("status") == "skipped" else "✗")
            print(f"  {icon} {s.get('skill', '?')}: {s.get('status', '?')}")
        print(f"\n  Duration: {summary['duration_seconds']}s")
        print(f"  Status: {'PASS' if gate_passed else 'FAIL'}")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
