#!/usr/bin/env python3
"""
swarm/cost_optimizer.py — Auto-pick the cheapest sufficient model per subtask.

The optimizer takes a Plan and rewrites the model field on each subtask based on:
- Required quality (from subtask role + any explicit hints)
- Cost ceiling (per-worker max spend)
- Observed history (if CostTracker data exists, prefer historically-fast/cheap models)

Quality requirements by role (default):
- reviewer: needs strong reasoning → sonnet preferred
- tester: needs accuracy → sonnet
- coder: needs strong reasoning → sonnet
- researcher: medium → haiku ok
- writer: medium → haiku ok

The optimizer is configurable: pass `quality_overrides` to tune per role.

Usage:
    from cost_optimizer import CostOptimizer
    optimizer = CostOptimizer(cost_tracker=tracker)
    optimized = optimizer.optimize(plan)
    original_cost = optimizer.estimate_cost(plan)
    optimized_cost = optimizer.estimate_cost(optimized)
    print(f"Saves ${original_cost - optimized_cost:.4f}")
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Lazy imports to avoid circular dependency
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    from orchestrator import Plan, SubTask, TaskStatus  # noqa: E402
    from cost_tracker import CostTracker, MODEL_PRICING  # noqa: E402


# Model capability score (rough, 0-100). Higher = better reasoning.
# Used to compare options for a given quality requirement.
MODEL_CAPABILITY = {
    "haiku": 60,
    "sonnet": 85,
    "opus": 100,
    "gpt-3.5-turbo": 55,
    "gpt-4": 90,
    "gpt-4-turbo": 95,
}

# Default quality requirements by role (minimum capability score)
QUALITY_REQUIREMENTS = {
    "reviewer": 85,   # needs strong reasoning
    "tester": 85,     # needs accuracy
    "coder": 85,      # needs reasoning for complex code
    "writer": 60,     # haiku is fine for prose
    "researcher": 60, # haiku ok for simple research
}

# Default models to consider in cost order
DEFAULT_MODEL_OPTIONS = ["haiku", "sonnet", "opus"]


@dataclass
class OptimizerConfig:
    """Tune the optimizer."""
    quality_overrides: dict  # role -> minimum capability
    model_options: list      # list of model names to consider
    cost_ceiling_usd: float  # reject options above this per worker
    prefer_history: bool     # use observed cost data if available

    @classmethod
    def default(cls) -> "OptimizerConfig":
        return cls(
            quality_overrides={},
            model_options=DEFAULT_MODEL_OPTIONS,
            cost_ceiling_usd=1.0,
            prefer_history=True,
        )


class CostOptimizer:
    """Choose the cheapest sufficient model for each subtask."""

    def __init__(
        self,
        cost_tracker: Optional["CostTracker"] = None,
        config: Optional[OptimizerConfig] = None,
    ):
        from cost_tracker import CostTracker
        self.tracker = cost_tracker
        self.config = config or OptimizerConfig.default()

    def optimize(self, plan: "Plan") -> "Plan":
        """Return a NEW plan with optimized model choices per subtask.

        Original plan is unchanged. New plan has same goal, subtasks, deps.
        """
        from orchestrator import Plan, SubTask, TaskStatus
        optimized_subtasks = []
        for subtask in plan.subtasks:
            new_model = self._pick_model(subtask)
            new_subtask = SubTask(
                id=subtask.id,
                role=subtask.role,
                description=subtask.description,
                depends_on=list(subtask.depends_on),
                extra_context=subtask.extra_context,
                timeout=subtask.timeout,
                model=new_model,
                status=TaskStatus.PENDING,
            )
            optimized_subtasks.append(new_subtask)
        return Plan(
            goal=plan.goal,
            subtasks=optimized_subtasks,
            metadata={**plan.metadata, "optimized": True},
        )

    def _pick_model(self, subtask: "SubTask") -> str:
        """Pick the cheapest model that meets quality requirements."""
        # Get required capability
        required = self.config.quality_overrides.get(
            subtask.role,
            QUALITY_REQUIREMENTS.get(subtask.role, 60),
        )

        # Filter to models that meet quality
        candidates = [
            m for m in self.config.model_options
            if MODEL_CAPABILITY.get(m, 60) >= required
        ]
        if not candidates:
            candidates = self.config.model_options  # fall back to all

        # Optionally use observed history to pick fastest/cheapest
        if self.config.prefer_history and self.tracker:
            history = self._history_for_role(subtask.role)
            if history:
                # Prefer historically-fastest (lowest cost/duration)
                candidates = sorted(
                    candidates,
                    key=lambda m: history.get(m, float("inf")),
                )

        # Pick cheapest viable option
        from cost_tracker import MODEL_PRICING
        def cost(m: str) -> float:
            pricing = MODEL_PRICING.get(m, {"input": 0.001, "output": 0.005})
            # Estimate: 8000 input + 2000 output (typical worker)
            return pricing["input"] * 8 + pricing["output"] * 2

        cheapest = min(candidates, key=lambda m: cost(m))
        # Apply cost ceiling
        if cost(cheapest) > self.config.cost_ceiling_usd:
            # All viable options exceed ceiling, fall back to haiku
            return "haiku"
        return cheapest

    def _history_for_role(self, role: str) -> dict:
        """Get observed cost-per-second per model for a role. Empty if no data."""
        if not self.tracker or not self.tracker.costs:
            return {}
        by_model: dict[str, list[float]] = {}
        for c in self.tracker.costs:
            if c.role == role and c.duration_sec > 0:
                cps = c.cost_usd / c.duration_sec
                by_model.setdefault(c.model, []).append(cps)
        return {m: sum(v) / len(v) for m, v in by_model.items() if v}

    def estimate_cost(self, plan: "Plan", tokens_per_subtask: int = 10000) -> dict:
        """Estimate total cost for a plan. Returns breakdown by model."""
        from cost_tracker import MODEL_PRICING
        total = 0.0
        by_model: dict[str, dict] = {}
        for s in plan.subtasks:
            model = s.model
            pricing = MODEL_PRICING.get(model, {"input": 0.001, "output": 0.005})
            # Assume 4:1 input:output ratio
            tokens_in = int(tokens_per_subtask * 0.8)
            tokens_out = tokens_per_subtask - tokens_in
            cost = (
                tokens_in / 1000 * pricing["input"]
                + tokens_out / 1000 * pricing["output"]
            )
            total += cost
            by_model.setdefault(model, {"count": 0, "cost_usd": 0.0})
            by_model[model]["count"] += 1
            by_model[model]["cost_usd"] += cost
        return {
            "total_cost_usd": round(total, 4),
            "n_subtasks": len(plan.subtasks),
            "by_model": {m: {**v, "cost_usd": round(v["cost_usd"], 4)} for m, v in by_model.items()},
        }


def main():
    """CLI: optimize a plan from JSON."""
    import argparse
    import json

    p = argparse.ArgumentParser(description="Auto-optimize a plan's model choices")
    p.add_argument("--plan-json", help="JSON of a Plan to optimize (subtasks + deps)")
    p.add_argument("--memory-dir", help="Use cost tracker history from this dir")
    p.add_argument("--cost-ceiling", type=float, default=1.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    from orchestrator import Plan, SubTask, TaskStatus
    plan_data = json.loads(args.plan_json) if args.plan_json else {
        "goal": "demo",
        "subtasks": [
            {"id": "research", "role": "researcher", "description": "d", "depends_on": []},
            {"id": "code", "role": "coder", "description": "d", "depends_on": ["research"]},
            {"id": "review", "role": "reviewer", "description": "d", "depends_on": ["code"]},
        ],
    }
    plan = Plan(
        goal=plan_data["goal"],
        subtasks=[
            SubTask(
                id=s["id"], role=s["role"], description=s.get("description", ""),
                depends_on=s.get("depends_on", []),
                model=s.get("model", "haiku"),
                timeout=s.get("timeout", 300),
            )
            for s in plan_data["subtasks"]
        ],
    )

    tracker = None
    if args.memory_dir:
        from cost_tracker import CostTracker
        tracker = CostTracker(args.memory_dir)

    optimizer = CostOptimizer(
        cost_tracker=tracker,
        config=OptimizerConfig(
            quality_overrides={},
            model_options=DEFAULT_MODEL_OPTIONS,
            cost_ceiling_usd=args.cost_ceiling,
            prefer_history=True,
        ),
    )
    optimized = optimizer.optimize(plan)
    original_cost = optimizer.estimate_cost(plan)
    optimized_cost = optimizer.estimate_cost(optimized)

    if args.json:
        print(json.dumps({
            "original": original_cost,
            "optimized": optimized_cost,
            "savings_usd": round(original_cost["total_cost_usd"] - optimized_cost["total_cost_usd"], 4),
            "before": [{"id": s.id, "model": s.model} for s in plan.subtasks],
            "after": [{"id": s.id, "model": s.model} for s in optimized.subtasks],
        }, indent=2))
    else:
        print(f"\nOriginal cost:  ${original_cost['total_cost_usd']:.4f}")
        print(f"Optimized cost:  ${optimized_cost['total_cost_usd']:.4f}")
        print(f"Savings:         ${original_cost['total_cost_usd'] - optimized_cost['total_cost_usd']:.4f}")
        print(f"\nModel changes:")
        for s_before, s_after in zip(plan.subtasks, optimized.subtasks):
            if s_before.model != s_after.model:
                print(f"  {s_before.id:20} {s_before.role:12} {s_before.model:8} → {s_after.model}")


if __name__ == "__main__":
    main()
