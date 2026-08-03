#!/usr/bin/env python3
"""
hermes-self-update-check.py — checks for new Hermes Agent releases.

Pattern from r/hermesagent "the cron every serious Hermes Agent user should have":
- Daily 8:30am
- Compares local install against origin/main
- Summarizes diff to Telegram (or local file if no Telegram)

Output format:
  📦 Hermes update check
  Current:  v0.16.0
  Latest:   v0.16.1
  Commits behind: 3
  Top changes:
    - fix: gateway timeout on long sessions
    - feat: skill bundles GA
    - perf: 30% faster tool loading
"""
import os
import subprocess
import datetime
import json

HERMES_HOME = os.path.expanduser("~/.hermes")
HERMES_AGENT_DIR = "/root/.hermes/hermes-agent"  # the canonical checkout
LOG_DIR = os.path.join(HERMES_HOME, "logs")
OUT_FILE = os.path.join(LOG_DIR, "hermes-update-check.log")


def get_local_version():
    """Read version from local checkout."""
    version_file = os.path.join(HERMES_AGENT_DIR, "VERSION")
    if os.path.exists(version_file):
        with open(version_file) as f:
            return f.read().strip()
    return "unknown"


def get_remote_version():
    """Try to fetch latest release tag from GitHub."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs",
             "https://github.com/NousResearch/hermes-agent.git"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            # Parse tags like: abc123 refs/tags/v0.16.1
            tags = []
            for line in result.stdout.strip().split("\n"):
                if "refs/tags/" in line:
                    tag = line.split("refs/tags/")[-1].strip()
                    if tag.startswith("v") and tag[1:].replace(".", "").isdigit():
                        tags.append(tag)
            if tags:
                # Sort by version
                tags.sort(key=lambda t: [int(x) for x in t.lstrip("v").split(".")])
                return tags[-1]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_commits_behind():
    """Count commits local is behind origin/main."""
    try:
        # First fetch
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=HERMES_AGENT_DIR, capture_output=True, timeout=30
        )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=HERMES_AGENT_DIR, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def get_top_changes(limit=5):
    """Get the most recent commit messages from origin/main not in HEAD."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "HEAD..origin/main", f"-{limit}"],
            cwd=HERMES_AGENT_DIR, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def main():
    os.makedirs(LOG_DIR, exist_ok=True)

    local = get_local_version()
    remote = get_remote_version()
    behind = get_commits_behind()
    changes = get_top_changes(5)

    lines = [
        f"📦 Hermes update check — {datetime.datetime.now().isoformat()}",
        f"  Current: {local}",
        f"  Latest:  {remote or 'unable to fetch'}",
    ]

    if behind is not None:
        lines.append(f"  Commits behind: {behind}")
        if changes:
            lines.append("  Top changes:")
            for c in changes:
                lines.append(f"    - {c}")
    else:
        lines.append("  Commits behind: unable to determine")

    output = "\n".join(lines)

    # Always log to file
    with open(OUT_FILE, "a") as f:
        f.write(output + "\n\n")

    # Print to stdout (cron job will deliver based on its delivery target)
    print(output)

    # Non-zero exit if there are updates (so cron delivery flags it)
    if behind and behind > 0:
        return 0  # Updates available, but we did the work
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
