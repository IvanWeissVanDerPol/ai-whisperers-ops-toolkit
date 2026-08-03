#!/usr/bin/env python3
"""
validate_collections.py — Validate the skill collections.

Ensures every skill is in exactly one collection, and every collection
manifest matches reality (no orphans, no duplicates).

Usage:
    python3 ~/.hermes/scripts/validate_collections.py
    python3 ~/.hermes/scripts/validate_collections.py --repo
    python3 ~/.hermes/scripts/validate_collections.py --json

Adopted from Eneve's `validate-prompt-collections.ps1` pattern.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"
COLLECTIONS_DIR = SKILLS_DIR / "collections"


def parse_collections() -> dict[str, list[str]]:
    """Parse all .yml collection files. Returns {collection_name: [skill_names]}."""
    collections = {}
    for path in sorted(COLLECTIONS_DIR.glob("*.yml")):
        name = path.stem
        content = path.read_text()
        # Find lines starting with "- " in the list section
        skills = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- ") and line.endswith("/"):
                skills.append(line[2:-1])
        collections[name] = skills
    return collections


def find_all_skills() -> set[str]:
    """Find all skill directories."""
    return {p.name for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists() and p.name != "collections"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate skill collections")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--repo", action="store_true", help="Alias for default")
    args = parser.parse_args()

    collections = parse_collections()
    all_skills = find_all_skills()
    in_collections = set()
    for coll_skills in collections.values():
        in_collections.update(coll_skills)

    # Compute diff
    orphans = sorted(all_skills - in_collections)  # Skills not in any collection
    ghosts = sorted(in_collections - all_skills)  # In collection but no skill
    duplicates = []
    seen = defaultdict(list)
    for coll, skills in collections.items():
        for s in skills:
            seen[s].append(coll)
    for s, colls in seen.items():
        if len(colls) > 1:
            duplicates.append({"skill": s, "collections": colls})

    report = {
        "skill": "validate-collections",
        "version": "1.0.0",
        "total_collections": len(collections),
        "total_skills": len(all_skills),
        "total_in_collections": len(in_collections),
        "orphans": orphans,           # Not in any collection
        "ghosts": ghosts,             # In collection but no skill
        "duplicates": duplicates,     # In multiple collections
        "valid": len(orphans) == 0 and len(ghosts) == 0 and len(duplicates) == 0,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Collection validation: {len(collections)} collections, {len(all_skills)} skills ===")
        print(f"  Skills in collections: {len(in_collections)}")
        print(f"  Orphans (not in any): {len(orphans)}")
        print(f"  Ghosts (in collection, no skill): {len(ghosts)}")
        print(f"  Duplicates (in multiple): {len(duplicates)}")
        if orphans:
            print(f"\n  Orphans:")
            for s in orphans[:20]:
                print(f"    - {s}")
        if ghosts:
            print(f"\n  Ghosts:")
            for s in ghosts[:20]:
                print(f"    - {s}")
        if duplicates:
            print(f"\n  Duplicates:")
            for d in duplicates[:20]:
                print(f"    - {d['skill']} in {d['collections']}")
        print(f"\n  {'VALID' if report['valid'] else 'INVALID'}")
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
