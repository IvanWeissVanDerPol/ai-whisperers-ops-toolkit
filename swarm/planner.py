#!/usr/bin/env python3
"""
swarm/planner.py — LLM-based task decomposition for the swarm.

Replaces the keyword-based heuristic planner with an LLM call. Given a goal,
the planner asks a model to:
1. Identify the type of work (research/build/review/audit/etc)
2. Break the goal into subtasks with roles
3. Specify dependencies between subtasks
4. Suggest which model to use per subtask

The planner uses JSON-mode prompts to ensure structured output. Falls back
to the heuristic planner if the LLM is unavailable or returns invalid JSON.

Usage:
    from planner import LLMPlanner
    planner = LLMPlanner(model="haiku")
    plan = planner.plan("Build a CLI that converts CSV to JSON")
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from orchestrator import Plan, SubTask, TaskStatus  # noqa: E402


PLANNER_PROMPT = """You are a TASK PLANNER for an AI agent swarm. Your job is to decompose a goal into a structured plan.

# Available roles
- **researcher**: gathers information, analyzes data, finds patterns
- **coder**: writes/modifies code, runs commands, fixes bugs
- **reviewer**: checks code/plans for issues (bugs, design, security)
- **tester**: verifies claims by actually running things
- **writer**: produces polished prose, documentation, content

# Available models
- **haiku**: faster, cheaper, good for simple/repetitive tasks
- **sonnet**: stronger reasoning, good for complex coding/analysis

# Output format (strict JSON)
```json
{{
  "rationale": "<one-sentence explanation of why this decomposition>",
  "subtasks": [
    {{
      "id": "<kebab-case-id>",
      "role": "<role>",
      "description": "<specific, actionable description>",
      "depends_on": ["<id-of-upstream-subtask>", ...],
      "model": "haiku|sonnet",
      "timeout_sec": <number>
    }},
    ...
  ]
}}
```

# Decomposition rules
- 1-7 subtasks (most goals: 2-4)
- Every subtask depends on at least one other, OR at least one other depends on it (no orphans)
- Use `depends_on: []` only for tasks that must run first
- Sequential chains: B depends on A, C depends on B
- Parallel research: 3 researcher tasks all depend on nothing, 1 synthesis depends on all 3
- Use sonnet for: complex code generation, nuanced analysis, content production
- Use haiku for: simple lookups, formatting, repetitive ops

# Common patterns

**Build workflow** (default for new features):
1. researcher → 2. coder (sonnet) → 3. tester → 4. reviewer

**Research workflow** (default for investigations):
1-3. Multiple parallel researcher tasks (different angles) → 4. writer synthesis → 5. reviewer

