#!/usr/bin/env python3
"""
swarm/examples/research_workflow.py — Example: research workflow for a ParaguAI lead site.

This example shows how to use the swarm to research a potential client before
generating their site brief. It's the kind of task that would benefit from
parallel exploration by multiple workers.

Usage:
    cd /root/ai-whisperers-ops-toolkit/swarm/examples
    python3 research_workflow.py "Research Tigo Paraguay's customer service for IT professionals"
"""

import sys
import time
from pathlib import Path

# Make swarm importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrator import Orchestrator, SubTask, Plan, TaskStatus  # noqa: E402


def research_plan(goal: str) -> Plan:
    """A more sophisticated plan than the default keyword-based one."""
    return Plan(
        goal=goal,
        subtasks=[
            # Phase 1: parallel research (3 angles)
            SubTask(
                id="business-profile",
                role="researcher",
                description=f"Find the business profile: who they are, where, contact info, hours. {goal}",
                timeout=180,
            ),
            SubTask(
                id="competitor-analysis",
                role="researcher",
                description=f"Identify 3-5 direct competitors and what they offer. {goal}",
                timeout=180,
            ),
            SubTask(
                id="online-presence",
                role="researcher",
                description=f"Audit their current online presence: Google Maps, social media, website. {goal}",
                timeout=180,
            ),
            # Phase 2: synthesis (depends on all 3)
            SubTask(
                id="synthesis",
                role="writer",
                description=f"Synthesize the 3 research outputs into a structured lead brief with priority score.",
                depends_on=["business-profile", "competitor-analysis", "online-presence"],
                timeout=300,
                model="sonnet",
            ),
            # Phase 3: review
            SubTask(
                id="review",
                role="reviewer",
                description=f"Review the lead brief for accuracy, missing fields, and lead-score reasonableness.",
                depends_on=["synthesis"],
                timeout=180,
            ),
        ],
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: research_workflow.py '<goal>'")
        sys.exit(1)
    goal = sys.argv[1]

    orch = Orchestrator(memory_dir=f"/tmp/swarm-state/example-{int(time.time())}")
    plan = research_plan(goal)

    print(f"\nPlan for: {goal}")
    print(f"  {len(plan.subtasks)} subtasks (3 parallel research → 1 synthesis → 1 review)")
    for s in plan.subtasks:
        deps = f" ← [{', '.join(s.depends_on)}]" if s.depends_on else ""
        print(f"    • [{s.role}] {s.id:20} {s.description[:70]}{deps}")

    print(f"\nMax parallel: 3 (research phase runs in parallel)")
    print(f"\nExecuting... (real workers will spawn claude subprocesses)")

    result = orch.run(plan)
    status = orch.status(result)

    print(f"\n✓ Done")
    print(f"  Succeeded: {status['succeeded']}/{status['n_total']}")
    print(f"  Failed:    {status['failed']}")
    print(f"  Duration:  {status.get('finished_at', '?')}")
    print(f"\nInspect: ls /tmp/swarm-state/example-*/")


if __name__ == "__main__":
    main()