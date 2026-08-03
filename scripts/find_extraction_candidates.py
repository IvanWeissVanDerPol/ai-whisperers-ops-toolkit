#!/usr/bin/env python3
"""
find_extraction_candidates.py — Find skills ready for templar/exemplar extraction.

A skill is a candidate if:
- Has ## Examples section (could become an exemplar)
- Has ## Output / ## Template section (could become a templar)
- Has long code blocks (could become a script reference)
- Already has references/ but no templar/exemplar frontmatter

Usage:
    python3 ~/.hermes/scripts/find_extraction_candidates.py
    python3 ~/.hermes/scripts/find_extraction_candidates.py --json
    python3 ~/.hermes/scripts/find_extraction_candidates.py --skill <skill-name>

Adopted from Eneve's `find-extraction-candidates.prompt.md`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"


def find_in_skill(skill_md: Path) -> dict:
    """Analyze a single skill for extraction candidates."""
    content = skill_md.read_text(errors="replace")
    candidates = []
    # Parse frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    has_templar = bool(fm_match) and "templar:" in (fm_match.group(1) if fm_match else "")
    has_exemplar = bool(fm_match) and "exemplar:" in (fm_match.group(1) if fm_match else "")
    # Look for extractable patterns
    if "## Examples" in content or "### Example" in content:
        candidates.append("exemplar")
    if "## Output" in content or "## Template" in content or "## Output Contract" in content:
        candidates.append("templar")
    # Long code blocks (could be scripts)
    code_blocks = re.findall(r"```(\w+)\n(.*?)```", content, re.DOTALL)
    total_lines = sum(len(b.split("\n")) for _, b in code_blocks)
    if total_lines > 50:
        candidates.append("script-extract")
    # Has references/ folder
    refs_dir = skill_md.parent / "references"
    if refs_dir.exists():
        if not has_templar:
            candidates.append("templar")
        if not has_exemplar:
            candidates.append("exemplar")
    return {
        "skill": skill_md.parent.name,
        "candidates": candidates,
        "has_templar": has_templar,
        "has_exemplar": has_exemplar,
        "code_lines": total_lines,
        "refs_exists": refs_dir.exists(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Find extraction candidates")
    parser.add_argument("--skill", help="Single skill name")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--category", help="Filter by category")
    args = parser.parse_args()

    targets = []
    if args.skill:
        targets = [SKILLS_DIR / args.skill]
    else:
        for p in sorted(SKILLS_DIR.iterdir()):
            if p.is_dir() and (p / "SKILL.md").exists() and p.name != "collections":
                targets.append(p)

    results = []
    for skill_dir in targets:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        info = find_in_skill(skill_md)
        if info["candidates"]:
            results.append(info)

    if args.json:
        print(json.dumps({
            "skill": "find-extraction-candidates",
            "version": "1.0.0",
            "count": len(results),
            "candidates": results,
        }, indent=2))
    else:
        print(f"\n=== Extraction candidates: {len(results)} skills ===")
        for r in results:
            tags = ", ".join(r["candidates"])
            print(f"  {r['skill']:<40} → {tags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
