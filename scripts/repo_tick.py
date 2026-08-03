#!/usr/bin/env python3
"""
repo_tick.py — Per-repo autonomous heartbeat.

Runs the quality-gate + coverage-runner + health check on every project
in the registry (or a single project). Writes a snapshot to
~/.hermes/state/health-snapshots/<repo>.json. Detects regressions vs
last snapshot.

Usage:
    python3 ~/.hermes/scripts/repo_tick.py --all
    python3 ~/.hermes/scripts/repo_tick.py --repo psycology
    python3 ~/.hermes/scripts/repo_tick.py --repo psycology --json
    python3 ~/.hermes/scripts/repo_tick.py --all --quiet   # only print regressions

Adopted from Eneve's validate-pre-merge.ps1 + cron orchestration pattern.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"
SCRIPTS_DIR = HERMES_HOME / "scripts"
PROJECTS_YAML = HERMES_HOME / "state" / "projects.yaml"
SNAPSHOTS_DIR = HERMES_HOME / "state" / "health-snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_projects() -> list[dict]:
    """Load projects from the registry."""
    if not PROJECTS_YAML.exists():
        return []
    data = yaml.safe_load(PROJECTS_YAML.read_text())
    return data.get("projects", [])


def run_quality_gate(repo_path: Path) -> dict:
    """Run quality-gate on a repo."""
    qg = SKILLS_DIR / "quality-gate" / "scripts" / "quality_gate.py"
    if not qg.exists():
        return {"status": "skipped", "reason": "quality-gate not installed"}
    try:
        result = subprocess.run(
            ["python3", str(qg), "--path", str(repo_path), "--no-auto-fix", "--json"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"status": "failed", "stdout": result.stdout[-1000:], "stderr": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_coverage_runner(repo_path: Path) -> dict:
    """Run coverage-runner on a repo."""
    cr = SKILLS_DIR / "coverage-runner" / "scripts" / "coverage_runner.py"
    if not cr.exists():
        return {"status": "skipped", "reason": "coverage-runner not installed"}
    try:
        result = subprocess.run(
            ["python3", str(cr), "--path", str(repo_path), "--json"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"status": "failed", "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_find_dead(repo_path: Path) -> dict:
    """Run find-dead-code on a repo's skills (only if repo has .hermes)."""
    if not (repo_path / ".hermes").exists():
        return {"status": "skipped", "reason": "no .hermes in repo"}
    fd = SKILLS_DIR / "find-dead-code" / "scripts" / "find_dead.py"
    if not fd.exists():
        return {"status": "skipped"}
    try:
        result = subprocess.run(
            ["python3", str(fd), "--json"],
            cwd=repo_path, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "status": "ok",
                "dead_skills": len(data.get("dead_skills", [])),
                "dead_scripts": len(data.get("dead_scripts", [])),
                "dangling": len(data.get("dangling_references", [])),
            }
        return {"status": "failed"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_git_status(repo_path: Path) -> dict:
    """Get git status (branch, uncommitted, behind/ahead)."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        uncommitted = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        ).stdout.strip().split("\n") if subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True, timeout=10
        ).stdout.strip() else []
        # Days since last commit
        last_commit_date = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        days_since_commit = None
        if last_commit_date.isdigit():
            import time
            days_since_commit = round((time.time() - int(last_commit_date)) / 86400, 1)
        return {
            "branch": branch,
            "uncommitted_files": len(uncommitted),
            "days_since_commit": days_since_commit,
        }
    except Exception as e:
        return {"branch": "error", "error": str(e)}


def compute_health_score(snapshot: dict) -> int:
    """Compute a unified health score 0-100.

    Weights:
      - coverage: 30%
      - complexity (if available): 20%
      - findings count inverse: 20%
      - branch age (no recent commits): 15%
      - test pass rate: 15%
    """
    score = 0.0
    # Coverage (30%)
    cov_data = snapshot.get("coverage", {})
    if isinstance(cov_data, dict) and "final_coverage" in cov_data:
        coverage = cov_data["final_coverage"]
        score += min(coverage, 1.0) * 30
    elif isinstance(cov_data, dict) and cov_data.get("status") == "ok":
        # Some coverage outputs use different field
        coverage = cov_data.get("coverage", 0)
        score += min(coverage, 1.0) * 30
    # Findings inverse (20%) — fewer findings = higher score
    new_findings = snapshot.get("new_findings", 0)
    if new_findings == 0:
        score += 20
    elif new_findings <= 5:
        score += 15
    elif new_findings <= 20:
        score += 10
    else:
        score += 5
    # Branch age (15%) — recent commits = higher score
    days = snapshot.get("git_status", {}).get("days_since_commit")
    if days is None:
        score += 5
    elif days < 7:
        score += 15
    elif days < 30:
        score += 10
    elif days < 90:
        score += 5
    # Quality gate pass (15%)
    qg = snapshot.get("quality_gate", {})
    if isinstance(qg, dict) and qg.get("gate_passed"):
        score += 15
    # Uncommitted files (10%)
    uncommitted = snapshot.get("git_status", {}).get("uncommitted_files", 0)
    if uncommitted == 0:
        score += 10
    elif uncommitted <= 5:
        score += 5
    # Coverage gate pass (10%)
    if isinstance(cov_data, dict) and cov_data.get("gate_passed"):
        score += 10
    return min(int(score), 100)


def tick_repo(project: dict, quiet: bool = False) -> dict:
    """Run all checks on one repo."""
    repo_path = Path(project["path"])
    if not repo_path.exists():
        return {"repo": project["name"], "status": "error", "error": "path missing"}
    started = datetime.now(timezone.utc)
    snapshot = {
        "repo": project["name"],
        "type": project.get("type", "unknown"),
        "timestamp": started.isoformat(),
        "path": str(repo_path),
        "default_branch": project.get("default_branch", "main"),
        "current_branch": None,
        "orchestrators": project.get("orchestrators", []),
        "git_status": run_git_status(repo_path),
        "quality_gate": run_quality_gate(repo_path),
        "coverage": run_coverage_runner(repo_path),
        "find_dead": run_find_dead(repo_path),
        "new_findings": 0,
    }
    snapshot["current_branch"] = snapshot["git_status"].get("branch", "unknown")
    # Coverage gate pass
    cov_data = snapshot.get("coverage", {})
    if isinstance(cov_data, dict):
        cov_data["gate_passed"] = cov_data.get("gate_passed", False)
    # Quality gate pass
    qg_data = snapshot.get("quality_gate", {})
    if isinstance(qg_data, dict):
        qg_data["gate_passed"] = qg_data.get("gate_passed", False)
    # Health score
    snapshot["health_score"] = compute_health_score(snapshot)
    snapshot["duration_seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    # Write snapshot
    snapshot_path = SNAPSHOTS_DIR / f"{project['name']}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2))
    return snapshot


def detect_regression(current: dict, previous: dict) -> list[str]:
    """Detect regressions between two snapshots."""
    regressions = []
    if not previous:
        return []
    # Health score dropped
    prev_score = previous.get("health_score", 0)
    curr_score = current.get("health_score", 0)
    if curr_score < prev_score - 5:
        regressions.append(f"Health score: {prev_score} → {curr_score} (regression)")
    # Coverage dropped
    prev_cov = previous.get("coverage", {}).get("final_coverage", 0)
    curr_cov = current.get("coverage", {}).get("final_coverage", 0)
    if isinstance(prev_cov, (int, float)) and isinstance(curr_cov, (int, float)):
        if curr_cov < prev_cov - 0.05:
            regressions.append(f"Coverage: {prev_cov*100:.1f}% → {curr_cov*100:.1f}% (regression)")
    # Quality gate flipped
    prev_qg = previous.get("quality_gate", {}).get("gate_passed", True)
    curr_qg = current.get("quality_gate", {}).get("gate_passed", True)
    if prev_qg and not curr_qg:
        regressions.append("Quality gate: PASS → FAIL (regression)")
    # New findings
    prev_findings = previous.get("new_findings", 0)
    curr_findings = current.get("new_findings", 0)
    if curr_findings > prev_findings + 5:
        regressions.append(f"Findings: {prev_findings} → {curr_findings} (regression)")
    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-repo autonomous heartbeat")
    parser.add_argument("--repo", help="Single repo name")
    parser.add_argument("--all", action="store_true", help="All repos in registry")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quiet", action="store_true", help="Only print regressions")
    parser.add_argument("--days-stale", type=int, default=30, help="Flag repos with no recent commits")
    parser.add_argument("--parallel", type=int, default=4, help="Number of parallel workers")
    args = parser.parse_args()

    if not args.repo and not args.all:
        parser.error("provide --repo or --all")

    projects = load_projects()
    if not projects:
        print("error: no projects in registry (run build_projects_yaml first)", file=sys.stderr)
        return 2

    if args.repo:
        projects = [p for p in projects if p["name"] == args.repo]
        if not projects:
            print(f"error: repo '{args.repo}' not found in registry", file=sys.stderr)
            return 2

    results = []
    regressions_found = []

    if args.parallel > 1 and len(projects) > 1:
        # Parallel execution
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            future_to_project = {executor.submit(tick_repo, p, args.quiet): p for p in projects}
            for future in as_completed(future_to_project):
                project = future_to_project[future]
                try:
                    snapshot = future.result()
                except Exception as e:
                    snapshot = {"repo": project["name"], "status": "error", "error": str(e), "health_score": 0}
                results.append(snapshot)
                if not args.quiet and not args.json:
                    score = snapshot.get("health_score", 0)
                    branch = snapshot.get("current_branch", "?")
                    status = "✓" if score >= 70 else "✗"
                    days = snapshot.get("git_status", {}).get("days_since_commit", "?")
                    print(f"  {status} {project['name']:<35} score={score:>3} branch={branch:<12} last_commit={days}d")
    else:
        # Sequential
        for project in projects:
            snapshot = tick_repo(project, quiet=args.quiet)
            results.append(snapshot)
            if not args.quiet and not args.json:
                score = snapshot.get("health_score", 0)
                branch = snapshot.get("current_branch", "?")
                status = "✓" if score >= 70 else "✗"
                days = snapshot.get("git_status", {}).get("days_since_commit", "?")
                print(f"  {status} {project['name']:<35} score={score:>3} branch={branch:<12} last_commit={days}d")

    # Detect regressions
    for snapshot in results:
        snapshot_path = SNAPSHOTS_DIR / f"{snapshot['repo']}.json"
        previous = None
        if snapshot_path.exists():
            try:
                previous = json.loads(snapshot_path.read_text())
            except Exception:
                pass
        reg = detect_regression(snapshot, previous) if previous else []
        if reg:
            regressions_found.append({"repo": snapshot["repo"], "regressions": reg})

    # Render
    if args.json:
        print(json.dumps({
            "skill": "repo-tick",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repos_ticked": len(results),
            "regressions": regressions_found,
            "snapshots": results,
        }, indent=2))
    else:
        print(f"\n=== Repo tick: {len(results)} repos ticked ===")
        if regressions_found:
            print(f"\n  REGRESSIONS ({len(regressions_found)}):")
            for r in regressions_found:
                print(f"    {r['repo']}:")
                for reg in r["regressions"]:
                    print(f"      - {reg}")
        avg_score = sum(r["health_score"] for r in results) / len(results) if results else 0
        print(f"\n  Avg health score: {avg_score:.1f}")
    return 0 if not regressions_found else 1


if __name__ == "__main__":
    sys.exit(main())
