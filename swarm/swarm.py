#!/usr/bin/env python3
"""
swarm/swarm.py — Main entry point for the Atlas E-1 Agent Swarm.

A swarm is a coordinated group of AI agents working together on a goal.

Quick start:
    python3 swarm.py "Build a CLI tool that converts CSV to JSON"

Common use cases:
    # Research-only swarm
    python3 swarm.py --role researcher "What are the top 3 competitor offerings for our AI Whisperers product?"

    # Build swarm (default: researcher → coder → tester → reviewer)
    python3 swarm.py "Fix the bug in cron_health.py where it reports wrong exit codes"

    # Custom memory dir
    python3 swarm.py --memory-dir /tmp/some-state "Build X"

The swarm persists state to a memory directory so you can inspect/replay:
    ls /tmp/swarm-state/run-123/        # memory.jsonl + snapshots + blackboard
    cat /tmp/swarm-state/run-123/memory.jsonl | jq

The pattern is intentionally simple:
1. Orchestrator decomposes goal into subtasks
2. Workers (subprocesses) execute each subtask
3. Shared memory threads state across workers
4. Orchestrator monitors + retries failures
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from orchestrator import Orchestrator, Plan  # noqa: E402


def create_run_dir() -> Path:
    """Create a unique run directory."""
    base = Path("/tmp/swarm-state")
    base.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base / f"run-{ts}"
    run_dir.mkdir(exist_ok=True)
    return run_dir


def status_for_run(run_dir: Path) -> dict:
    """Get the current status of a swarm run."""
    log_path = run_dir / "memory.jsonl"
    if not log_path.exists():
        return {"status": "no_data", "run_dir": str(run_dir)}
    entries = []
    for line in log_path.read_text().splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not entries:
        return {"status": "empty", "run_dir": str(run_dir)}
    return {
        "run_dir": str(run_dir),
        "started_at": entries[0]["ts"],
        "last_activity": entries[-1]["ts"],
        "n_events": len(entries),
        "agents": sorted({e["agent_id"] for e in entries}),
        "last_event": entries[-1],
    }


def list_runs() -> list[dict]:
    """List all swarm runs."""
    base = Path("/tmp/swarm-state")
    if not base.exists():
        return []
    runs = []
    for d in sorted(base.glob("run-*")):
        if d.is_dir():
            runs.append({
                "id": d.name,
                "path": str(d),
                "status": status_for_run(d),
            })
    return runs


def main():
    p = argparse.ArgumentParser(
        description="Atlas E-1 Agent Swarm — coordinate multiple AI agents on a goal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  swarm.py "Build a CLI tool that converts CSV to JSON"
  swarm.py --plan-only "Research the top 5 Python web frameworks in 2026"
  swarm.py --memory-dir /tmp/my-state "Fix the auth bug"
  swarm.py --status
  swarm.py --list-runs
        """,
    )
    p.add_argument("goal", nargs="?", help="The goal for the swarm (required unless --status/--list-runs)")
    p.add_argument("--memory-dir", help="Where to store shared memory (default: auto-generated run dir)")
    p.add_argument("--max-parallel", type=int, default=3, help="Max parallel workers (default: 3)")
    p.add_argument("--plan-only", action="store_true", help="Show plan without executing")
    p.add_argument("--status", action="store_true", help="Show status of latest run")
    p.add_argument("--list-runs", action="store_true", help="List all swarm runs")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    args = p.parse_args()

    if args.list_runs:
        runs = list_runs()
        if args.json:
            print(json.dumps(runs, indent=2, default=str))
        else:
            if not runs:
                print("No swarm runs found in /tmp/swarm-state/")
                return
            for r in runs:
                status = r["status"]
                print(f"\n{r['id']}")
                print(f"  events: {status.get('n_events', 0)}")
                print(f"  agents: {', '.join(status.get('agents', []))}")
                print(f"  last: {status.get('last_activity', '?')}")
        return

    if args.status:
        # Show status of the most recent run
        runs = list_runs()
        if not runs:
            print("No swarm runs found.")
            return
        latest = runs[-1]
        if args.json:
            print(json.dumps(latest, indent=2, default=str))
        else:
            print(f"\nLatest run: {latest['id']}")
            print(json.dumps(latest['status'], indent=2, default=str))
        return

    if not args.goal:
        p.error("goal is required (unless using --status or --list-runs)")

    # Setup
    memory_dir = Path(args.memory_dir) if args.memory_dir else create_run_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)

    if not args.json:
        print(f"╔══════════════════════════════════════════════════════════╗")
        print(f"║  SWARM (Atlas E-1 Agent Swarm)                          ║")
        print(f"╚══════════════════════════════════════════════════════════╝")
        print(f"\nGoal: {args.goal}")
        print(f"Memory: {memory_dir}")
        print(f"Max parallel: {args.max_parallel}")

    orch = Orchestrator(memory_dir=memory_dir, max_parallel=args.max_parallel)
    plan = orch.plan(args.goal)

    if not args.json:
        print(f"\nPlan: {len(plan.subtasks)} subtasks")
        for s in plan.subtasks:
            deps = f" ← [{', '.join(s.depends_on)}]" if s.depends_on else ""
            print(f"  • [{s.role:10}] {s.id:12} {s.description[:60]}{deps}")

    if args.plan_only:
        return

    if not args.json:
        print(f"\nExecuting...")

    start = time.time()
    result = orch.run(plan)
    duration = time.time() - start
    status = orch.status(result)

    if args.json:
        print(json.dumps({
            "goal": args.goal,
            "memory_dir": str(memory_dir),
            "duration_sec": round(duration, 1),
            **status,
        }, indent=2, default=str))
    else:
        print(f"\n{'─' * 60}")
        print(f"Done in {duration:.1f}s")
        print(f"  ✓ Succeeded: {status['succeeded']}")
        print(f"  ✗ Failed:    {status['failed']}")
        print(f"  ⤼ Skipped:   {status['skipped']}")
        print(f"\nMemory: {memory_dir}")
        print(f"  cat {memory_dir}/memory.jsonl | jq   # full event log")


if __name__ == "__main__":
    main()