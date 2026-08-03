#!/usr/bin/env python3
"""
sync_hermes_config.py — Sync ~/.hermes/ scripts/state into hermes-config repo.

After editing scripts in ~/.hermes/, this script:
1. Copies the changed files into /root/hermes-config/
2. Stages them
3. Commits with a generated message

Usage:
    python3 ~/.hermes/scripts/sync_hermes_config.py --message "fix: ..."
    python3 ~/.hermes/scripts/sync_hermes_config.py --auto  # auto-commit with timestamp

Cron: optional weekly.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
CONFIG_REPO = Path("/root/hermes-config")
SCRIPTS_SRC = HERMES_HOME / "scripts"
SCRIPTS_DST = CONFIG_REPO / "scripts"
STATE_SRC = HERMES_HOME / "state"
STATE_DST = CONFIG_REPO / "state"
DOCS_SRC = HERMES_HOME / "inbox"
DOCS_DST = CONFIG_REPO / "docs"
COLL_SRC = HERMES_HOME / "skills" / "collections"
COLL_DST = CONFIG_REPO / "skills" / "collections"


SYNC_FILES = {
    "scripts": {
        "src": SCRIPTS_SRC,
        "dst": SCRIPTS_DST,
        "files": [
            "repo_tick.py", "pipeline_run.py", "cron_orchestrator.py",
            "repo_dashboard.py", "auto_remediate.py", "skill_usage_tracker.py",
            "snapshot_diff.py", "migrate_skills.py", "new_project.py",
            "kanban_orchestrator.py", "regression_alert.py", "dashboard_server.py",
            "validate_skill_frontmatter.py", "validate_collections.py",
            "file_mask_router.py", "pre_merge_check.py",
            "find_extraction_candidates.py", "find_condense_candidates.py",
            "find_script_extraction_candidates.py",
        ],
    },
    "state": {
        "src": STATE_SRC,
        "dst": STATE_DST,
        "files": ["projects.yaml"],
    },
    "docs": {
        "src": DOCS_SRC,
        "dst": DOCS_DST,
        "files": [
            "cursor-loop-integration.md",
            "cursor-loop-integration-round3.md",
            "cursor-loop-integration-round4.md",
            "cursor-loop-v2-full-audit.md",
            "cursor-loop-round5-autonomous-plan.md",
            "cursor-loop-round5-shipping.md",
            "cursor-loop-gold-i-missed.md",
        ],
    },
    "collections": {
        "src": COLL_SRC,
        "dst": COLL_DST,
        "files": None,  # entire dir
    },
}


def sync_files(category: str) -> list[str]:
    """Sync one category. Returns list of files synced."""
    config = SYNC_FILES[category]
    src = config["src"]
    dst = config["dst"]
    synced = []
    if config["files"] is None:
        # Directory sync
        if not src.exists():
            return []
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and f.name.endswith(".yml"):
                shutil.copy(f, dst / f.name)
                synced.append(f"{category}/{f.name}")
    else:
        for fname in config["files"]:
            f_src = src / fname
            if not f_src.exists():
                continue
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy(f_src, dst / fname)
            synced.append(f"{category}/{fname}")
    return synced


def git_commit(message: str, push: bool = False) -> dict:
    """Stage + commit + optionally push."""
    try:
        # Stage
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd=CONFIG_REPO, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"status": "git-add-failed", "stderr": result.stderr[-500:]}
        # Check if there are changes
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=CONFIG_REPO, capture_output=True, text=True, timeout=30,
        )
        if not diff_result.stdout.strip():
            return {"status": "no-changes"}
        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=CONFIG_REPO, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"status": "git-commit-failed", "stderr": result.stderr[-500:]}
        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=CONFIG_REPO, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        out = {"status": "committed", "sha": commit_sha[:8]}
        if push:
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=CONFIG_REPO, capture_output=True, text=True, timeout=60,
            )
            out["push_status"] = "ok" if push_result.returncode == 0 else "failed"
            out["push_stderr"] = push_result.stderr[-500:]
        return out
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync ~/.hermes into hermes-config repo")
    parser.add_argument("--message", help="Commit message")
    parser.add_argument("--auto", action="store_true", help="Auto-commit with timestamp")
    parser.add_argument("--push", action="store_true", help="Also push to origin")
    parser.add_argument("--dry-run", action="store_true", help="Sync files but don't commit")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not args.message and not args.auto:
        args.message = input("Commit message: ").strip()
    if args.auto or not args.message:
        args.message = f"chore: auto-sync from ~/.hermes/ at {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"

    all_synced = []
    for category in SYNC_FILES:
        synced = sync_files(category)
        all_synced.extend(synced)

    if args.dry_run:
        result = {"status": "dry-run", "files_synced": len(all_synced), "files": all_synced}
    else:
        result = git_commit(args.message, push=args.push)
        result["files_synced"] = len(all_synced)
        result["files"] = all_synced

    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print(f"\n=== Hermes Config Sync ===")
        print(f"  Files synced: {len(all_synced)}")
        for f in all_synced[:10]:
            print(f"    • {f}")
        if len(all_synced) > 10:
            print(f"    ... +{len(all_synced) - 10} more")
        print(f"\n  Status: {result.get('status')}")
        if result.get("sha"):
            print(f"  SHA: {result.get('sha')}")
        if result.get("push_status"):
            print(f"  Push: {result.get('push_status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())