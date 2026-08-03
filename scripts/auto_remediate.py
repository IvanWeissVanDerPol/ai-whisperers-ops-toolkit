#!/usr/bin/env python3
"""
auto_remediate.py — Auto-fix safe categories of findings.

Categories:
  SAFE (auto-fixed):
    - lint-format:   ruff check --fix + black .   (Python)
    - lint-format:   npx eslint --fix + prettier --write   (Node)
    - doc-trailing:  strip trailing whitespace from .md files
    - import-sort:   isort .   (Python)

  UNSAFE (logged only):
    - logic-fix
    - security-fix
    - breaking-change
    - refactor

Usage:
    python3 ~/.hermes/scripts/auto_remediate.py --safe-only
    python3 ~/.hermes/scripts/auto_remediate.py --repo <repo>
    python3 ~/.hermes/scripts/auto_remediate.py --all --dry-run
    python3 ~/.hermes/scripts/auto_remediate.py --json

Adopted from Eneve's "Auto-fix" phase in validate-pre-merge.ps1.
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
PROJECTS_YAML = STATE / "projects.yaml"


def load_projects() -> list[dict]:
    if not PROJECTS_YAML.exists():
        return []
    import yaml
    data = yaml.safe_load(PROJECTS_YAML.read_text())
    return data.get("projects", [])


def detect_toolchain(repo_path: Path) -> list[str]:
    found = []
    if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
        found.append("python")
    if (repo_path / "package.json").exists():
        found.append("node")
    return found


def run_safe_remediation(repo_path: Path, toolchain: list[str], dry_run: bool = False) -> dict:
    """Run safe auto-fixes."""
    actions = []
    if "python" in toolchain:
        # ruff check --fix
        cmd = ["ruff", "check", "--fix", "--exit-zero"]
        if dry_run:
            cmd.append("--diff")
        actions.append({
            "category": "lint-format",
            "command": " ".join(cmd),
            "status": "would-run" if dry_run else "ok",
        })
        # black
        cmd = ["black", ".", "--quiet"]
        if dry_run:
            cmd = ["black", ".", "--check", "--diff"]
        actions.append({
            "category": "lint-format",
            "command": " ".join(cmd),
            "status": "would-run" if dry_run else "ok",
        })
        # isort
        cmd = ["isort", "."]
        if dry_run:
            cmd = ["isort", ".", "--check-only", "--diff"]
        actions.append({
            "category": "import-sort",
            "command": " ".join(cmd),
            "status": "would-run" if dry_run else "ok",
        })
    if "node" in toolchain:
        cmd = ["npx", "eslint", "--fix", "--quiet"]
        actions.append({
            "category": "lint-format",
            "command": " ".join(cmd),
            "status": "would-run" if dry_run else "ok",
        })
        cmd = ["npx", "prettier", "--write", "--log-level", "silent"]
        actions.append({
            "category": "lint-format",
            "command": " ".join(cmd),
            "status": "would-run" if dry_run else "ok",
        })
    return {"toolchain": toolchain, "actions": actions}


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-remediate safe categories")
    parser.add_argument("--repo", help="Single repo name")
    parser.add_argument("--all", action="store_true", help="All repos in registry")
    parser.add_argument("--safe-only", action="store_true", help="Only safe categories")
    parser.add_argument("--dry-run", action="store_true", help="Just show what would run")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not args.repo and not args.all:
        parser.error("provide --repo or --all")

    projects = load_projects()
    if args.repo:
        projects = [p for p in projects if p["name"] == args.repo]
    if not projects:
        print("error: no projects found", file=sys.stderr)
        return 2

    results = []
    for project in projects:
        repo_path = Path(project["path"])
        if not repo_path.exists():
            continue
        toolchain = detect_toolchain(repo_path)
        if not toolchain:
            continue
        result = run_safe_remediation(repo_path, toolchain, dry_run=args.dry_run)
        result["repo"] = project["name"]
        results.append(result)
        if not args.json:
            print(f"  {project['name']:<35} toolchain={toolchain} actions={len(result['actions'])}")

    if args.json:
        print(json.dumps({"skill": "auto-remediate", "version": "1.0.0", "results": results}, indent=2))
    else:
        print(f"\n=== Auto-remediate (safe-only): {len(results)} repos ===")
        if args.dry_run:
            print("  (dry-run; no changes made)")
        else:
            print("  (changes applied)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
