#!/usr/bin/env python3
"""
swarm/shared_memory.py — Cross-agent state via append-only JSONL log + named snapshots.

Workers and the orchestrator share state through:
1. **Append-only log** (`memory.jsonl`): every state-changing event, never deleted
2. **Named snapshots** (`snapshots/<name>.json`): structured state for fast lookup
3. **Blackboard** (`blackboard/<key>`): free-form text/JSON keys for ad-hoc sharing

The pattern is intentionally simple: no database, no Redis, just JSON files. This makes
the swarm debuggable from any agent (just `cat memory.jsonl`).

Why this design:
- **Append-only log**: durable history, can replay any worker's actions
- **Named snapshots**: workers can publish results other workers need
- **Blackboard keys**: shared scratch space for cross-agent context

Example usage:
    memory = SharedMemory("/tmp/swarm-state/run-123")
    memory.log("worker-1", "researcher", "started")
    memory.publish("research-1", {"findings": [...]})
    memory.write_blackboard("todo", "fix the bug in worker.py")
    memory.read_blackboard("todo")
    memory.snapshot("final-result", {"ok": True})
"""

import json
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class SharedMemory:
    """File-backed shared state for an agent swarm."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.log_path = self.base_dir / "memory.jsonl"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.blackboard_dir = self.base_dir / "blackboard"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)
        self.blackboard_dir.mkdir(exist_ok=True)
        # Ensure log file exists
        if not self.log_path.exists():
            self.log_path.touch()

    # ---- Append-only log ----

    def log(
        self,
        agent_id: str,
        role: str,
        event: str,
        payload: Optional[dict] = None,
    ) -> None:
        """Append an event to the memory log. Thread-safe via file lock."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "role": role,
            "event": event,
            "payload": payload or {},
        }
        with open(self.log_path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read_log(
        self,
        since: Optional[str] = None,
        agent_id: Optional[str] = None,
        role: Optional[str] = None,
        event: Optional[str] = None,
    ) -> list[dict]:
        """Read log entries with optional filters."""
        entries = []
        if not self.log_path.exists():
            return entries
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if since and entry.get("ts", "") < since:
                    continue
                if agent_id and entry.get("agent_id") != agent_id:
                    continue
                if role and entry.get("role") != role:
                    continue
                if event and entry.get("event") != event:
                    continue
                entries.append(entry)
        return entries

    # ---- Named snapshots ----

    def publish(self, name: str, data: Any) -> None:
        """Publish a named snapshot for other workers to read."""
        path = self.snapshots_dir / f"{name}.json"
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "name": name,
            "data": data,
        }
        # Atomic write
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(payload, f, indent=2, default=str)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        tmp.replace(path)

    def read(self, name: str) -> Optional[Any]:
        """Read a named snapshot. Returns None if not found."""
        path = self.snapshots_dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                payload = json.load(f)
            return payload.get("data")
        except (json.JSONDecodeError, OSError):
            return None

    def list_snapshots(self) -> list[str]:
        """List all available snapshot names."""
        return sorted(p.stem for p in self.snapshots_dir.glob("*.json"))

    # ---- Blackboard keys ----

    def write_blackboard(self, key: str, value: Any) -> None:
        """Write a free-form value to the blackboard."""
        path = self.blackboard_dir / self._safe_key(key)
        if isinstance(value, str):
            path.write_text(value)
        else:
            path.write_text(json.dumps(value, indent=2, default=str))

    def read_blackboard(self, key: str) -> Optional[Any]:
        """Read a blackboard key."""
        path = self.blackboard_dir / self._safe_key(key)
        if not path.exists():
            return None
        text: str = ""
        try:
            text = path.read_text()
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text

    def list_blackboard_keys(self) -> list[str]:
        """List all blackboard keys."""
        return sorted(p.name for p in self.blackboard_dir.iterdir() if p.is_file())

    def delete_blackboard(self, key: str) -> None:
        """Delete a blackboard key."""
        path = self.blackboard_dir / self._safe_key(key)
        if path.exists():
            path.unlink()

    @staticmethod
    def _safe_key(key: str) -> str:
        """Make a key filesystem-safe."""
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in key)

    # ---- Status / introspection ----

    def status(self) -> dict:
        """Get current memory status for the orchestrator."""
        log_entries = self.read_log()
        return {
            "base_dir": str(self.base_dir),
            "log_entries": len(log_entries),
            "snapshots": self.list_snapshots(),
            "blackboard_keys": self.list_blackboard_keys(),
            "first_entry": log_entries[0] if log_entries else None,
            "last_entry": log_entries[-1] if log_entries else None,
        }


def main():
    """CLI: manage shared memory from the command line."""
    import argparse

    p = argparse.ArgumentParser(description="Swarm shared memory CLI")
    p.add_argument("--dir", default="/tmp/swarm-state/default",
                   help="Base directory for this swarm run")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_log = sub.add_parser("log", help="Append an event")
    p_log.add_argument("--agent", required=True)
    p_log.add_argument("--role", required=True)
    p_log.add_argument("--event", required=True)
    p_log.add_argument("--payload", help="JSON payload")

    p_pub = sub.add_parser("publish", help="Publish a named snapshot")
    p_pub.add_argument("--name", required=True)
    p_pub.add_argument("--data", required=True, help="JSON data")

    p_read = sub.add_parser("read", help="Read a named snapshot")
    p_read.add_argument("--name", required=True)

    p_bb = sub.add_parser("blackboard-write", help="Write to blackboard")
    p_bb.add_argument("--key", required=True)
    p_bb.add_argument("--value", required=True)

    p_bbr = sub.add_parser("blackboard-read", help="Read from blackboard")
    p_bbr.add_argument("--key", required=True)

    sub.add_parser("status", help="Print memory status")
    sub.add_parser("snapshots", help="List snapshots")
    sub.add_parser("blackboard", help="List blackboard keys")

    args = p.parse_args()
    mem = SharedMemory(args.dir)

    if args.cmd == "log":
        payload = json.loads(args.payload) if args.payload else None
        mem.log(args.agent, args.role, args.event, payload)
    elif args.cmd == "publish":
        mem.publish(args.name, json.loads(args.data))
    elif args.cmd == "read":
        data = mem.read(args.name)
        print(json.dumps(data, indent=2, default=str) if data else "(not found)")
    elif args.cmd == "blackboard-write":
        mem.write_blackboard(args.key, args.value)
    elif args.cmd == "blackboard-read":
        val = mem.read_blackboard(args.key)
        print(val if val is not None else "(not found)")
    elif args.cmd == "status":
        print(json.dumps(mem.status(), indent=2, default=str))
    elif args.cmd == "snapshots":
        for name in mem.list_snapshots():
            print(name)
    elif args.cmd == "blackboard":
        for key in mem.list_blackboard_keys():
            print(key)


if __name__ == "__main__":
    main()