**Audit workflow** (default for "review/check/audit"):
1. researcher (gather what's there) → 2. reviewer (analyze) → 3. writer (report)

**Fix workflow** (default for "fix the bug"):
1. researcher (understand bug) → 2. coder (sonnet, fix) → 3. tester (verify fix) → 4. reviewer (sanity check)

Now decompose this goal:
{goal}

Output ONLY the JSON. No preamble, no explanation, no markdown fences."""


class LLMPlanner:
    """Plans a swarm goal using an LLM."""

    def __init__(self, model: str = "haiku", timeout: int = 60, fallback_planner=None):
        """Initialize with model + optional fallback."""
        self.model = model
        self.timeout = timeout
        self.fallback_planner = fallback_planner or self._default_heuristic

    def plan(self, goal: str, memory_dir: Optional[Path] = None) -> Plan:
        """Decompose a goal into a Plan. Falls back to heuristic on failure."""
        from shared_memory import SharedMemory  # local import to avoid cycles
        memory = None
        if memory_dir:
            memory = SharedMemory(memory_dir)
            memory.log("planner", "planner", "plan_requested", {"goal": goal[:500]})

        try:
            raw = self._call_llm(goal)
            parsed = self._parse_json(raw)
            plan = self._to_plan(goal, parsed)
            if memory:
                memory.log("planner", "planner", "plan_created", {
                    "n_subtasks": len(plan.subtasks),
                    "model": self.model,
                })
            return plan
        except Exception as e:
            # Fall back to heuristic
            if memory:
                memory.log("planner", "planner", "plan_fallback_to_heuristic", {
                    "error": str(e)[:300],
                })
            return self.fallback_planner(goal)

    def _call_llm(self, goal: str) -> str:
        """Call claude CLI with the planner prompt. Returns raw text output."""
        prompt = PLANNER_PROMPT.format(goal=goal)
        cmd = ["claude", "-p", prompt, "--model", self.model, "--no-input"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(f"claude CLI exit {result.returncode}: {result.stderr[:200]}")
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError("claude CLI not installed")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"claude CLI timeout after {self.timeout}s")

    def _parse_json(self, raw: str) -> dict:
        """Extract JSON from claude output (which may include markdown fences)."""
        # Strip markdown code fences if present
        text = raw.strip()
        # Match ```json ... ``` or ``` ... ```
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        # Sometimes claude puts JSON inline
        if not text.startswith("{"):
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                text = m.group(0)
        return json.loads(text)

    def _to_plan(self, goal: str, parsed: dict) -> Plan:
        """Convert parsed JSON to Plan object. Validates structure."""
        if "subtasks" not in parsed or not isinstance(parsed["subtasks"], list):
            raise ValueError("parsed response missing 'subtasks' array")
        subtasks = []
        valid_roles = {"researcher", "coder", "reviewer", "tester", "writer"}
        valid_models = {"haiku", "sonnet"}
        for i, raw in enumerate(parsed["subtasks"]):
            role = raw.get("role", "").lower()
            if role not in valid_roles:
                raise ValueError(f"subtask {i}: invalid role '{role}'")
            model = raw.get("model", "haiku").lower()
            if model not in valid_models:
                model = "haiku"
            sid = raw.get("id", f"task-{i+1}")
            sid = re.sub(r"[^a-z0-9-]", "-", sid.lower())
            subtasks.append(SubTask(
                id=sid,
                role=role,
                description=raw.get("description", ""),
                depends_on=raw.get("depends_on", []) or [],
                model=model,
                timeout=raw.get("timeout_sec", 300),
            ))
        return Plan(
            goal=goal,
            subtasks=subtasks,
            metadata={
                "planner": "llm",
                "model": self.model,
                "rationale": parsed.get("rationale", ""),
            },
        )

    @staticmethod
    def _default_heuristic(goal: str) -> Plan:
        """Keyword-based fallback planner (matches Orchestrator.plan logic)."""
        goal_l = goal.lower()
        if any(k in goal_l for k in ["research", "find out", "look up", "investigate"]):
            return Plan(goal=goal, subtasks=[
                SubTask(id="research", role="researcher", description=f"Research: {goal}", timeout=300),
            ])
        elif any(k in goal_l for k in ["review", "check", "audit"]):
            return Plan(goal=goal, subtasks=[
                SubTask(id="review", role="reviewer", description=f"Review: {goal}", timeout=300),
            ])
        else:
            return Plan(goal=goal, subtasks=[
                SubTask(id="research", role="researcher",
                        description=f"Research what needs to be built: {goal}", timeout=180),
                SubTask(id="code", role="coder", description=f"Implement: {goal}",
                        depends_on=["research"], timeout=600, model="sonnet"),
                SubTask(id="test", role="tester", description=f"Verify: {goal}",
                        depends_on=["code"], timeout=300),
                SubTask(id="review", role="reviewer", description=f"Review: {goal}",
                        depends_on=["test"], timeout=180),
            ])


def main():
    """CLI: plan a goal."""
    import argparse
    p = argparse.ArgumentParser(description="LLM-based task planner")
    p.add_argument("goal", help="The goal to decompose")
    p.add_argument("--model", default="haiku")
    p.add_argument("--memory-dir", help="Log planning decisions to this memory dir")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    planner = LLMPlanner(model=args.model)
    memory_dir = Path(args.memory_dir) if args.memory_dir else None
    plan = planner.plan(args.goal, memory_dir=memory_dir)

    if args.json:
        print(json.dumps({
            "goal": plan.goal,
            "metadata": plan.metadata,
            "subtasks": [asdict(s) for s in plan.subtasks],
        }, indent=2, default=str))
    else:
        print(f"\nPlan for: {plan.goal}\n")
        print(f"Rationale: {plan.metadata.get('rationale', '')}\n")
        for s in plan.subtasks:
            deps = f" ← [{', '.join(s.depends_on)}]" if s.depends_on else ""
            print(f"  • [{s.role:10}] {s.id:20} ({s.model:6}) {s.description[:60]}{deps}")


if __name__ == "__main__":
    main()