#!/usr/bin/env python3
"""
swarm/examples/reflection_cycle.py — Reflection loop demo (Atlas C-2).

Demonstrates:
- Run 3 fake swarm runs with different outcomes (1 succeed, 1 retry-heavy, 1 clean)
- Extract lessons from each via reflection_loop.py
- Query the reflection log for patterns
- Show how future runs could use these lessons to avoid past mistakes

Usage:
    cd /root/ai-whisperers-ops-toolkit
    python3 swarm/examples/reflection_cycle.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from swarm.shared_memory import SharedMemory
from swarm.reflection_loop import ReflectionLog, extract_lessons_from_run


def make_fake_run(run_dir: Path, n_succeeded: int, n_failed: int,
                   n_retries: int, n_escalations: int) -> None:
    """Create a fake swarm run with the given outcome pattern."""
    mem = SharedMemory(run_dir)
    now_iso = "2026-08-03T12:00:00+00:00"
    mem.publish("plan", {"goal": f"test run in {run_dir.name}",
                          "subtasks": [], "metadata": {}})
    subtask_count = 1
    for i in range(n_succeeded):
        sid = f"task-{subtask_count}"
        mem.log("orchestrator", "orchestrator", "subtask_launched",
                {"id": sid, "role": "researcher", "worker_id": f"w-{sid}"})
        mem.log(f"w-{sid}", "researcher", "started", {"task": f"Task {sid}"})
        mem.log("orchestrator", "orchestrator", "subtask_finished",
                {"id": sid, "status": "succeeded", "worker_id": f"w-{sid}"})
        subtask_count += 1
    for i in range(n_failed):
        sid = f"task-{subtask_count}"
        mem.log("orchestrator", "orchestrator", "subtask_launched",
                {"id": sid, "role": "coder", "worker_id": f"w-{sid}"})
        mem.log(f"w-{sid}", "coder", "started", {"task": f"Task {sid}"})
        mem.log("orchestrator", "orchestrator", "subtask_finished",
                {"id": sid, "status": "failed", "worker_id": f"w-{sid}"})
        subtask_count += 1
    for i in range(n_retries):
        mem.log("orchestrator", "orchestrator", "retry_added", {"id": f"task-r{i}"})
    for i in range(n_escalations):
        mem.log("orchestrator", "orchestrator", "escalation_added",
                {"id": f"task-e{i}"})
    mem.log("orchestrator", "orchestrator", "plan_finished",
            {"succeeded": n_succeeded, "failed": n_failed, "skipped": 0})


def main():
    print("=== Atlas C-2: Reflection Loop Demo ===\n")

    # Use a temp file for the reflection log (not real ~/.hermes)
    tmp = Path(tempfile.mkdtemp(prefix="reflection_demo_"))
    log_path = tmp / "reflections.jsonl"
    log = ReflectionLog(log_path=log_path)

    # 3 fake runs with different patterns
    runs = [
        ("run-A-clean", make_fake_run(tmp / "run-A-clean",
                                      n_succeeded=5, n_failed=0,
                                      n_retries=0, n_escalations=0)),
        ("run-B-retry-heavy", make_fake_run(tmp / "run-B-retry-heavy",
                                           n_succeeded=3, n_failed=1,
                                           n_retries=4, n_escalations=1)),
        ("run-C-mostly-fail", make_fake_run(tmp / "run-C-mostly-fail",
                                           n_succeeded=1, n_failed=3,
                                           n_retries=2, n_escalations=2)),
    ]

    # Extract + add lessons from each
    total_lessons = 0
    for name, _ in runs:
        run_dir = tmp / name
        lessons = extract_lessons_from_run(run_dir)
        n = log.add(lessons)
        total_lessons += n
        print(f"  Run {name}: extracted {n} lessons")

    # Stats
    print(f"\n=== Reflection log stats ===")
    stats = log.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Query observations
    print(f"\n=== Pattern observations ===")
    observations = log.query(lesson_type="observation")
    for obs in observations:
        print(f"  - {obs.get('observation', '')}")

    # Query subtask outcomes
    print(f"\n=== Subtask outcomes (across all 3 runs) ===")
    outcomes = log.query(lesson_type="subtask_outcome", limit=20)
    print(f"  {len(outcomes)} total subtask_outcome lessons recorded")

    # Cleanup
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n✓ Reflection demo completed.")
    print(f"  Lessons learned across 3 runs: {stats['n_lessons']}")
    print(f"  Patterns detected: {len(observations)}")
    print(f"  These lessons can be queried by future runs to avoid repeating mistakes.")


if __name__ == "__main__":
    main()
