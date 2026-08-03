#!/usr/bin/env python3
"""
swarm/orchestrator.py — Routes tasks to workers and monitors progress.

The orchestrator is the brain of the swarm. It:
1. Receives a goal from the user (via swarm.py CLI)
2. Decomposes the goal into subtasks with roles (researcher, coder, reviewer, tester)
3. Decides execution order + parallelism
4. Spawns workers (subprocesses) for each subtask
5. Monitors shared memory for results
6. Decides when to retry, escalate, or finish

Execution model:
- Workers are launched concurrently (up to max_parallel)
- Orchestrator polls shared memory for completions
- Failure policy: retry once with same role, then escalate to reviewer

Usage:
    from orchestrator import Orchestrator, SubTask
    orch = Orchestrator(memory_dir="/tmp/swarm-state/run-123")
    plan = orch.plan(goal="Build a CLI tool that does X")
    orch.run(plan)
"""

import argparse
import json
import os
import subprocess
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from shared_memory import SharedMemory  # noqa: E402
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from retry import RetryPolicy  # noqa: F401


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    """One unit of work for a single worker."""
    id: str
    role: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    extra_context: Optional[str] = None
    timeout: int = 300
    model: str = "haiku"
    status: TaskStatus = TaskStatus.PENDING
    worker_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[dict] = None


@dataclass
class Plan:
    """A list of subtasks with their dependencies."""
    goal: str
    subtasks: list[SubTask]
    metadata: dict = field(default_factory=dict)

    def pending(self) -> list[SubTask]:
        return [s for s in self.subtasks if s.status == TaskStatus.PENDING]

    def ready(self) -> list[SubTask]:
        """Subtasks whose dependencies are all succeeded."""
        done_ids = {s.id for s in self.subtasks if s.status == TaskStatus.SUCCEEDED}
        return [s for s in self.pending() if all(d in done_ids for d in s.depends_on)]

    def failed(self) -> list[SubTask]:
        return [s for s in self.subtasks if s.status == TaskStatus.FAILED]

    def is_complete(self) -> bool:
        return all(
            s.status in (TaskStatus.SUCCEEDED, TaskStatus.SKIPPED, TaskStatus.FAILED)
            for s in self.subtasks
        )


