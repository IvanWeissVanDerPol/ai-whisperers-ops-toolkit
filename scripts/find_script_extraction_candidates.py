#!/usr/bin/env python3
"""
find_script_extraction_candidates.py — Find inline scripts that should be moved to scripts/.

Identifies large code blocks in SKILL.md files that should be extracted
to ~/hermes/scripts/ or /root/.hermes/skills/<skill>/scripts/.

Usage:
    python3 ~/.REPLACE_ME.py
    python3 ~/.REPLACE_ME.py --json
    python3 ~/.REPLACE_ME.py --min-lines 80

Adopted from Eneve's `find-script-extraction-candidates.prompt.md`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"


def find_in_skill(skill_md: Path, min_lines: int) -> list[dict]:
    """Find large code blocks in a skill."""
    content = skill_md.read_text(errors="replace")
    blocks = []
    for m in re.finditer(r"```(\w+)\n(.*?)```", content, re.DOTALL):
        lang = m.group(1)
        code = m.group(2)
        lines = code.count("\n") + 1
        if lines >= min_lines and lang in ("bash", "sh", "python", "py", "javascript", "js", "typescript", "ts", "yaml", "yml"):
            blocks.append({
                "skill": skill_md.parent.name,
                "language": lang,
                "lines": lines,
                "preview": code.split("\n")[0][:80],
            })
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser(description="Find inline-script extraction candidates")
    parser.add_argument("--min-lines", type=int, default=50, help="Minimum codeblock lines (default 50)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    all_blocks = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name == "collections":
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        blocks = find_in_skill(skill_md, args.min_lines)
        all_blocks.extend(blocks)

    all_blocks.sort(key=lambda b: -b["lines"])

    if args.json:
        print(json.dumps({
            "skill": "find-script-extraction-candidates",
            "version": "1.0.0",
            "min_lines": args.min_lines,
            "count": len(all_blocks),
            "blocks": all_blocks,
        }, indent=2))
    else:
        print(f"\n=== Script extraction candidates (≥{args.min_lines} lines): {len(all_blocks)} ===")
        for b in all_blocks[:20]:
            print(f"  {b['skill']:<40} {b['language']:<8} {b['lines']:>4} lines")
            print(f"      → {b['preview']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
