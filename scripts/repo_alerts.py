#!/usr/bin/env python3
"""
repo_alerts.py — Per-repo alert routing.

Reads project-specific notification preferences from projects.yaml and
routes alerts to the configured channel.

Each project can have a `notifications` block:
  notifications:
    on_regression: whatsapp
    on_health_drop: telegram
    on_anomaly: slack
    threshold:
      health_drop: 10   # alert if health drops > 10 points
      coverage_drop: 0.05  # alert if coverage drops > 5%

Usage:
    python3 ~/.hermes/scripts/repo_alerts.py --all
    python3 ~/.hermes/scripts/repo_alerts.py --repo psycology
    python3 ~/.hermes/scripts/repo_alerts.py --kind regression --all
    python3 ~/.hermes/scripts/repo_alerts.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
SCRIPTS = HERMES_HOME / "scripts"
PROJECTS_YAML = STATE / "projects.yaml"
SNAPSHOTS_DIR = STATE / "health-snapshots"


def load_projects() -> list[dict]:
    if not PROJECTS_YAML.exists():
        return []
    import yaml
    return yaml.safe_load(PROJECTS_YAML.read_text()).get("projects", [])


def get_notifications(project: dict) -> dict:
    """Get notification config, with defaults."""
    return project.get("notifications", {
        "on_regression": "whatsapp",
        "on_health_drop": None,  # off by default
        "on_anomaly": None,
        "threshold": {"health_drop": 15, "coverage_drop": 0.1},
    })


def check_alerts(repo: str, notifications: dict) -> list[dict]:
    """Check for alerts based on the project's config."""
    alerts = []
    # Run snapshot_diff to find regressions
    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "snapshot_diff.py"),
             "--repo", repo, "--compare", "1d", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode in (0, 1):
            data = json.loads(result.stdout)
            results = data.get("results", [])
            if results:
                alerts.append({
                    "kind": "regression",
                    "repo": repo,
                    "details": results[0].get("diff", {}),
                    "severity": "medium",
                })
    except Exception as e:
        pass

    # Check health threshold drop
    snap_path = SNAPSHOTS_DIR / f"{repo}.json"
    if snap_path.exists():
        try:
            snap = json.loads(snap_path.read_text())
            score = snap.get("health_score", 0)
            cov = snap.get("coverage", {}).get("final_coverage", 0)
            threshold = notifications.get("threshold", {})
            health_min = threshold.get("health_drop", 15)
            cov_min = threshold.get("coverage_drop", 0.1)
            # Compare against the avg of all repos
            all_snaps = []
            for p in SNAPSHOTS_DIR.glob("*.json"):
                try:
                    s = json.loads(p.read_text())
                    all_snaps.append(s.get("health_score", 0))
                except Exception:
                    continue
            avg = sum(all_snaps) / len(all_snaps) if all_snaps else 50
            if avg - score > health_min:
                alerts.append({
                    "kind": "health_drop",
                    "repo": repo,
                    "details": f"score={score}, avg={avg:.0f}, drop={avg - score:.0f}",
                    "severity": "high" if avg - score > health_min * 2 else "medium",
                })
            if cov < cov_min:
                alerts.append({
                    "kind": "coverage_low",
                    "repo": repo,
                    "details": f"coverage={cov*100:.0f}%",
                    "severity": "low",
                })
        except Exception:
            pass

    return alerts


def format_alert(alert: dict) -> str:
    """Format an alert for delivery."""
    severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(alert["severity"], "⚪")
    kind_labels = {
        "regression": "Regression detected",
        "health_drop": "Health score drop",
        "coverage_low": "Low coverage",
        "anomaly": "Anomaly detected",
    }
    label = kind_labels.get(alert["kind"], alert["kind"])
    details = alert.get("details", "")
    if isinstance(details, dict):
        details_str = ", ".join(f"{k}={v}" for k, v in details.items() if isinstance(v, (str, int, float)))
    else:
        details_str = str(details)
    return f"{severity_icon} *{label}*: `{alert['repo']}`\n  {details_str}"


def send(target: str, message: str) -> bool:
    """Send via hermes send."""
    try:
        result = subprocess.run(
            ["hermes", "send", "-t", target, message],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-repo alert routing")
    parser.add_argument("--repo", help="Single repo")
    parser.add_argument("--all", action="store_true", help="All projects")
    parser.add_argument("--kind", choices=["regression", "health_drop", "coverage_low", "anomaly"],
                        help="Alert kind filter")
    parser.add_argument("--dry-run", action="store_true", help="Don't send")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not args.repo and not args.all:
        parser.error("--repo or --all required")

    projects = load_projects()
    targets = [p for p in projects if not args.repo or p["name"] == args.repo]
    if args.repo and not targets:
        print(f"error: repo '{args.repo}' not in projects.yaml", file=sys.stderr)
        return 2

    all_alerts = []
    for project in targets:
        notifications = get_notifications(project)
        alerts = check_alerts(project["name"], notifications)
        for a in alerts:
            if args.kind and a["kind"] != args.kind:
                continue
            # Determine channel
            key = f"on_{a['kind']}"
            channel = notifications.get(key) or notifications.get("on_regression")
            a["channel"] = channel
            a["project_notifications"] = notifications
            if not args.dry_run and channel:
                msg = format_alert(a)
                a["sent"] = send(channel, msg)
            all_alerts.append(a)

    summary = {
        "skill": "repo-alerts",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "projects_scanned": len(targets),
        "alerts": all_alerts,
        "total_alerts": len(all_alerts),
        "alerts_sent": sum(1 for a in all_alerts if a.get("sent")),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n=== Repo Alerts ===")
        print(f"  Projects scanned: {len(targets)}")
        print(f"  Alerts: {summary['total_alerts']}")
        print(f"  Sent: {summary['alerts_sent']}")
        for a in all_alerts[:10]:
            print(f"  • [{a['kind']}] {a['repo']} → {a.get('channel', '?')}: sent={a.get('sent', False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())