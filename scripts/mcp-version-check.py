#!/usr/bin/env python3
"""
MCP Version Monitor — runs weekly.

Reads the pinned versions from config.yaml, checks npm for newer versions,
reports any that have updates available.
"""
import os
import re
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

CONFIG_PATH = "/root/.hermes/config.yaml"
STATE_PATH = "/root/.hermes/state/mcp-version-state.json"


def get_pinned_versions():
    with open(CONFIG_PATH) as f:
        cfg = f.read()
    # Match patterns like '- '@org/pkg@1.2.3''
    pinned = re.findall(r"'(@?[\w/-]+)@([\d\.]+)'", cfg)
    return {pkg: ver for pkg, ver in pinned}


def get_latest_version(pkg):
    """Query npm registry for the latest version. Uses metadata endpoint to handle malformed latest responses."""
    # Use abbreviated metadata to avoid the common JSON parse errors
    url = f"https://registry.npmjs.org/{pkg}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(50000)
        # Manual parse to find "dist-tags":{"latest":"x.y.z"}
        m = re.search(rb'"dist-tags"\s*:\s*\{[^}]*"latest"\s*:\s*"([^"]+)"', raw)
        if m:
            return m.group(1).decode("utf-8", errors="replace")
        # Fallback: try parsing JSON
        try:
            data = json.loads(raw)
            return data.get("dist-tags", {}).get("latest", "?")
        except json.JSONDecodeError:
            return "ERR:parse"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except Exception as e:
        return f"ERR:{str(e)[:30]}"


def parse_version(v):
    """Return tuple of ints for comparison. '?' or non-numeric → (0,)."""
    if v == "?" or "ERR" in v or "HTTP" in v:
        return (0,)
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) if parts else (0,)


def main():
    pinned = get_pinned_versions()
    if not pinned:
        print("✅ MCP version monitor: no pinned packages found in config")
        return 0

    outdated = []
    unknown = []
    ok = []

    for pkg, current in pinned.items():
        latest = get_latest_version(pkg)
        if "ERR" in latest or "HTTP" in latest:
            unknown.append(f"{pkg}: current={current}, latest=? ({latest})")
        elif parse_version(latest) > parse_version(current):
            outdated.append(f"{pkg}: {current} → {latest}")
        else:
            ok.append(f"{pkg}: {current} (current)")

    # Save state
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    state = {
        "last_run": datetime.now().isoformat(),
        "pinned_count": len(pinned),
        "outdated": outdated,
        "ok": ok,
    }
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

    # Report
    lines = [f"📦 MCP version check — {len(pinned)} pinned"]
    if outdated:
        lines.append(f"\n⚠️ OUTDATED ({len(outdated)}):")
        for o in outdated:
            lines.append(f"  • {o}")
    if unknown:
        lines.append(f"\n❓ UNKNOWN ({len(unknown)}):")
        for u in unknown:
            lines.append(f"  • {u}")
    if ok and not outdated:
        lines.append(f"✅ All {len(ok)} packages up to date")

    output = "\n".join(lines)
    print(output)
    # Exit 0 even with outdated, so cron doesn't alert
    return 0


if __name__ == "__main__":
    sys.exit(main())
