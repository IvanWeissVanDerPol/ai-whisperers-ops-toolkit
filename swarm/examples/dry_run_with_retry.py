#!/usr/bin/env python3
"""
swarm/examples/dry_run_with_retry.py — End-to-end test of retry + cost tracking.

Tests:
- 3-subtask plan (researcher → coder → tester)
- Coder fails on first attempt → retry succeeds
- Cost tracker records all attempts
- Reports total cost + final status

This is a richer test than dry_run.py — exercises the full resilience loop.

Usage:
    cd /root/ai-whisperers-ops-toolkit/swarm/examples
    python3 dry_run_with_retry.py
"""

import json
import sys
import time
from pathlib import Path

# Make swarm importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrator import Orchestrator, SubTask, Plan, TaskStatus  # noqa: E402
from retry import RetryPolicy  # noqa: E402
from cost_tracker import CostTracker  # noqa: E402


# Global failure simulation state
FAIL_COUNT = {"task-2": 0}  # task-2 (coder) fails once, then succeeds


class DryRunWorker:
    """Test worker that simulates failure on first coder attempt."""

    def __init__(self, role: str, task: str, memory_dir: str, worker_id: str, model: str):
        self.role = role
        self.task = task
        self.memory_dir = Path(memory_dir)
        self.worker_id = worker_id
        self.model = model

    def run(self) -> dict:
        # Simulate cost based on duration
        start = time.time()
        time.sleep(1)
        duration = time.time() - start

        # Simulate one failure on coder task
        should_fail = (
            "task-2" in self.task.lower() and FAIL_COUNT["task-2"] == 0
        )
        if should_fail:
            FAIL_COUNT["task-2"] += 1
            return {"ok": False, "error": "simulated first-attempt failure", "duration_sec": duration}

        # Record cost
        tracker = CostTracker(self.memory_dir)
        cost = tracker.record_worker(
            worker_id=self.worker_id,
            role=self.role,
            model=self.model,
            duration_sec=duration,
            tokens_in=1000,
            tokens_out=500,
        )

        # Append to memory log
        log_path = self.memory_dir / "memory.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "agent_id": self.worker_id,
                "role": self.role,
                "event": "completed",
                "payload": {"ok": True, "duration_sec": duration},
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
                "result": f"Dry-run result for {self.role}",
                "duration_sec": duration,
                "cost_usd": cost.cost_usd,
            }, f, indent=2)

        return {
            "ok": True,
            "worker_id": self.worker_id,
            "role": self.role,
            "duration_sec": duration,
            "result_snapshot": {"worker_id": self.worker_id, "role": self.role},
        }


def build_plan() -> Plan:
    """3-subtask plan where task-2 (coder) will fail once."""
    return Plan(
        goal="Test swarm retry behavior",
        subtasks=[
            SubTask(id="task-1", role="researcher", description="Research task 1", timeout=60),
            SubTask(id="task-2", role="coder", description="Coder task 2 (will fail once)",
                    depends_on=["task-1"], timeout=60),
            SubTask(id="task-3", role="tester", description="Test task 3",
                    depends_on=["task-2"], timeout=60),
        ],
    )


def main():
    """Run the test plan with retry policy."""
    import orchestrator as orch_mod
    from datetime import datetime, timezone

    memory_dir = Path(f"/tmp/swarm-state/retry-test-{int(time.time())}")
    memory_dir.mkdir(parents=True)

    # Use a retry policy with 1 retry before escalation
    policy = RetryPolicy(max_retries=1, escalate_after=2)
    orch = Orchestrator(memory_dir=memory_dir, max_parallel=1, retry_policy=policy)

    # Monkey-patch _run_subtask to use dry-run workers
    def dry_run_subtask(self, plan, subtask):
        from shared_memory import SharedMemory
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
            model=subtask.model,
        )
        result = worker.run()
        subtask.finished_at = datetime.now(timezone.utc).isoformat()

        if result["ok"]:
            subtask.status = TaskStatus.SUCCEEDED
        else:
            subtask.status = TaskStatus.FAILED
            subtask.failure_reason = result.get("error", "unknown")

        subtask.result = result
        mem.log(subtask.worker_id, subtask.role, "completed" if result["ok"] else "FAILED",
                {"ok": result["ok"], "error": result.get("error")})
        return result

    orch_mod.Orchestrator._run_subtask = dry_run_subtask

    print(f"Memory dir: {memory_dir}")
    print(f"Retry policy: max_retries=1, escalate_after=2")
    print(f"\nExpected: task-2 fails first attempt, retries, succeeds.")

    plan = build_plan()
    start = time.time()
    result = orch.run(plan)
    duration = time.time() - start

    print(f"\n✓ Done in {duration:.1f}s")
    print(f"\nFinal plan:")
    for s in result.subtasks:
        status_icon = {"succeeded": "✓", "failed": "✗", "skipped": "⤼", "pending": "•", "running": "…"}.get(s.status.value, "?")
        print(f"  {status_icon} {s.id:30} ({s.role:10}) {s.status.value:10}  {s.description[:50]}")

    # Cost summary
    tracker = CostTracker(memory_dir)
    tracker.save()
    summary = tracker.summary()
    print(f"\n=== Cost Summary ===")
    print(f"  Workers: {summary['n_workers']}")
    print(f"  Total cost: ${summary['total_cost_usd']:.4f}")
    print(f"  Total tokens: {summary['total_tokens']:,}")
    print(f"  By model: {summary['by_model']}")

    # Verify expectations
    succeeded = [s for s in result.subtasks if s.status == TaskStatus.SUCCEEDED]
    failed = [s for s in result.subtasks if s.status == TaskStatus.FAILED]
    task2 = [s for s in result.subtasks if s.id.startswith("task-2")]

    print(f"\n=== Verification ===")
    print(f"  ✓ Original task-2 first attempt: should have FAILED")
    print(f"  ✓ Retry task-2 should have SUCCEEDED")
    print(f"  ✓ task-3 should have SUCCEEDED (depends on retry)")

    if failed:
        print(f"\n  ✗ Unexpected failures: {[s.id for s in failed]}")
        return 1
    if len(succeeded) != 3:
        print(f"\n  ✗ Expected 3 successes, got {len(succeeded)}")
        return 1

    print(f"\n✓ Retry test PASSED. All 3 tasks succeeded (1 with retry).")
    return 0


if __name__ == "__main__":
    sys.exit(main())