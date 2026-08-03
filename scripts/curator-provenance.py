#!/usr/bin/env python3
"""curator-provenance.py — record provenance for curator skill changes.

Pattern from r/hermesagent "local-first Hermes plugin that evolves skills" thread:
  "collect local session/tool-call evidence, detect which skills may be stale or
   worth improving, generate dry-run proposals and evidence reports, apply only
   guarded, append-only updates, keep provenance, backups, and rollback manifests"
"""
import os
import json
import datetime
import sys

HERMES_HOME = os.path.expanduser("~/.hermes")
LOG_FILE = os.path.join(HERMES_HOME, "logs/curator-provenance.log")
SNAPSHOT_DIR = os.path.join(HERMES_HOME, "backups")


def record_change(action, skill_name, reason, snapshot_id=None, evidence=None):
    """Record a single provenance entry."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    entry = {
        "ts": datetime.datetime.now().isoformat(),
        "action": action,  # archive, consolidate, prune, restore
        "skill": skill_name,
        "reason": reason,
        "snapshot_id": snapshot_id,
        "evidence": evidence or {},
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"  recorded: {action} {skill_name}")


def latest_snapshot():
    """Return the most recent curator snapshot ID."""
    if not os.path.isdir(SNAPSHOT_DIR):
        return None
    snaps = sorted(
        [d for d in os.listdir(SNAPSHOT_DIR) if d.startswith("snapshot-")],
        reverse=True
    )
    return snaps[0] if snaps else None


def main():
    if len(sys.argv) < 4:
        print("Usage: curator-provenance.py <action> <skill> <reason> [evidence_json]")
        print("  action: archive | consolidate | prune | restore | pin")
        print("  skill:  skill name")
        print("  reason: short reason (e.g. 'idle 90d, 0 activity')")
        sys.exit(1)

    action = sys.argv[1]
    skill = sys.argv[2]
    reason = sys.argv[3]
    evidence = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}

    record_change(action, skill, reason, latest_snapshot(), evidence)


if __name__ == "__main__":
    main()
