#!/usr/bin/env python3
"""
repo_dashboard.py — Cross-repo health dashboard.

Renders an ASCII table of all repos in the registry with their health
scores, coverage, and last-tick timestamps. Optionally writes HTML.

Usage:
    python3 ~/.hermes/scripts/repo_dashboard.py
    python3 ~/.hermes/scripts/repo_dashboard.py --html
    python3 ~/.hermes/scripts/repo_dashboard.py --json

Adopted from Eneve's pre-merge summary view.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
SNAPSHOTS_DIR = STATE / "health-snapshots"
DASHBOARD_PATH = STATE / "dashboard.html"


def load_snapshots() -> list[dict]:
    """Load all repo snapshots."""
    snapshots = []
    for path in sorted(SNAPSHOTS_DIR.glob("*.json")):
        try:
            snapshots.append(json.loads(path.read_text()))
        except Exception:
            continue
    return snapshots


def render_ascii(snapshots: list[dict]) -> None:
    """Render ASCII table."""
    if not snapshots:
        print("  (no snapshots yet; run repo_tick first)")
        return
    # Sort by health score ascending (worst first — so operator sees what needs attention)
    snapshots.sort(key=lambda s: s.get("health_score", 0))
    print(f"\n=== Repo Dashboard — {len(snapshots)} repos — {datetime.now(timezone.utc).isoformat()} ===\n")
    print(f"  {'Repo':<30} {'Score':>5} {'Coverage':>9} {'Branch':<12} {'Last tick':<22} {'Status':<10}")
    print(f"  {'─' * 30} {'─' * 5} {'─' * 9} {'─' * 12} {'─' * 22} {'─' * 10}")
    for s in snapshots:
        score = s.get("health_score", 0)
        status = "✓" if score >= 70 else ("⚠" if score >= 50 else "✗")
        cov = s.get("coverage", {}).get("final_coverage", 0)
        cov_str = f"{cov*100:.1f}%" if isinstance(cov, (int, float)) else "N/A"
        branch = s.get("current_branch", "?")[:11]
        ts = s.get("timestamp", "?")[:19]
        repo = s.get("repo", "?")[:29]
        print(f"  {repo:<30} {score:>5} {cov_str:>9} {branch:<12} {ts:<22} {status:<10}")
    avg = sum(s.get("health_score", 0) for s in snapshots) / len(snapshots)
    print(f"\n  Average health score: {avg:.1f}")
    print(f"  Threshold: 70 (pass) / 50 (warn) / else fail")


def render_html(snapshots: list[dict]) -> None:
    """Render HTML dashboard."""
    from html import escape
    snapshots.sort(key=lambda s: s.get("health_score", 0))
    html = ['<!DOCTYPE html>']
    html.append('<html><head><meta charset="utf-8">')
    html.append('<title>Hermes Repo Dashboard</title>')
    html.append('<style>')
    html.append('body { font-family: -apple-system, system-ui, sans-serif; margin: 20px; background: #0a0a0a; color: #e0e0e0; }')
    html.append('table { border-collapse: collapse; width: 100%; max-width: 1100px; }')
    html.append('th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #222; }')
    html.append('th { background: #1a1a1a; color: #999; font-weight: 500; text-transform: uppercase; font-size: 11px; }')
    html.append('tr:hover { background: #1a1a1a; }')
    html.append('.score-good { color: #4ade80; font-weight: 600; }')
    html.append('.score-warn { color: #fbbf24; font-weight: 600; }')
    html.append('.score-bad { color: #f87171; font-weight: 600; }')
    html.append('.avg { margin-top: 20px; padding: 12px; background: #1a1a1a; border-radius: 8px; max-width: 1100px; }')
    html.append('h1 { font-size: 18px; margin-bottom: 16px; }')
    html.append('</style></head><body>')
    html.append('<h1>Hermes Repo Dashboard — ' + escape(datetime.now(timezone.utc).isoformat()) + '</h1>')
    html.append('<table>')
    html.append('<tr><th>Repo</th><th>Score</th><th>Coverage</th><th>Branch</th><th>Last tick</th></tr>')
    for s in snapshots:
        score = s.get("health_score", 0)
        cls = "score-good" if score >= 70 else ("score-warn" if score >= 50 else "score-bad")
        cov = s.get("coverage", {}).get("final_coverage", 0)
        cov_str = f"{cov*100:.1f}%" if isinstance(cov, (int, float)) else "N/A"
        branch = escape(s.get("current_branch", "?")[:30])
        ts = escape(s.get("timestamp", "?")[:19])
        repo = escape(s.get("repo", "?")[:40])
        html.append(f'<tr><td>{repo}</td><td class="{cls}">{score}</td><td>{cov_str}</td><td>{branch}</td><td>{ts}</td></tr>')
    html.append('</table>')
    if snapshots:
        avg = sum(s.get("health_score", 0) for s in snapshots) / len(snapshots)
        html.append(f'<div class="avg">Average health score: <strong>{avg:.1f}</strong> · Threshold: 70 (pass) / 50 (warn) / else fail</div>')
    html.append('</body></html>')
    DASHBOARD_PATH.write_text("\n".join(html))


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-repo health dashboard")
    parser.add_argument("--html", action="store_true", help="Also render HTML")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    snapshots = load_snapshots()
    if args.json:
        print(json.dumps({"skill": "repo-dashboard", "version": "1.0.0", "snapshots": snapshots}, indent=2))
    else:
        render_ascii(snapshots)
    if args.html:
        render_html(snapshots)
        print(f"\n  HTML dashboard: {DASHBOARD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
