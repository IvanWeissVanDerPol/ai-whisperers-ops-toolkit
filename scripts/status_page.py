#!/usr/bin/env python3
"""
status_page.py — Public status page generator.

Builds a single-file HTML page with:
  - Overall health score (gauge)
  - Per-repo status cards
  - Last tick timestamp
  - Public API endpoints (no auth) for monitoring tools

Designed for Cloudflare Pages deployment. Single self-contained HTML
file with inline CSS + minimal JS for auto-refresh.

Usage:
    python3 ~/.hermes/scripts/status_page.py
    python3 ~/.hermes/scripts/status_page.py --output /var/www/status.html
    python3 ~/.hermes/scripts/status_page.py --json
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
DEFAULT_OUTPUT = HERMES_HOME / "state" / "status.html"


def load_snapshots() -> list[dict]:
    snapshots = []
    for path in sorted(SNAPSHOTS_DIR.glob("*.json")):
        try:
            snapshots.append(json.loads(path.read_text()))
        except Exception:
            continue
    return snapshots


def gauge_color(score: int) -> str:
    if score >= 70:
        return "#10b981"  # green
    if score >= 50:
        return "#f59e0b"  # amber
    return "#ef4444"  # red


def render_html(snapshots: list[dict], generated: str) -> str:
    # Sort by health score (worst first)
    snapshots.sort(key=lambda s: s.get("health_score", 0))
    total = len(snapshots)
    avg = sum(s.get("health_score", 0) for s in snapshots) / total if total else 0
    # Build per-repo cards
    cards = []
    for s in snapshots:
        score = s.get("health_score", 0)
        cov = s.get("coverage", {}).get("final_coverage", 0)
        cov_str = f"{cov*100:.0f}%" if isinstance(cov, (int, float)) else "—"
        branch = s.get("current_branch", "?")
        days = s.get("git_status", {}).get("days_since_commit")
        days_str = f"{days}d" if isinstance(days, (int, float)) else "—"
        uncommitted = s.get("git_status", {}).get("uncommitted_files", 0)
        color = gauge_color(score)
        cards.append(f"""
        <div class="repo-card" data-score="{score}">
          <div class="repo-header">
            <span class="repo-name">{s.get('repo', '?')}</span>
            <span class="score-badge" style="background:{color}">{score}</span>
          </div>
          <div class="repo-meta">
            <div class="meta-row"><span>Branch</span><code>{branch}</code></div>
            <div class="meta-row"><span>Coverage</span><code>{cov_str}</code></div>
            <div class="meta-row"><span>Last commit</span><code>{days_str}</code></div>
            <div class="meta-row"><span>Uncommitted</span><code>{uncommitted}</code></div>
          </div>
        </div>""")
    cards_html = "\n".join(cards)
    # Overall gauge
    overall_color = gauge_color(int(avg))
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hermes Status</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<style>
  :root {{
    --bg: #0a0a0a; --fg: #e0e0e0; --card-bg: #1a1a1a; --border: #2a2a2a;
    --green: #10b981; --amber: #f59e0b; --red: #ef4444; --muted: #666;
  }}
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 24px;
         background: var(--bg); color: var(--fg); }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  .gauge {{ display: inline-flex; align-items: center; gap: 16px; padding: 16px 24px;
          background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border);
          margin-bottom: 32px; }}
  .gauge-score {{ font-size: 48px; font-weight: 700; }}
  .gauge-label {{ font-size: 14px; color: var(--muted); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
  .repo-card {{ background: var(--card-bg); border: 1px solid var(--border);
                border-radius: 8px; padding: 14px; }}
  .repo-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
  .repo-name {{ font-weight: 600; font-size: 14px; }}
  .score-badge {{ color: white; padding: 2px 10px; border-radius: 12px;
                 font-size: 12px; font-weight: 600; }}
  .repo-meta {{ font-size: 12px; }}
  .meta-row {{ display: flex; justify-content: space-between; padding: 3px 0; color: var(--muted); }}
  .meta-row code {{ color: var(--fg); font-family: monospace; }}
  .api-info {{ margin-top: 32px; padding: 16px; background: var(--card-bg);
              border: 1px solid var(--border); border-radius: 8px; font-size: 13px; }}
  .api-info code {{ background: #0f0f0f; padding: 2px 6px; border-radius: 3px; }}
</style>
</head>
<body>
<h1>🤖 Hermes — System Status</h1>
<div class="sub">Last updated: {generated} · {total} repos monitored · auto-refresh 60s</div>
<div class="gauge">
  <div class="gauge-score" style="color: {overall_color}">{avg:.0f}</div>
  <div>
    <div>Average health score</div>
    <div class="gauge-label">across all repos</div>
  </div>
</div>
<div class="grid">
{cards_html}
</div>
<div class="api-info">
  <strong>API endpoints:</strong>
  <ul style="margin: 8px 0; padding-left: 20px;">
    <li><code>GET /api/health</code> — JSON status</li>
    <li><code>GET /api/snapshots</code> — all 45 health snapshots (JSON)</li>
    <li><code>GET /api/projects</code> — projects registry (JSON)</li>
    <li><code>GET /api/digest</code> — last cron-orchestrator run</li>
  </ul>
  Auth: <code>admin:&lt;password&gt;</code> via HTTP Basic
</div>
</body>
</html>"""
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description="Public status page generator")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path")
    parser.add_argument("--json", action="store_true", help="JSON metadata")
    args = parser.parse_args()
    snapshots = load_snapshots()
    generated = datetime.now(timezone.utc).isoformat()
    html = render_html(snapshots, generated)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    if args.json:
        print(json.dumps({
            "skill": "status-page",
            "version": "1.0.0",
            "output": str(output_path),
            "repos": len(snapshots),
            "generated": generated,
            "size_bytes": output_path.stat().st_size,
        }, indent=2))
    else:
        print(f"\n=== Status Page ===")
        print(f"  Output: {output_path}")
        print(f"  Repos: {len(snapshots)}")
        print(f"  Size: {output_path.stat().st_size} bytes")
        print(f"  Generated: {generated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())