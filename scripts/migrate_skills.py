#!/usr/bin/env python3
"""
migrate_skills.py — Migrate old skills to the structured frontmatter schema.

For each skill missing `kind` and/or `provenance` fields, add them with
heuristic defaults derived from the skill name and existing metadata.

Usage:
    python3 ~/.hermes/scripts/migrate_skills.py --dry-run
    python3 ~/.hermes/scripts/migrate_skills.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


HERMES_HOME = Path.home() / ".hermes"
SKILLS_DIR = HERMES_HOME / "skills"

# Heuristic kind inference from name patterns
# Valid kinds per validator: skill, meta, orchestration, validator
KIND_PATTERNS = [
    (r"^quality-gate$|^coverage-runner|^complexity", "orchestration"),
    (r"-gate$|-runner$", "orchestration"),
    (r"^delivery-prep$|^pre-merge|^changelog-releaser$|^git-pr-workflow$", "orchestration"),
    (r"^find-dead-code$|^api-refactor$|^code-review-exemplar$|^simplify-code$|^doc-architecture$", "skill"),
    (r"^(.*?)verify$", "skill"),
    (r"manage-playbook$|^ticket-lifecycle$", "orchestration"),
    (r"^manage-|^admin-|^onboard-", "skill"),
    (r"^create-|^build-|^generate-|^scaffold-", "skill"),
    (r"^analyze-|^audit-|^inspect-|^review-", "skill"),
    (r"^deploy-|^monitor-|^watchdog-|^alert-", "skill"),
    (r"^test-|^verify-|^check-", "skill"),
    (r"^hermes-", "meta"),
]


def infer_kind(name: str) -> str:
    """Infer kind from skill name (must be in validator's enum)."""
    for pattern, kind in KIND_PATTERNS:
        if re.search(pattern, name):
            return kind
    return "skill"


def infer_provenance(name: str, content: str) -> dict:
    """Infer provenance from content heuristics."""
    prov = {
        "owner": "erebus",
        "last_review": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "migrated",
        "round": "R4-migration",
    }
    if "cursor_20260628" in content or "Eneve" in content:
        prov["source"] = "cursor-loop R4"
        prov["round"] = "R4"
    if "Round 5" in content or "R5" in content or "autonomous" in content.lower():
        prov["source"] = "cursor-loop R5"
        prov["round"] = "R5"
    return prov


def parse_frontmatter(content: str) -> tuple[dict | None, str]:
    """Parse frontmatter; return (dict, error)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return None, "no frontmatter"
    try:
        data = yaml.safe_load(m.group(1))
        if not isinstance(data, dict):
            return None, "frontmatter is not a mapping"
        return data, ""
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {str(e)[:80]}"


def needs_migration(fm: dict) -> tuple[bool, set[str]]:
    """Check what fields are missing or invalid."""
    VALID_KINDS = {"skill", "meta", "orchestration", "validator"}
    missing = set()
    if not fm.get("kind") or fm.get("kind") not in VALID_KINDS:
        missing.add("kind")
    if not fm.get("provenance"):
        missing.add("provenance")
    if not fm.get("version"):
        missing.add("version")
    return bool(missing), missing


def migrate_skill(skill_path: Path, dry_run: bool = False) -> dict:
    """Migrate one skill. Returns result dict."""
    name = skill_path.name
    md_path = skill_path / "SKILL.md"
    if not md_path.exists():
        return {"name": name, "status": "skip", "reason": "no SKILL.md"}
    content = md_path.read_text()
    fm, err = parse_frontmatter(content)
    if fm is None:
        return {"name": name, "status": "skip", "reason": f"frontmatter parse: {err}"}
    needs, missing = needs_migration(fm)
    if not needs:
        return {"name": name, "status": "skip", "reason": "already compliant"}
    # Infer missing fields
    if "kind" in missing:
        fm["kind"] = infer_kind(name)
    if "version" in missing:
        fm["version"] = fm.get("version", "1.0.0")
    if "provenance" in missing:
        fm["provenance"] = infer_provenance(name, content)
    # Re-serialize
    new_fm_yaml = yaml.safe_dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
    # Replace frontmatter
    new_content = re.sub(
        r"^---\s*\n.*?\n---\s*\n",
        f"---\n{new_fm_yaml}\n---\n\n",
        content,
        count=1,
        flags=re.DOTALL,
    )
    if dry_run:
        return {"name": name, "status": "would-migrate", "added": list(missing), "kind": fm.get("kind")}
    md_path.write_text(new_content)
    return {"name": name, "status": "migrated", "added": list(missing), "kind": fm.get("kind")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate old skills to structured frontmatter")
    parser.add_argument("--dry-run", action="store_true", help="Don't write, just show what would happen")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    results = []
    for skill_path in sorted(SKILLS_DIR.iterdir()):
        if not skill_path.is_dir() or skill_path.name == "collections":
            continue
        if not (skill_path / "SKILL.md").exists():
            continue
        result = migrate_skill(skill_path, dry_run=args.dry_run)
        results.append(result)

    # Summary
    migrated = [r for r in results if r["status"] == "migrated"]
    would = [r for r in results if r["status"] == "would-migrate"]
    skipped = [r for r in results if r["status"] == "skip"]

    if args.json:
        print(json.dumps({
            "skill": "skill-migrator",
            "version": "1.0.0",
            "dry_run": args.dry_run,
            "migrated": len(migrated),
            "would_migrate": len(would),
            "skipped": len(skipped),
            "results": results,
        }, indent=2))
    else:
        action = "WOULD MIGRATE" if args.dry_run else "MIGRATED"
        print(f"\n=== Skill Migrator ({'dry-run' if args.dry_run else 'live'}) ===")
        print(f"  {action}: {len(migrated) or len(would)}")
        print(f"  Skipped: {len(skipped)}")
        if migrated or would:
            target = migrated if migrated else would
            print(f"\n  Top 5:")
            for r in target[:5]:
                print(f"    {r['name']:<40} kind={r.get('kind', '?')} added={r.get('added', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())