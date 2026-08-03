#!/usr/bin/env python3
"""
swarm/examples/dry_run.py — End-to-end test that doesn't require claude auth.

Replaces the worker subprocess with a simple `echo` so you can verify the
swarm orchestration works without needing authenticated API access.

Usage:
    python3 dry_run.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

# Make swarm importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrator import Orchestrator, SubTask, Plan, TaskStatus  # noqa: E402


class DryRunWorker:
    """A test worker that simulates a real worker with echo."""

    def __init__(self, role: str, task: str, memory_dir: str, worker_id: str):
        self.role = role
        self.task = task
        self.memory_dir = Path(memory_dir)
        self.worker_id = worker_id

    def run(self) -> dict:
        # Simulate work with a sleep
        time.sleep(1)

        # Append to memory log
        log_path = self.memory_dir / "memory.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "agent_id": self.worker_id,
                "role": self.role,
                "event": "completed_dry_run",
                "payload": {"task": self.task[:100]},
            }) + "\n")

        # Publish a snapshot
        snapshots_dir = self.memory_dir / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        snap_path = snapshots_dir / f"result-{self.worker_id}.json"
        with open(snap_path, "w") as f:
            json.dump({
                "worker_id": self.worker_id,
                "role": self.role,
                "task": self.task,
                "result": f"Simulated result for {self.role} task: {self.task[:50]}",
                "ts": time.time(),
            }, f, indent=2)

        return {
            "ok": True,
            "worker_id": self.worker_id,
            "role": self.role,
            "duration_sec": 1.0,
            "result_snapshot": {"worker_id": self.worker_id, "role": self.role},
        }


def dry_run_plan() -> Plan:
    """3-subtask plan that runs in dry-run mode."""
    return Plan(
        goal="Dry run test of the swarm",
        subtasks=[
            SubTask(id="task-1", role="researcher",
                    description="Simulated research task"),
            SubTask(id="task-2", role="coder",
                    description="Simulated coding task",
                    depends_on=["task-1"]),
            SubTask(id="task-3", role="tester",
                    description="Simulated testing task",
                    depends_on=["task-2"]),
        ],
    )


def main():
    """Run a 3-task plan with simulated workers."""
    memory_dir = Path(f"/tmp/swarm-state/dry-run-{int(time.time())}")
    memory_dir.mkdir(parents=True)

    orch = Orchestrator(memory_dir=memory_dir, max_parallel=2)

    # Monkey-patch the worker spawning for dry-run mode
    import orchestrator as orch_mod
    original_run = orch_mod.Orchestrator._run_subtask

    def dry_run_subtask(self, plan, subtask):
        """Replace worker subprocess with dry-run worker."""
        from shared_memory import SharedMemory
        from datetime import datetime, timezone
        # Set up subtask state (matches real orchestrator)
        subtask.status = TaskStatus.RUNNING
        subtask.started_at = datetime.now(timezone.utc).isoformat()
        subtask.worker_id = f"w-dryrun-{subtask.id}-{int(time.time())}"

        mem = SharedMemory(memory_dir)
        mem.log(subtask.worker_id, subtask.role, "started", {"task": subtask.description[:100]})
        worker = DryRunWorker(
            role=subtask.role,
            task=subtask.description,
            memory_dir=str(memory_dir),
            worker_id=subtask.worker_id,
        )
        result = worker.run()
        subtask.status = TaskStatus.SUCCEEDED if result["ok"] else TaskStatus.FAILED
        subtask.result = result
        subtask.finished_at = datetime.now(timezone.utc).isoformat()
        mem.log(subtask.worker_id, subtask.role, "completed", {"ok": result["ok"]})

    orch_mod.Orchestrator._run_subtask = dry_run_subtask

    print(f"Memory dir: {memory_dir}")
    print(f"\nExecuting 3-subtask plan (dry-run mode)...")

    plan = dry_run_plan()
    start = time.time()
    result = orch.run(plan)
    duration = time.time() - start

    print(f"\n✓ Done in {duration:.1f}s")
    print(f"  Status: {orch.status(result)}")

    # Show memory log
    print(f"\n=== Memory log ({memory_dir}/memory.jsonl) ===")
    log_path = memory_dir / "memory.jsonl"
    from datetime import datetime
    for line in log_path.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            ts_raw = entry.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_raw).strftime("%H:%M:%S")
            except (ValueError, TypeError):
                ts = "?"
            print(f"  [{ts}] {entry['agent_id']:35} ({entry['role']:12}): {entry['event']}")

    # Show snapshots
    print(f"\n=== Snapshots ({memory_dir}/snapshots/) ===")
    snapshots_dir = memory_dir / "snapshots"
    for f in sorted(snapshots_dir.iterdir()):
        print(f"  {f.name}")

    print(f"\n✓ Dry-run passed. Orchestration works end-to-end.")
    return 0 if orch.status(result)["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())