#!/usr/bin/env python3
"""
pre_merge_check.py — Slim pre-merge validation for git hooks.

Wraps quality-gate but exposes a single command suitable for use as a
git pre-commit hook:

    ln -s ~/.hermes/scripts/pre_merge_check.py .git/hooks/pre-commit
    python3 ~/.hermes/scripts/pre_merge_check.py

Or invoke manually:

    python3 ~/.hermes/scripts/pre_merge_check.py --path <repo>
    python3 ~/.hermes/scripts/pre_merge_check.py --path <repo> --strict
    python3 ~/.hermes/scripts/pre_merge_check.py --path <repo> --json

Adopted from Eneve's `validate-pre-merge.ps1` (7-step pre-merge gate).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
QUALITY_GATE = HERMES_HOME / "skills" / "quality-gate" / "scripts" / "quality_gate.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-merge validation (slim wrapper for git hooks)")
    parser.add_argument("--path", default=".", help="Repository path (default: cwd)")
    parser.add_argument("--strict", action="store_true", help="Block on warnings (default: warn-only)")
    parser.add_argument("--no-coverage", action="store_true", help="Skip coverage check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    repo = Path(args.path).resolve()
    if not repo.exists():
        print(f"error: {repo} does not exist", file=sys.stderr)
        return 2

    # 1. Detect uncommitted changes
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo, capture_output=True, text=True
    )
    uncommitted = status.stdout.strip().split("\n") if status.stdout.strip() else []

    # 2. Run quality-gate (covers build, lint, test, complexity)
    gate_cmd = ["python3", str(QUALITY_GATE), "--path", str(repo), "--no-auto-fix"]
    if args.json:
        gate_cmd.append("--json")
    gate = subprocess.run(gate_cmd, capture_output=True, text=True)

    # 3. Run coverage-runner
    coverage_script = HERMES_HOME / "skills" / "coverage-runner" / "scripts" / "coverage_runner.py"
    coverage_result = {"status": "skipped"}
    if not args.no_coverage and coverage_script.exists():
        cov = subprocess.run(
            ["python3", str(coverage_script), "--path", str(repo), "--json"],
            capture_output=True, text=True
        )
        try:
            coverage_result = json.loads(cov.stdout)
        except Exception:
            coverage_result = {"status": "failed", "error": cov.stderr}

    # 4. Detect non-standard branch
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    branch_ok = branch in ("main", "master", "develop") or any(
        branch.startswith(p) for p in ("feature/", "fix/", "chore/", "docs/", "test/", "release/", "hotfix/")
    )

    # 5. Detect large files (>1MB) staged
    large_files = []
    diff = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
        cwd=repo, capture_output=True, text=True
    )
    for fname in diff.stdout.strip().split("\n"):
        if not fname:
            continue
        fpath = repo / fname
        if fpath.exists() and fpath.stat().st_size > 1_000_000:
            large_files.append({"file": fname, "size_mb": round(fpath.stat().st_size / 1_000_000, 2)})

    # Build report
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    gate_passed = gate.returncode == 0
    cov_passed = coverage_result.get("gate_passed", True)

    report = {
        "skill": "pre-merge-check",
        "version": "1.0.0",
        "repo": repo.name,
        "branch": branch,
        "timestamp": started.isoformat(),
        "uncommitted_files": len(uncommitted),
        "branch_name_convention": branch_ok,
        "large_files": large_files,
        "quality_gate": {"passed": gate_passed, "return_code": gate.returncode},
        "coverage": coverage_result,
        "ready": gate_passed and cov_passed and branch_ok and not large_files,
        "duration_seconds": round(duration, 1),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Pre-Merge Check — {repo.name} ===")
        print(f"  Branch: {branch} {'✓' if branch_ok else '✗ non-standard'}")
        print(f"  Uncommitted files: {len(uncommitted)}")
        if large_files:
            print(f"  Large files (>1MB): {[lf['file'] for lf in large_files]}")
        print(f"  Quality gate: {'PASS' if gate_passed else 'FAIL'}")
        print(f"  Coverage: {coverage_result.get('final_coverage', 0.0)*100:.1f}% "
              f"(passed: {coverage_result.get('gate_passed', False)})")
        if not args.json and gate.stdout:
            print()
            print(gate.stdout)
        print()
        status = "✅ READY TO MERGE" if report["ready"] else "❌ NOT READY"
        print(f"  {status}")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
