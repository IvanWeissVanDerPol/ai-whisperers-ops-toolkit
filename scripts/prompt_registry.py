#!/usr/bin/env python3
"""
prompt_registry.py — Atlas K-1: Version-controlled prompt storage with diff support.

Stores prompts as versioned files with metadata, supports:
  - register: save a prompt with version + metadata
  - get: retrieve a specific version
  - diff: compare two versions
  - list: enumerate all prompts and versions
  - tag: mark a version as stable/production

Storage:
  /root/.hermes/state/prompts/<name>/<version>.md
  /root/.hermes/state/prompts/<name>/_meta.json (latest version, tags, history)

Usage:
  python3 prompt_registry.py register --name "deliver" --version v1 --content "..."
  python3 prompt_registry.py get --name "deliver" --version v1
  python3 prompt_registry.py diff --name "deliver" --from v1 --to v2
  python3 prompt_registry.py list [--name NAME]
  python3 prompt_registry.py tag --name "deliver" --version v1 --tag stable
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROMPTS_DIR = Path("/root/.hermes/state/prompts")


def _name_safe(name: str) -> str:
    """Make a name safe for filesystem."""
    return name.replace("/", "_").replace(" ", "_").lower()


def _meta_path(name: str) -> Path:
    return PROMPTS_DIR / _name_safe(name) / "_meta.json"


def _version_path(name: str, version: str) -> Path:
    return PROMPTS_DIR / _name_safe(name) / f"{version}.md"


def register(name: str, version: str, content: str, tag: str | None = None,
             notes: str | None = None) -> dict:
    """Register a new prompt version."""
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    prompt_dir = PROMPTS_DIR / _name_safe(name)
    prompt_dir.mkdir(parents=True, exist_ok=True)

    # Write the version file
    vp = _version_path(name, version)
    vp.write_text(content)

    # Update metadata
    meta_path = _meta_path(name)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    else:
        meta = {
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "versions": {},
            "tags": {},
        }

    now = datetime.now(timezone.utc).isoformat()
    meta["versions"][version] = {
        "registered_at": now,
        "size_bytes": len(content),
        "notes": notes,
    }
    if tag:
        meta["tags"][tag] = {"version": version, "tagged_at": now}
    meta["latest"] = version
    meta["updated_at"] = now
    meta_path.write_text(json.dumps(meta, indent=2))

    return {
        "name": name,
        "version": version,
        "size_bytes": len(content),
        "tag": tag,
        "path": str(vp),
    }


def get(name: str, version: str = "latest") -> dict:
    """Get a prompt version."""
    meta_path = _meta_path(name)
    if not meta_path.exists():
        return {"error": f"prompt '{name}' not found"}
    meta = json.loads(meta_path.read_text())

    if version == "latest":
        version = meta.get("latest")
        if not version:
            return {"error": f"no latest version for '{name}'"}
    elif version in meta.get("tags", {}):
        version = meta["tags"][version]["version"]

    if version not in meta.get("versions", {}):
        return {"error": f"version '{version}' not found for '{name}'"}

    vp = _version_path(name, version)
    if not vp.exists():
        return {"error": f"file missing: {vp}"}

    return {
        "name": name,
        "version": version,
        "content": vp.read_text(),
        "metadata": meta["versions"][version],
        "all_tags": meta.get("tags", {}),
    }


def diff_prompts(name: str, from_v: str, to_v: str) -> dict:
    """Show diff between two versions."""
    a = get(name, from_v)
    b = get(name, to_v)
    if "error" in a:
        return a
    if "error" in b:
        return b

    # Simple line-by-line diff
    import difflib
    a_lines = a["content"].splitlines(keepends=True)
    b_lines = b["content"].splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        a_lines, b_lines,
        fromfile=f"{name}:{from_v}", tofile=f"{name}:{to_v}",
        lineterm="",
    ))
    return {
        "name": name,
        "from": from_v,
        "to": to_v,
        "diff": "\n".join(diff) if diff else "(no changes)",
        "from_size": len(a["content"]),
        "to_size": len(b["content"]),
        "lines_added": sum(1 for line in diff if line.startswith("+") and not line.startswith("+++")),
        "lines_removed": sum(1 for line in diff if line.startswith("-") and not line.startswith("---")),
    }


def list_prompts(name: str | None = None) -> dict:
    """List all prompts or versions of one prompt."""
    if not PROMPTS_DIR.exists():
        return {"prompts": [], "total": 0}

    if name:
        meta_path = _meta_path(name)
        if not meta_path.exists():
            return {"error": f"prompt '{name}' not found"}
        meta = json.loads(meta_path.read_text())
        return {
            "name": name,
            "versions": list(meta.get("versions", {}).keys()),
            "latest": meta.get("latest"),
            "tags": meta.get("tags", {}),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
        }

    prompts = []
    for prompt_dir in sorted(PROMPTS_DIR.iterdir()):
        if not prompt_dir.is_dir():
            continue
        meta_path = prompt_dir / "_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            prompts.append({
                "name": meta.get("name"),
                "latest": meta.get("latest"),
                "version_count": len(meta.get("versions", {})),
                "tags": list(meta.get("tags", {}).keys()),
                "updated_at": meta.get("updated_at"),
            })
    return {"prompts": prompts, "total": len(prompts)}


def tag_prompt(name: str, version: str, tag: str) -> dict:
    """Tag a version."""
    return register(name, version, get(name, version).get("content", ""), tag=tag)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # register
    p_reg = sub.add_parser("register", help="Register a new prompt version")
    p_reg.add_argument("--name", required=True)
    p_reg.add_argument("--version", required=True)
    p_reg.add_argument("--content", help="Inline content (or use --file)")
    p_reg.add_argument("--file", help="Path to file with content")
    p_reg.add_argument("--tag", help="Optional tag (e.g., stable, prod)")
    p_reg.add_argument("--notes", help="Optional notes about this version")
    p_reg.add_argument("--json", action="store_true")

    # get
    p_get = sub.add_parser("get", help="Retrieve a prompt version")
    p_get.add_argument("--name", required=True)
    p_get.add_argument("--version", default="latest")
    p_get.add_argument("--json", action="store_true")

    # diff
    p_diff = sub.add_parser("diff", help="Diff two versions")
    p_diff.add_argument("--name", required=True)
    p_diff.add_argument("--from", dest="from_v", required=True)
    p_diff.add_argument("--to", dest="to_v", required=True)
    p_diff.add_argument("--json", action="store_true")

    # list
    p_list = sub.add_parser("list", help="List prompts")
    p_list.add_argument("--name", help="List versions of a specific prompt")
    p_list.add_argument("--json", action="store_true")

    # tag
    p_tag = sub.add_parser("tag", help="Tag a version")
    p_tag.add_argument("--name", required=True)
    p_tag.add_argument("--version", required=True)
    p_tag.add_argument("--tag", required=True)
    p_tag.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.cmd == "register":
        if args.file:
            content = Path(args.file).read_text()
        elif args.content:
            content = args.content
        else:
            print("Error: must provide --content or --file", file=sys.stderr)
            return 1
        result = register(args.name, args.version, content, args.tag, args.notes)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✓ Registered {args.name}:{args.version} ({result['size_bytes']} bytes)")
            if args.tag:
                print(f"  Tagged: {args.tag}")

    elif args.cmd == "get":
        result = get(args.name, args.version)
        if args.json:
            print(json.dumps(result, indent=2))
        elif "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1
        else:
            print(result["content"])

    elif args.cmd == "diff":
        result = diff_prompts(args.name, args.from_v, args.to_v)
        if args.json:
            print(json.dumps(result, indent=2))
        elif "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1
        else:
            print(f"Diff {result['name']}:{result['from']} → {result['to_v'] if hasattr(result, 'to_v') else result['to']}")
            print(f"  Lines added: {result['lines_added']}, removed: {result['lines_removed']}")
            print(f"  Size: {result['from_size']} → {result['to_size']} bytes")
            print(f"\n{result['diff']}")

    elif args.cmd == "list":
        result = list_prompts(args.name)
        if args.json:
            print(json.dumps(result, indent=2))
        elif "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1
        elif args.name:
            print(f"Prompt: {result['name']}")
            print(f"  Versions: {', '.join(result['versions'])}")
            print(f"  Latest: {result['latest']}")
            if result["tags"]:
                print(f"  Tags: {result['tags']}")
        else:
            print(f"Total prompts: {result['total']}")
            for p in result["prompts"]:
                tags_str = f" [{','.join(p['tags'])}]" if p["tags"] else ""
                print(f"  {p['name']} ({p['version_count']} versions, latest: {p['latest']}){tags_str}")

    elif args.cmd == "tag":
        # First get the content of the version
        existing = get(args.name, args.version)
        if "error" in existing:
            print(f"Error: {existing['error']}", file=sys.stderr)
            return 1
        result = tag_prompt(args.name, args.version, args.tag)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✓ Tagged {args.name}:{args.version} as '{args.tag}'")

    return 0


if __name__ == "__main__":
    sys.exit(main())
