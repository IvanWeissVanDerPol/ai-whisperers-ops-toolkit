#!/usr/bin/env python3
"""
snapshot_diff.py — Differential snapshots for health tracking.

Keeps a rolling history of per-repo snapshots and computes diffs.
Detects regressions in coverage, health score, findings count, etc.

Usage:
    python3 ~/.hermes/scripts/snapshot_diff.py --repo psycology
    python3 ~/.hermes/scripts/snapshot_diff.py --repo psycology --compare 7d
    python3 ~/.hermes/scripts/snapshot_diff.py --all
    python3 ~/.hermes/scripts/snapshot_diff.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
SNAPSHOTS_DIR = STATE / "health-snapshots"
HISTORY_DIR = STATE / "health-history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def list_snapshots(repo_name: str) -> list[dict]:
    """List all snapshots for a repo, sorted by time."""
    snapshots = []
    for path in SNAPSHOTS_DIR.glob(f"{repo_name}*.json"):
        try:
            snapshots.append(json.loads(path.read_text()))
        except Exception:
            continue
    return sorted(snapshots, key=lambda s: s.get("timestamp", ""))


def diff_snapshots(current: dict, previous: dict) -> dict:
    """Compute diff between two snapshots."""
    diff = {"regressions": [], "improvements": []}
    if not previous:
        return {"is_baseline": True, "current_score": current.get("health_score")}
    # Health score
    prev_score = previous.get("health_score", 0)
    curr_score = current.get("health_score", 0)
    if curr_score < prev_score - 5:
        diff["regressions"].append(f"health_score: {prev_score} → {curr_score}")
    elif curr_score > prev_score + 5:
        diff["improvements"].append(f"health_score: {prev_score} → {curr_score}")
    # Coverage
    prev_cov = previous.get("coverage", {}).get("final_coverage", 0)
    curr_cov = current.get("coverage", {}).get("final_coverage", 0)
    if isinstance(prev_cov, (int, float)) and isinstance(curr_cov, (int, float)):
        if curr_cov < prev_cov - 0.05:
            diff["regressions"].append(f"coverage: {prev_cov*100:.1f}% → {curr_cov*100:.1f}%")
        elif curr_cov > prev_cov + 0.05:
            diff["improvements"].append(f"coverage: {prev_cov*100:.1f}% → {curr_cov*100:.1f}%")
    # Quality gate
    prev_qg = previous.get("quality_gate", {}).get("gate_passed", True)
    curr_qg = current.get("quality_gate", {}).get("gate_passed", True)
    if prev_qg and not curr_qg:
        diff["regressions"].append("quality_gate: PASS → FAIL")
    elif not prev_qg and curr_qg:
        diff["improvements"].append("quality_gate: FAIL → PASS")
    # Findings
    prev_f = previous.get("new_findings", 0)
    curr_f = current.get("new_findings", 0)
    if curr_f > prev_f + 5:
        diff["regressions"].append(f"new_findings: {prev_f} → {curr_f}")
    elif curr_f < prev_f:
        diff["improvements"].append(f"new_findings: {prev_f} → {curr_f}")
    return diff


def main() -> int:
    parser = argparse.ArgumentParser(description="Differential snapshots")
    parser.add_argument("--repo", help="Single repo name")
    parser.add_argument("--all", action="store_true", help="All repos")
    parser.add_argument("--compare", default="7d", help="Comparison window (e.g. 7d, 30d)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # Parse compare window
    days = 7
    if args.compare.endswith("d"):
        days = int(args.compare[:-1])

    if not args.repo and not args.all:
        parser.error("provide --repo or --all")

    # Find all repos with snapshots
    repos = []
    if args.repo:
        repos = [args.repo]
    else:
        repos = sorted({p.stem for p in SNAPSHOTS_DIR.glob("*.json")})

    results = []
    for repo_name in repos:
        snapshots = list_snapshots(repo_name)
        if len(snapshots) < 2:
            if not args.json:
                print(f"  {repo_name}: only {len(snapshots)} snapshot(s), skipping")
            continue
        current = snapshots[-1]
        # Find snapshot from N days ago
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        previous = None
        for s in snapshots[:-1]:
            ts = s.get("timestamp", "")
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            if t <= cutoff:
                previous = s
                break
        if not previous:
            previous = snapshots[0]
        diff = diff_snapshots(current, previous)
        results.append({"repo": repo_name, "diff": diff, "current_score": current.get("health_score")})
        if not args.json:
            reg = diff.get("regressions", [])
            imp = diff.get("improvements", [])
            score = current.get("health_score", 0)
            tag = ""
            if reg:
                tag += f" ⚠ {len(reg)} regressions"
            if imp:
                tag += f" ↑ {len(imp)} improvements"
            print(f"  {repo_name:<35} score={score:>3}{tag}")

    total_reg = sum(len(r["diff"].get("regressions", [])) for r in results)
    if args.json:
        print(json.dumps({"skill": "snapshot-diff", "version": "1.0.0", "total_regressions": total_reg, "results": results}, indent=2))
    else:
        if total_reg > 0:
            print(f"\n  Total regressions: {total_reg}")
        else:
            print(f"\n  ✓ No regressions detected in {len(results)} repos")
    return 0 if total_reg == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