class Orchestrator:
    """Routes work to workers and tracks progress."""

    def __init__(
        self,
        memory_dir: str | Path,
        max_parallel: int = 3,
        worker_script: Optional[Path] = None,
        retry_policy: Optional["RetryPolicy"] = None,
    ):
        self.memory = SharedMemory(memory_dir)
        self.memory_dir = Path(memory_dir)
        self.max_parallel = max_parallel
        self.worker_script = worker_script or (Path(__file__).parent / "worker.py")
        self.orchestrator_id = f"orch-{int(time.time())}"
        if retry_policy is None:
            from retry import RetryPolicy
            retry_policy = RetryPolicy.default()
        self.retry_policy = retry_policy

    # ---- Decomposition ----

    def plan(self, goal: str) -> Plan:
        """Decompose a goal into a plan of subtasks.

        Simple heuristic-based decomposition. For complex goals, swap in a
        LLM-based planner.

        For now, this implements a few common patterns:
        - "build" → researcher + coder + tester
        - "fix"   → researcher + coder + tester
        - "research" → researcher only
        - "review" → reviewer only
        """
        goal_l = goal.lower()
        if any(k in goal_l for k in ["research", "find out", "look up", "investigate"]):
            return self._plan_research(goal)
        elif any(k in goal_l for k in ["review", "check", "audit"]):
            return self._plan_review(goal)
        else:  # default: build/fix workflow
            return self._plan_build(goal)

    def _plan_research(self, goal: str) -> Plan:
        return Plan(
            goal=goal,
            subtasks=[
                SubTask(
                    id="research",
                    role="researcher",
                    description=f"Research: {goal}",
                    timeout=300,
                ),
            ],
        )

    def _plan_review(self, goal: str) -> Plan:
        return Plan(
            goal=goal,
            subtasks=[
                SubTask(
                    id="review",
                    role="reviewer",
                    description=f"Review: {goal}",
                    timeout=300,
                ),
            ],
        )

    def _plan_build(self, goal: str) -> Plan:
        """Default: research → code → test → review."""
        return Plan(
            goal=goal,
            subtasks=[
                SubTask(
                    id="research",
                    role="researcher",
                    description=f"Research what needs to be built: {goal}",
                    timeout=180,
                ),
                SubTask(
                    id="code",
                    role="coder",
                    description=f"Implement: {goal}",
                    depends_on=["research"],
                    timeout=600,
                    model="sonnet",
                ),
                SubTask(
                    id="test",
                    role="tester",
                    description=f"Verify the implementation works: {goal}",
                    depends_on=["code"],
                    timeout=300,
                ),
                SubTask(
                    id="review",
                    role="reviewer",
                    description=f"Review the implementation: {goal}",
                    depends_on=["test"],
                    timeout=180,
                ),
            ],
        )

    # ---- Execution ----

    def run(self, plan: Plan) -> Plan:
        """Execute the plan, spawning workers in parallel where possible."""
        self.memory.log(self.orchestrator_id, "orchestrator", "plan_started", {
            "goal": plan.goal,
            "n_subtasks": len(plan.subtasks),
            "max_parallel": self.max_parallel,
        })
        plan.metadata["started_at"] = datetime.now(timezone.utc).isoformat()

        try:
            while not plan.is_complete():
                ready = plan.ready()
                if not ready:
                    # Check for deadlock (no ready tasks + pending tasks = cycle)
                    if plan.pending():
                        failed = plan.failed()
                        if failed:
                            self.memory.log(self.orchestrator_id, "orchestrator",
                                            "blocked_by_failures", {
                                                "failed": [s.id for s in failed],
                                                "pending": [s.id for s in plan.pending()],
                                            })
                            break
                        # Cycle: skip remaining
                        for s in plan.pending():
                            s.status = TaskStatus.SKIPPED
                            self.memory.log(self.orchestrator_id, "orchestrator",
                                            "cycle_skip", {"subtask_id": s.id})
                        continue

                # Launch up to max_parallel ready tasks
                with ThreadPoolExecutor(max_workers=self.max_parallel) as ex:
                    futures = {}
                    for subtask in ready[: self.max_parallel]:
                        f = ex.submit(self._run_subtask, plan, subtask)
                        futures[f] = subtask

                    for f in as_completed(futures):
                        try:
                            f.result()
                        except Exception as e:
                            subtask = futures[f]
                            self.memory.log(
                                self.orchestrator_id, "orchestrator",
                                "subtask_raised", {"id": subtask.id, "error": str(e)},
                            )
                            subtask.status = TaskStatus.FAILED

                # Save state
                self._save_plan(plan)
        finally:
            plan.metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save_plan(plan)
            self.memory.publish("plan", {
                "goal": plan.goal,
                "subtasks": [self._serialize(s) for s in plan.subtasks],
                "metadata": plan.metadata,
            })
            self.memory.log(self.orchestrator_id, "orchestrator", "plan_finished", {
                "succeeded": sum(1 for s in plan.subtasks if s.status == TaskStatus.SUCCEEDED),
                "failed": sum(1 for s in plan.subtasks if s.status == TaskStatus.FAILED),
                "skipped": sum(1 for s in plan.subtasks if s.status == TaskStatus.SKIPPED),
            })
        return plan

    def _run_subtask(self, plan: Plan, subtask: SubTask) -> None:
        """Run a single subtask via worker subprocess."""
        subtask.status = TaskStatus.RUNNING
        subtask.started_at = datetime.now(timezone.utc).isoformat()
        subtask.worker_id = f"w-{subtask.id}-{int(time.time())}"

        self.memory.log(self.orchestrator_id, "orchestrator", "subtask_launched", {
            "id": subtask.id,
            "role": subtask.role,
            "worker_id": subtask.worker_id,
        })

        # Find extra context from upstream tasks
        extra_parts = [f"Goal: {plan.goal}"]
        for dep_id in subtask.depends_on:
            for dep in plan.subtasks:
                if dep.id == dep_id:
                    snap_name = f"result-{dep.id}"
                    data = self.memory.read(snap_name)
                    if data is not None:
                        extra_parts.append(
                            f"\n\nOutput from {dep.id} ({dep.role}):\n```json\n{json.dumps(data, indent=2, default=str)[:3000]}\n```"
                        )
        subtask.extra_context = "\n\n".join(extra_parts)

        # Launch worker subprocess
        cmd = [
            sys.executable,
            str(self.worker_script),
            "--role", subtask.role,
            "--task", subtask.description,
            "--memory-dir", str(self.memory_dir),
            "--worker-id", subtask.worker_id,
            "--model", subtask.model,
            "--timeout", str(subtask.timeout),
            "--json",
        ]
        if subtask.extra_context:
            cmd.extend(["--extra-context", subtask.extra_context])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=subtask.timeout + 60)
            subtask.finished_at = datetime.now(timezone.utc).isoformat()
            if result.returncode == 0:
                try:
                    parsed = json.loads(result.stdout)
                    subtask.result = parsed
                    subtask.status = TaskStatus.SUCCEEDED if parsed.get("ok") else TaskStatus.FAILED
                except json.JSONDecodeError:
                    subtask.result = {"raw": result.stdout[-2000:]}
                    subtask.status = TaskStatus.SUCCEEDED
            else:
                subtask.result = {"stderr": result.stderr[-500:], "raw": result.stdout[-500:]}
                subtask.status = TaskStatus.FAILED
        except subprocess.TimeoutExpired:
            subtask.status = TaskStatus.FAILED
            subtask.result = {"error": "timeout"}

        self.memory.log(self.orchestrator_id, "orchestrator", "subtask_finished", {
            "id": subtask.id,
            "status": subtask.status.value,
            "worker_id": subtask.worker_id,
        })

    def _serialize(self, subtask: SubTask) -> dict:
        return {
            "id": subtask.id,
            "role": subtask.role,
            "description": subtask.description[:200],
            "status": subtask.status.value,
            "depends_on": subtask.depends_on,
            "started_at": subtask.started_at,
            "finished_at": subtask.finished_at,
            "result_ok": subtask.result.get("ok") if subtask.result else None,
        }

    def _save_plan(self, plan: Plan) -> None:
        self.memory.write_blackboard("current_plan", {
            "goal": plan.goal,
            "subtasks": [self._serialize(s) for s in plan.subtasks],
            "metadata": plan.metadata,
        })

    def _handle_failure(self, plan: Plan, subtask: SubTask, failure_reason: str) -> None:
        """Apply retry policy to a failed subtask."""
        # Inline import to avoid circular dependency
        from retry import RetryPolicy, should_skip_dependents
        # Ensure we have a RetryPolicy instance
        if not hasattr(self, "retry_policy") or self.retry_policy is None:
            self.retry_policy = RetryPolicy.default()
        # Count existing attempts (look for retry subtasks with this prefix)
        attempt = sum(
            1 for s in plan.subtasks
            if s.id == subtask.id or s.id.startswith(f"{subtask.id}-retry-")
        )
        decision = self.retry_policy.decide(subtask, attempt, failure_reason)
        self.memory.log(self.orchestrator_id, "orchestrator", "retry_decision", decision.to_dict())

        if decision.action.value == "retry" and decision.retry_subtask:
            # Add retry subtask to plan
            plan.subtasks.append(decision.retry_subtask)
            self.memory.log(
                self.orchestrator_id, "orchestrator",
                "retry_added", {"id": decision.retry_subtask.id},
            )
        elif decision.action.value == "escalate" and decision.next_subtask:
            # Add escalation subtask that re-tries the original after
            plan.subtasks.append(decision.next_subtask)
            # Also retry the original after the escalation
            retry_subtask = self.retry_policy._make_retry(subtask, attempt + 1)
            retry_subtask.depends_on = [decision.next_subtask.id] + list(subtask.depends_on)
            plan.subtasks.append(retry_subtask)
            self.memory.log(
                self.orchestrator_id, "orchestrator",
                "escalation_added", {"id": decision.next_subtask.id},
            )
        else:  # fail
            # Skip all dependents
            for dep in should_skip_dependents(subtask, plan):
                dep.status = TaskStatus.SKIPPED
                self.memory.log(
                    self.orchestrator_id, "orchestrator",
                    "dependent_skipped", {"id": dep.id, "due_to": subtask.id},
                )

    def status(self, plan: Plan) -> dict:
        return {
            "goal": plan.goal,
            "n_total": len(plan.subtasks),
            "succeeded": sum(1 for s in plan.subtasks if s.status == TaskStatus.SUCCEEDED),
            "failed": sum(1 for s in plan.subtasks if s.status == TaskStatus.FAILED),
            "running": sum(1 for s in plan.subtasks if s.status == TaskStatus.RUNNING),
            "pending": sum(1 for s in plan.subtasks if s.status == TaskStatus.PENDING),
            "skipped": sum(1 for s in plan.subtasks if s.status == TaskStatus.SKIPPED),
            "started_at": plan.metadata.get("started_at"),
            "finished_at": plan.metadata.get("finished_at"),
        }


