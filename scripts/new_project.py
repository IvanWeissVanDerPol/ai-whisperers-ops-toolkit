#!/usr/bin/env python3
"""
new_project.py — Scaffold + register a new client site in 30 seconds.

Clones a template repo, customizes the name, sets up the orchestrators,
registers the project in ~/.hermes/state/projects.yaml, and triggers
the first repo_tick.

Usage:
    python3 ~/.hermes/scripts/new_project.py --name "client-x" --type "nextjs-pyme"
    python3 ~/.hermes/scripts/new_project.py --name "client-x" --type "nextjs-pyme" --dry-run
    python3 ~/.hermes/scripts/new_project.py --list-templates
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


HERMES_HOME = Path.home() / ".hermes"
PROJECTS_YAML = HERMES_HOME / "state" / "projects.yaml"
TEMPLATES = {
    "nextjs-pyme": {
        "template_path": "/root/template-nextjs-client",
        "default_branch": "main",
        "cron": "daily",
        "orchestrators": ["quality-gate", "coverage-runner", "delivery-prep"],
        "type": "nextjs-client",
    },
    "nextjs-monorepo": {
        "template_path": "/root/paragu-ai-platform",
        "default_branch": "main",
        "cron": "daily",
        "orchestrators": ["quality-gate", "coverage-runner", "delivery-prep"],
        "type": "nextjs-monorepo",
    },
    "python-research": {
        "template_path": "/root/psycology",
        "default_branch": "master",
        "cron": "weekly",
        "orchestrators": ["quality-gate", "coverage-runner"],
        "type": "python-research",
    },
    "python-pipeline": {
        "template_path": "/root/paragu-ai-leads",
        "default_branch": "main",
        "cron": "weekly",
        "orchestrators": ["quality-gate", "coverage-runner"],
        "type": "python-pipeline",
    },
}


def list_templates() -> None:
    print("\n=== Available Templates ===\n")
    for name, info in TEMPLATES.items():
        path_exists = Path(info["template_path"]).exists()
        icon = "✓" if path_exists else "✗"
        print(f"  {icon} {name:<20} → {info['template_path']:<50} ({info['type']})")
    print()


def load_projects() -> dict:
    if not PROJECTS_YAML.exists():
        return {"schema_version": "1.0.0", "kind": "projects-registry", "projects": []}
    return yaml.safe_load(PROJECTS_YAML.read_text()) or {"projects": []}


def save_projects(data: dict) -> None:
    data["total_projects"] = len(data.get("projects", []))
    data["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    PROJECTS_YAML.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))


def scaffold(name: str, template_key: str, target_dir: Path, dry_run: bool) -> list[str]:
    """Scaffold a new project from template. Returns list of actions."""
    actions = []
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"unknown template: {template_key}")
    src = Path(template["template_path"])
    if not src.exists():
        raise FileNotFoundError(f"template path missing: {src}")
    if target_dir.exists():
        return [f"skip: target {target_dir} already exists"]
    actions.append(f"cp -r {src} → {target_dir}")
    if not dry_run:
        shutil.copytree(src, target_dir)
    # Remove .git (start fresh)
    git_dir = target_dir / ".git"
    if git_dir.exists():
        actions.append(f"rm -rf {git_dir}")
        if not dry_run:
            shutil.rmtree(git_dir)
    # Update README + package.json with new name
    if not dry_run:
        for readme in target_dir.glob("**/README.md"):
            content = readme.read_text(errors="replace")
            new_content = content.replace(src.name, name).replace(src.name.upper(), name.upper())
            if new_content != content:
                readme.write_text(new_content)
                actions.append(f"updated README: {readme.relative_to(target_dir)}")
                break  # only update root README
        for pkg in target_dir.glob("**/package.json"):
            content = pkg.read_text(errors="replace")
            try:
                pdata = json.loads(content)
                pdata["name"] = name
                pkg.write_text(json.dumps(pdata, indent=2))
                actions.append(f"updated package.json: {pkg.relative_to(target_dir)}")
            except Exception:
                pass
            break  # only update root package.json
    return actions


def register_project(name: str, template_key: str, target_dir: Path) -> str:
    """Register project in projects.yaml."""
    data = load_projects()
    # Check if already registered
    if any(p.get("name") == name for p in data.get("projects", [])):
        return f"already registered: {name}"
    template = TEMPLATES[template_key]
    new_proj = {
        "name": name,
        "type": template["type"],
        "default_branch": template["default_branch"],
        "orchestrators": template["orchestrators"],
        "cron": template["cron"],
        "notes": f"Scaffolded via new_project.py on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "path": str(target_dir),
        "current_branch": template["default_branch"],
        "remote": "local",
    }
    data.setdefault("projects", []).append(new_proj)
    save_projects(data)
    return f"registered: {name} → {target_dir}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold + register a new client site")
    parser.add_argument("--name", help="Project name (e.g. 'client-x')")
    parser.add_argument("--type", choices=list(TEMPLATES.keys()), help="Project template type")
    parser.add_argument("--target", help="Target directory (default: /root/<name>)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write anything")
    parser.add_argument("--list-templates", action="store_true", help="List available templates")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list_templates:
        list_templates()
        return 0

    if not args.name or not args.type:
        parser.error("--name and --type are required (or use --list-templates)")

    target = Path(args.target) if args.target else Path(f"/root/{args.name}")
    template = TEMPLATES[args.type]

    # Validate
    if not Path(template["template_path"]).exists():
        print(f"error: template source missing: {template['template_path']}", file=sys.stderr)
        return 2

    # Step 1: scaffold
    scaffold_actions = scaffold(args.name, args.type, target, dry_run=args.dry_run)
    # Step 2: register
    register_msg = register_project(args.name, args.type, target) if not args.dry_run else f"would register: {args.name}"

    summary = {
        "skill": "new-project",
        "version": "1.0.0",
        "name": args.name,
        "type": args.type,
        "target": str(target),
        "dry_run": args.dry_run,
        "actions": scaffold_actions,
        "registration": register_msg,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n=== New Project: {args.name} ===")
        print(f"  Type: {args.type} → {template['template_path']}")
        print(f"  Target: {target}")
        print(f"  Mode: {'dry-run' if args.dry_run else 'live'}")
        print(f"\n  Actions:")
        for action in scaffold_actions:
            print(f"    • {action}")
        print(f"\n  Registration: {register_msg}")
        if not args.dry_run:
            print(f"\n  Next: run repo_tick.py --repo {args.name} to initialize health snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())