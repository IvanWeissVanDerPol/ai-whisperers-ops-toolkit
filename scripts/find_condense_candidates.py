#!/usr/bin/env python3
"""
find_condense_candidates.py — Find skills that are too long.

Skills over 300 lines are flagged for condensation. The condensation
process moves bulky sections (examples, scripts, templates) to references/
and replaces them with one-line pointers.

Usage:
    python3 ~/.hermes/scripts/find_condense_candidates.py
    python3 ~/.hermes/scripts/find_condense_candidates.py --threshold 200
    python3 ~/.hermes/scripts/find_condense_candidates.py --json

Adopted from Eneve's `find-condense-candidates.prompt.md`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description="Find oversized skills")
    parser.add_argument("--threshold", type=int, default=300, help="Lines threshold (default 300)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    candidates = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name == "collections":
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        lines = len(skill_md.read_text().split("\n"))
        if lines > args.threshold:
            candidates.append({
                "skill": skill_dir.name,
                "lines": lines,
                "excess": lines - args.threshold,
            })

    candidates.sort(key=lambda c: -c["lines"])

    if args.json:
        print(json.dumps({
            "skill": "find-condense-candidates",
            "version": "1.0.0",
            "threshold": args.threshold,
            "count": len(candidates),
            "candidates": candidates,
        }, indent=2))
    else:
        print(f"\n=== Skills over {args.threshold} lines: {len(candidates)} ===")
        for c in candidates[:20]:
            print(f"  {c['skill']:<40} {c['lines']:>5} lines (+{c['excess']})")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