def main():
    """CLI: run a swarm on a goal."""
    p = argparse.ArgumentParser(description="Orchestrate an agent swarm")
    p.add_argument("--goal", required=True, help="What you want done")
    p.add_argument("--memory-dir", default="/tmp/swarm-state/default",
                   help="Where to store shared memory")
    p.add_argument("--max-parallel", type=int, default=3)
    p.add_argument("--plan-only", action="store_true",
                   help="Only show the plan, don't execute")
    p.add_argument("--json", action="store_true", help="Output as JSON only")
    args = p.parse_args()

    orch = Orchestrator(memory_dir=args.memory_dir, max_parallel=args.max_parallel)
    plan = orch.plan(args.goal)

    if args.plan_only:
        if args.json:
            print(json.dumps({
                "goal": plan.goal,
                "subtasks": [orch._serialize(s) for s in plan.subtasks],
            }, indent=2))
        else:
            print(f"\nPlan for: {plan.goal}\n")
            for s in plan.subtasks:
                deps = f" (depends on: {', '.join(s.depends_on)})" if s.depends_on else ""
                print(f"  - [{s.role}] {s.id}: {s.description[:80]}{deps}")
        return

    result = orch.run(plan)
    status = orch.status(result)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"\nResult: {status['succeeded']}/{status['n_total']} succeeded")
        if status['failed']:
            print(f"  Failed: {status['failed']}")


if __name__ == "__main__":
    main()