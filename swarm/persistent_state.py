#!/usr/bin/env python3
"""
swarm/persistent_state.py — Save + load swarm plan state to/from disk.

A persistent state lets you:
- Resume an interrupted swarm run (crash, Ctrl-C, OOM, timeout)
- Audit completed swarms (review what each worker did)
- Clone a running swarm to fork the work
- Migrate runs across hosts (state is just JSON files)

The state includes:
- The full Plan (subtasks, dependencies, status)
- All retry/escalation history
- Worker cost records
- Orchestrator metadata

Usage:
    from persistent_state import PersistentState
    state = PersistentState("/tmp/swarm-state/run-123")
    state.save(plan)
    plan = state.load()
    if state.is_interrupted():
        plan = state.resume()
"""

import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared_memory import SharedMemory  # noqa: E402

# Import Plan/SubTask only for type hints (avoid circular import)
if __name__ == "__main__":
    from orchestrator import Plan, SubTask  # noqa: E402


STATE_FILENAME = "plan-state.json"
SCHEMA_VERSION = 1


def _subtask_to_dict(subtask) -> dict:
    """Serialize a SubTask (avoiding dataclasses issues with timestamp fields)."""
    return {
        "id": subtask.id,
        "role": subtask.role,
        "description": subtask.description,
        "depends_on": list(subtask.depends_on),
        "extra_context": subtask.extra_context,
        "timeout": subtask.timeout,
        "model": subtask.model,
        "status": subtask.status.value if hasattr(subtask.status, "value") else str(subtask.status),
        "worker_id": subtask.worker_id,
        "started_at": subtask.started_at,
        "finished_at": subtask.finished_at,
        "result": subtask.result,
        "failure_reason": getattr(subtask, "failure_reason", None),
    }


def _subtask_from_dict(data: dict):
    """Reconstruct a SubTask from a dict."""
    from orchestrator import Plan, SubTask, TaskStatus
    return SubTask(
        id=data["id"],
        role=data["role"],
        description=data["description"],
        depends_on=data.get("depends_on", []),
        extra_context=data.get("extra_context"),
        timeout=data.get("timeout", 300),
        model=data.get("model", "haiku"),
        status=TaskStatus(data.get("status", "pending")),
        worker_id=data.get("worker_id"),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        result=data.get("result"),
    )


class PersistentState:
    """Manages a swarm plan's persistent state on disk."""

    def __init__(self, memory_dir: str | Path):
        self.memory = SharedMemory(memory_dir)
        self.memory_dir = Path(memory_dir)
        self.state_path = self.memory_dir / STATE_FILENAME
        self.lock_path = self.memory_dir / f"{STATE_FILENAME}.lock"

    def exists(self) -> bool:
        return self.state_path.exists()

    def save(self, plan) -> None:
        """Save the current plan + metadata to disk. Atomic write."""
        data = {
            "schema_version": SCHEMA_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "goal": plan.goal,
            "metadata": dict(plan.metadata),
            "subtasks": [_subtask_to_dict(s) for s in plan.subtasks],
        }
        # Atomic write via temp file
        tmp = self.state_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.replace(self.state_path)
        self.memory.log(
            "persistent_state", "state_manager", "state_saved",
            {"path": str(self.state_path), "n_subtasks": len(data["subtasks"])},
        )

    def load(self):
        """Load a plan from disk. Raises FileNotFoundError if no state."""
        with open(self.state_path) as f:
            data = json.load(f)
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"State schema version {data.get('schema_version')} "
                f"does not match current {SCHEMA_VERSION}"
            )
        from orchestrator import Plan
        plan = Plan(
            goal=data["goal"],
            subtasks=[_subtask_from_dict(s) for s in data["subtasks"]],
            metadata=data.get("metadata", {}),
        )
        plan.metadata["loaded_at"] = datetime.now(timezone.utc).isoformat()
        plan.metadata["original_saved_at"] = data.get("saved_at", "")
        return plan

    def is_interrupted(self) -> bool:
        """Check if a previous run was interrupted (not cleanly completed)."""
        if not self.exists():
            return False
        try:
            plan = self.load()
            # If plan has any running subtasks, it was interrupted
            from orchestrator import TaskStatus
            if any(s.status == TaskStatus.RUNNING for s in plan.subtasks):
                return True
            # Or if plan is incomplete (any pending subtasks but plan isn't marked complete)
            if plan.metadata.get("finished_at"):
                return False  # Cleanly finished
            pending = sum(1 for s in plan.subtasks if s.status == TaskStatus.PENDING)
            failed = sum(1 for s in plan.subtasks if s.status == TaskStatus.FAILED)
            return pending > 0 or failed > 0
        except (FileNotFoundError, ValueError, KeyError):
            return False

    def get_status_summary(self) -> dict:
        """Quick status check without full deserialization (for huge plans)."""
        if not self.exists():
            return {"exists": False}
        with open(self.state_path) as f:
            data = json.load(f)
        from collections import Counter
        statuses = Counter()
        for s in data.get("subtasks", []):
            statuses[s.get("status", "pending")] += 1
        return {
            "exists": True,
            "schema_version": data.get("schema_version"),
            "saved_at": data.get("saved_at"),
            "goal": data.get("goal"),
            "n_subtasks": len(data.get("subtasks", [])),
            "by_status": dict(statuses),
            "metadata": data.get("metadata", {}),
        }

    def cleanup(self) -> None:
        """Delete persistent state (call after a clean run completes)."""
        if self.state_path.exists():
            self.state_path.unlink()
        if self.lock_path.exists():
            self.lock_path.unlink()

    def archive(self, destination: str | Path) -> Path:
        """Move state to a different location (keeps history)."""
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists():
            dest.write_bytes(self.state_path.read_bytes())
            self.state_path.unlink()
        return dest


def main():
    """CLI: inspect / save / load / cleanup persistent state."""
    import argparse
    p = argparse.ArgumentParser(description="Manage persistent swarm state")
    p.add_argument("--memory-dir", required=True)
    sub = p.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="Print status summary (no full load)")
    sub.add_parser("exists", help="Exit 0 if state file exists")
    p_cleanup = sub.add_parser("cleanup", help="Delete state file")
    p_cleanup.add_argument("--yes", action="store_true")
    p_list = sub.add_parser("list-runs", help="List all swarm runs with state")

    args = p.parse_args()
    state = PersistentState(args.memory_dir)

    if args.cmd == "status":
        print(json.dumps(state.get_status_summary(), indent=2))
    elif args.cmd == "exists":
        return 0 if state.exists() else 1
    elif args.cmd == "cleanup":
        if not args.yes:
            print("Refusing to cleanup without --yes")
            return 1
        state.cleanup()
        print(f"✓ Cleaned up {args.memory_dir}")
    elif args.cmd == "list-runs":
        base = Path("/tmp/swarm-state")
        if not base.exists():
            return
        for d in sorted(base.glob("run-*")):
            summary = PersistentState(d).get_status_summary()
            if summary["exists"]:
                print(f"\n{d.name}")
                print(f"  goal: {summary['goal']}")
                print(f"  saved: {summary['saved_at']}")
                print(f"  statuses: {summary['by_status']}")


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
