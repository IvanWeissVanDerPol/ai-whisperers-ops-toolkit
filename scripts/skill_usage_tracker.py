#!/usr/bin/env python3
"""
skill_usage_tracker.py — Track skill usage from logs.

Scans ~/.hermes/logs/skill_view.log (if it exists) and other log files
to count skill loads per day. Identifies dead skills (0 loads in 30 days)
and high-use skills (>= 10 loads/week).

Cron: hourly.

Usage:
    python3 ~/.hermes/scripts/skill_usage_tracker.py
    python3 ~/.hermes/scripts/skill_usage_tracker.py --days 30
    python3 ~/.hermes/scripts/skill_usage_tracker.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
LOGS_DIR = HERMES_HOME / "logs"
STATE = HERMES_HOME / "state"
USAGE_PATH = STATE / "skill-usage.json"
SKILLS_DIR = HERMES_HOME / "skills"


def find_all_skill_names() -> set[str]:
    """Inventory all current skills."""
    names = set()
    for p in SKILLS_DIR.iterdir():
        if p.is_dir() and (p / "SKILL.md").exists():
            names.add(p.name)
    return names


def scan_logs(days: int = 30) -> dict[str, int]:
    """Scan logs for skill-view mentions, count per skill (fast)."""
    if not LOGS_DIR.exists():
        return {}
    all_skills = find_all_skill_names()
    counts = defaultdict(int)
    # Build a single regex OR pattern for all skill names (fast)
    skill_pattern = re.compile("|".join(re.escape(s) for s in all_skills))
    # Only scan recent log files (last 30 days)
    cutoff_time = datetime.now(timezone.utc).timestamp() - (days * 86400)
    log_files = []
    for log_path in LOGS_DIR.glob("*.log*"):
        try:
            if log_path.stat().st_mtime > cutoff_time:
                log_files.append(log_path)
        except Exception:
            continue
    # Limit to last 50 log files to avoid scanning huge history
    log_files = sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)[:50]
    for log_path in log_files:
        try:
            content = log_path.read_text(errors="replace")
        except Exception:
            continue
        for match in skill_pattern.finditer(content):
            counts[match.group(0)] += 1
    return dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Track skill usage from logs")
    parser.add_argument("--days", type=int, default=30, help="Look-back window in days")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    counts = scan_logs(days=args.days)
    all_skills = find_all_skill_names()
    # Categorize
    dead = sorted([s for s in all_skills if counts.get(s, 0) == 0])
    active = sorted([s for s in all_skills if counts.get(s, 0) > 0])
    high_use = sorted([s for s, c in counts.items() if c >= 10], key=lambda s: -counts[s])

    report = {
        "skill": "skill-usage-tracker",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "window_days": args.days,
        "total_skills": len(all_skills),
        "active_skills": len(active),
        "dead_skills": len(dead),
        "high_use_skills": len(high_use),
        "dead": dead,
        "high_use": [{"skill": s, "loads": counts[s]} for s in high_use],
        "counts": counts,
    }
    USAGE_PATH.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Skill Usage Tracker ===")
        print(f"  Total skills: {len(all_skills)}")
        print(f"  Active (>=1 load): {len(active)}")
        print(f"  Dead (0 loads in {args.days}d): {len(dead)}")
        print(f"  High-use (>=10 loads): {len(high_use)}")
        if high_use:
            print(f"\n  Top 5 high-use:")
            for s in high_use[:5]:
                print(f"    {s}: {counts[s]} loads")
        if dead:
            print(f"\n  First 10 dead skills:")
            for s in dead[:10]:
                print(f"    - {s}")
        print(f"\n  Report saved to {USAGE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
