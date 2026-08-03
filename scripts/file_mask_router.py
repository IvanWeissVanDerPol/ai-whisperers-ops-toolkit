#!/usr/bin/env python3
"""
file_mask_router.py — Strategy 1: file-mask triggered skill loading.

Given a file path (or glob), find which skills have matching `triggers`
in their frontmatter. Implements the 3 invocation strategies:

Strategy 1: file-mask triggered (this skill)
Strategy 2: description-triggered (handled by skill_view natively)
Strategy 3: always-apply (handled by `auto_load` config)

Usage:
    python3 ~/.hermes/scripts/file_mask_router.py --path src/handler.py
    python3 ~/.hermes/scripts/file_mask_router.py --path src/handler.py --json
    python3 ~/.hermes/scripts/file_mask_router.py --find-glob "**/*.py"
    python3 ~/.hermes/scripts/file_mask_router.py --list-always-apply

Adopted from Eneve's rule invocation strategies (rule-invocation-strategies.mdc).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"


def parse_frontmatter(content: str) -> tuple[dict, int]:
    """Parse YAML-ish frontmatter. Returns (dict, end_line)."""
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return {}, 0
    fm = match.group(1)
    result: dict = {}
    lines = fm.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).strip()
        if value == "":
            block_lines = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t")):
                block_lines.append(lines[i].strip())
                i += 1
            if block_lines and all(bl.startswith("- ") for bl in block_lines):
                result[key] = [bl[2:].strip() for bl in block_lines]
            else:
                d = {}
                for bl in block_lines:
                    km = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", bl)
                    if km:
                        d[km.group(1)] = km.group(2).strip()
                if d:
                    result[key] = d
                else:
                    result[key] = "\n".join(block_lines)
            continue
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        elif value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            result[key] = [v.strip().strip('"').strip("'") for v in inner.split(",")] if inner else []
        else:
            result[key] = value
        i += 1
    return result, match.end()


def load_skills_index() -> list[dict]:
    """Load all skills with their frontmatter."""
    skills = []
    for p in sorted(SKILLS_DIR.iterdir()):
        if not p.is_dir():
            continue
        skill_md = p / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            content = skill_md.read_text(errors="replace")
        except Exception:
            continue
        fm, _ = parse_frontmatter(content)
        if not fm:
            continue
        # Strip quotes from triggers (YAML list items sometimes have quotes)
        triggers = fm.get("triggers", [])
        if isinstance(triggers, list):
            triggers = [t.strip().strip('"').strip("'") for t in triggers]
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        skills.append({
            "path": str(p),
            "name": p.name,
            "triggers": triggers,
            "alwaysApply": fm.get("alwaysApply", False),
            "kind": fm.get("kind", "skill"),
            "tags": tags,
            "category": fm.get("category", ""),
            "description": fm.get("description", "")[:200],
        })
    return skills


def glob_matches(glob: str, path: str) -> bool:
    """Match a glob against a file path. Supports ** patterns via pathlib."""
    from pathlib import PurePath, Path
    # Strip quotes from glob (YAML list items)
    glob = glob.strip().strip('"').strip("'")
    # Try pathlib PurePath.match (handles ** recursively)
    try:
        pure = PurePath(path)
        if pure.match(glob):
            return True
    except Exception:
        pass
    # Try without leading **/ (PurePath.** requires matches to start at root)
    if glob.startswith("**/"):
        alt = glob[3:]
        try:
            pure = PurePath(path)
            if pure.match(alt):
                return True
            # Also try with **
            if pure.match("**/" + alt):
                return True
        except Exception:
            pass
    # Fallback to fnmatch
    try:
        fp = Path(path)
        if fp.is_absolute():
            try:
                fp = fp.relative_to(Path.cwd())
            except ValueError:
                pass
        return fnmatch.fnmatch(str(fp), glob)
    except Exception:
        return False


def find_skills_for_file(file_path: str, skills: list[dict]) -> list[dict]:
    """Strategy 1: Find skills matching a file path."""
    matches = []
    for s in skills:
        for trigger in s.get("triggers", []):
            if glob_matches(trigger, file_path):
                matches.append({
                    "skill": s["name"],
                    "kind": s["kind"],
                    "trigger": trigger,
                    "description": s["description"],
                })
                break
    return matches


def find_always_apply(skills: list[dict]) -> list[dict]:
    """Strategy 3: Always-apply skills."""
    return [{
        "skill": s["name"],
        "kind": s["kind"],
        "description": s["description"],
    } for s in skills if s.get("alwaysApply")]


def find_skills_by_glob(glob: str, skills: list[dict]) -> list[dict]:
    """Find skills whose `triggers` contain the given glob."""
    return [{
        "skill": s["name"],
        "kind": s["kind"],
        "triggers": s["triggers"],
        "description": s["description"],
    } for s in skills if glob in s.get("triggers", [])]


def main() -> int:
    parser = argparse.ArgumentParser(description="Strategy 1 file-mask skill router")
    parser.add_argument("--path", help="File path to match")
    parser.add_argument("--find-glob", help="Find skills with this glob in triggers")
    parser.add_argument("--list-always-apply", action="store_true", help="List always-apply skills")
    parser.add_argument("--list-all", action="store_true", help="List all skills with strategy metadata")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    skills = load_skills_index()

    if args.list_always_apply:
        aa = find_always_apply(skills)
        if args.json:
            print(json.dumps({"strategy": "always-apply", "skills": aa}, indent=2))
        else:
            print(f"=== Always-apply skills (Strategy 3): {len(aa)} ===")
            for s in aa:
                print(f"  - {s['skill']} ({s['kind']}): {s['description'][:80]}")
        return 0

    if args.list_all:
        if args.json:
            print(json.dumps({
                "strategy": "all",
                "count": len(skills),
                "with_triggers": sum(1 for s in skills if s.get("triggers")),
                "always_apply": sum(1 for s in skills if s.get("alwaysApply")),
                "skills": skills,
            }, indent=2))
        else:
            print(f"=== All skills: {len(skills)} ===")
            print(f"  With file-mask triggers (Strategy 1): {sum(1 for s in skills if s.get('triggers'))}")
            print(f"  Always-apply (Strategy 3): {sum(1 for s in skills if s.get('alwaysApply'))}")
            print(f"  Description-only (Strategy 2): {len(skills) - sum(1 for s in skills if s.get('triggers') or s.get('alwaysApply'))}")
        return 0

    if args.find_glob:
        matching = find_skills_by_glob(args.find_glob, skills)
        if args.json:
            print(json.dumps({"glob": args.find_glob, "matching": matching}, indent=2))
        else:
            print(f"=== Skills with trigger '{args.find_glob}': {len(matching)} ===")
            for s in matching:
                print(f"  - {s['skill']} ({s['kind']})")
        return 0

    if args.path:
        matches = find_skills_for_file(args.path, skills)
        if args.json:
            print(json.dumps({
                "skill": "file-mask-router",
                "file": args.path,
                "strategy": "Strategy 1 (file-mask)",
                "matches": matches,
            }, indent=2))
        else:
            print(f"=== File-mask matches for '{args.path}': {len(matches)} ===")
            if not matches:
                print("  (no skills with matching triggers)")
            for m in matches:
                print(f"  - {m['skill']} ({m['kind']}) — matched: {m['trigger']}")
                print(f"      {m['description'][:120]}")
        return 0

    parser.error("provide --path, --find-glob, --list-always-apply, or --list-all")
    return 1


if __name__ == "__main__":
    sys.exit(main())
