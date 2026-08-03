#!/usr/bin/env python3
"""
validate_skill_frontmatter.py - Skill frontmatter schema validator.

Validates Hermes skill SKILL.md frontmatter against the structured schema
defined in `~/.hermes/skills/skill-frontmatter-schema/`.

Usage:
    python3 ~/.hermes/scripts/validate_skill_frontmatter.py --dir ~/.hermes/skills/
    python3 ~/.hermes/scripts/validate_skill_frontmatter.py --path <skill-dir>
    python3 ~/.hermes/scripts/validate_skill_frontmatter.py --report missing-only
    python3 ~/.hermes/scripts/validate_skill_frontmatter.py --json

Adopted from Eneve's `validate-prompt-collections.ps1` pattern
(cursor_20260628-2.zip).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# Required fields every skill MUST have
REQUIRED_FIELDS = ["name", "description", "version", "kind"]

# Recommended fields (validator reports but does not block)
RECOMMENDED_FIELDS = ["tags", "provenance", "allowed-tools", "requires"]

# Optional-but-useful fields (informational)
OPTIONAL_FIELDS = [
    "category",
    "triggers",
    "alwaysApply",
    "templar",
    "exemplar",
    "model_hints",
    "when_to_use",
    "when_not_to_use",
    "metadata",
    "license",
    "author",
    "related_skills",
]

# Field aliases (legacy → canonical)
ALIASES = {
    "title": "name",
    "input": "inputs",
    "output": "outputs",
    "trigger": "triggers",
}

# Field type expectations
FIELD_TYPES = {
    "name": str,
    "description": str,
    "version": str,
    "kind": str,
    "tags": list,
    "category": str,
    "triggers": list,
    "alwaysApply": bool,
    "allowed-tools": list,
    "requires": dict,
    "templar": str,
    "exemplar": str,
    "provenance": dict,
    "model_hints": dict,
}

# `kind` enum
VALID_KINDS = ["skill", "meta", "orchestration", "validator"]


def parse_frontmatter(content: str) -> tuple[dict[str, Any], int]:
    """Parse YAML-ish frontmatter. Returns (dict, end_line)."""
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return {}, 0
    fm = match.group(1)
    result: dict[str, Any] = {}
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
        key = m.group(1)
        value = m.group(2).strip()
        # Multi-line: list (lines starting with `- ` indented under key)
        if value == "":
            # Read indented block
            block_lines = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t")):
                block_lines.append(lines[i].strip())
                i += 1
            if not block_lines:
                result[key] = ""
                continue
            # All `-` lines → list
            if all(bl.startswith("- ") for bl in block_lines):
                result[key] = [bl[2:].strip() for bl in block_lines]
            else:
                # Inline yaml-ish dict (key: value per line)
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
        # Single-line value
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        elif value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif re.match(r"^-?\d+\.?\d*$", value):
            value = float(value) if "." in value else int(value)
        elif value.startswith("[") and value.endswith("]"):
            # Inline list: [a, b, c]
            inner = value[1:-1].strip()
            if inner:
                value = [v.strip().strip('"').strip("'") for v in inner.split(",")]
            else:
                value = []
        elif value.startswith("{") and value.endswith("}"):
            # Inline dict: {key: value, ...}
            inner = value[1:-1].strip()
            d = {}
            if inner:
                # Split on commas but be careful with quoted values
                for part in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*([^,]+?)(?=,\s*[a-zA-Z_]|$)", inner):
                    k = part.group(1).strip()
                    v = part.group(2).strip().strip('"').strip("'").strip()
                    if v.lower() in ("true", "false"):
                        v = v.lower() == "true"
                    elif re.match(r"^-?\d+\.?\d*$", v):
                        v = float(v) if "." in v else int(v)
                    d[k] = v
            value = d
        result[key] = value
        i += 1
    return result, match.end()


def validate_skill(skill_md: Path) -> dict[str, Any]:
    """Validate a single skill's frontmatter. Returns report dict."""
    content = skill_md.read_text(errors="replace")
    fm, _ = parse_frontmatter(content)
    report = {
        "path": str(skill_md.parent),
        "name": skill_md.parent.name,
        "required_ok": 0,
        "required_missing": [],
        "recommended_present": 0,
        "recommended_missing": [],
        "warnings": [],
        "errors": [],
    }
    # Required
    for field in REQUIRED_FIELDS:
        if field in fm:
            report["required_ok"] += 1
        else:
            report["required_missing"].append(field)
    # Recommended
    for field in RECOMMENDED_FIELDS:
        if field in fm:
            report["recommended_present"] += 1
        else:
            report["recommended_missing"].append(field)
    # Aliases
    for old, new in ALIASES.items():
        if old in fm and new not in fm:
            report["warnings"].append(f"deprecated field '{old}' → use '{new}'")
    # Type checks
    for field, expected in FIELD_TYPES.items():
        if field not in fm:
            continue
        value = fm[field]
        if not isinstance(value, expected):
            report["warnings"].append(
                f"field '{field}' has type {type(value).__name__}, expected {expected.__name__}"
            )
    # Enum checks
    if "kind" in fm and fm["kind"] not in VALID_KINDS:
        report["errors"].append(
            f"kind='{fm['kind']}' not in {VALID_KINDS}"
        )
    # Cross-field rules
    if fm.get("alwaysApply") is True and "triggers" in fm:
        report["warnings"].append(
            "alwaysApply=true with triggers is contradictory "
            "(Strategy 3 is global, not file-mask)"
        )
    if "requires" in fm and isinstance(fm["requires"], dict):
        for sub_key in ["skills", "scripts"]:
            if sub_key in fm["requires"]:
                for dep in fm["requires"][sub_key]:
                    if dep.startswith("~/"):
                        dep_path = Path.home() / dep[2:]
                    elif dep.startswith("/"):
                        dep_path = Path(dep)
                    else:
                        # Treat as skill name
                        dep_path = Path.home() / ".hermes" / "skills" / dep
                    if not dep_path.exists():
                        report["warnings"].append(
                            f"requires.{sub_key}='{dep}' not found at {dep_path}"
                        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Hermes skill frontmatter.")
    parser.add_argument("--path", help="Single skill directory to validate")
    parser.add_argument("--dir", help="Parent directory of skills (default: ~/.hermes/skills/)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--report", choices=["all", "missing-only", "errors-only"], default="all")
    args = parser.parse_args()

    if args.path:
        targets = [Path(args.path)]
    else:
        base = Path(args.dir) if args.dir else Path.home() / ".hermes" / "skills"
        targets = sorted([p for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").exists()])

    reports = []
    for skill_dir in targets:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        reports.append(validate_skill(skill_md))

    if args.json:
        print(json.dumps({"skills": reports, "total": len(reports)}, indent=2))
        return 0

    # Summary
    total = len(reports)
    compliant = sum(1 for r in reports if not r["required_missing"] and not r["errors"])
    print(f"== Skill frontmatter validation: {total} skills ==")
    print(f"   Fully compliant: {compliant}/{total}")
    print(f"   With errors: {sum(1 for r in reports if r['errors'])}")
    print(f"   With warnings: {sum(1 for r in reports if r['warnings'])}")
    print()

    if args.report == "missing-only":
        reports = [r for r in reports if r["required_missing"] or r["recommended_missing"]]
    elif args.report == "errors-only":
        reports = [r for r in reports if r["errors"]]

    for r in reports:
        status = "✓" if not r["required_missing"] and not r["errors"] else "✗"
        print(f"{status} {r['name']}")
        if r["required_missing"]:
            print(f"    REQUIRED missing: {', '.join(r['required_missing'])}")
        if r["recommended_missing"]:
            print(f"    RECOMMENDED missing: {', '.join(r['recommended_missing'])}")
        if r["errors"]:
            for e in r["errors"]:
                print(f"    ERROR: {e}")
        if r["warnings"] and args.report == "all":
            for w in r["warnings"][:3]:
                print(f"    warn: {w}")
            if len(r["warnings"]) > 3:
                print(f"    ... +{len(r['warnings']) - 3} more warnings")
    print()
    return 0 if all(not r["errors"] for r in reports) else 2


if __name__ == "__main__":
    sys.exit(main())
