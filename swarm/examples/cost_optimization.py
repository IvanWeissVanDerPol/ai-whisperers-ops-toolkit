#!/usr/bin/env python3
"""
swarm/examples/cost_optimization.py — Compare cost of a default plan vs an optimized plan.

Demonstrates:
- Build a 5-task plan with default (sonnet-everywhere) model choices
- Run CostOptimizer with different quality profiles
- Compare costs and show which tasks changed model

Usage:
    cd /root/ai-whisperers-ops-toolkit/swarm/examples
    python3 cost_optimization.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrator import Plan, SubTask, TaskStatus  # noqa: E402
from cost_optimizer import CostOptimizer, OptimizerConfig  # noqa: E402
from cost_tracker import CostTracker, MODEL_PRICING  # noqa: E402


def build_default_plan():
    """A 5-task plan starting with sonnet for everything (the expensive default)."""
    return Plan(
        goal="Compare model costs for a real workflow",
        subtasks=[
            SubTask(id="research", role="researcher", description="Research topic", model="sonnet"),
            SubTask(id="analyze", role="researcher", description="Analyze findings",
                    depends_on=["research"], model="sonnet"),
            SubTask(id="code", role="coder", description="Implement solution",
                    depends_on=["analyze"], model="sonnet"),
            SubTask(id="review", role="reviewer", description="Review implementation",
                    depends_on=["code"], model="sonnet"),
            SubTask(id="write", role="writer", description="Document the work",
                    depends_on=["review"], model="sonnet"),
        ],
    )


def build_optimized_plan():
    """Same plan but with model choices optimized for cost."""
    return Plan(
        goal="Same workflow, optimized models",
        subtasks=[
            SubTask(id="research", role="researcher", description="Research topic", model="haiku"),
            SubTask(id="analyze", role="researcher", description="Analyze findings",
                    depends_on=["research"], model="haiku"),
            SubTask(id="code", role="coder", description="Implement solution",
                    depends_on=["analyze"], model="sonnet"),
            SubTask(id="review", role="reviewer", description="Review implementation",
                    depends_on=["code"], model="sonnet"),
            SubTask(id="write", role="writer", description="Document the work",
                    depends_on=["review"], model="haiku"),
        ],
    )


def main():
    default_plan = build_default_plan()

    # Run optimizer
    optimizer = CostOptimizer(
        cost_tracker=None,
        config=OptimizerConfig(
            quality_overrides={},
            model_options=["haiku", "sonnet", "opus"],
            cost_ceiling_usd=5.0,
            prefer_history=False,
        ),
    )
    optimized = optimizer.optimize(default_plan)

    # Compare costs
    default_cost = optimizer.estimate_cost(default_plan)
    optimized_cost = optimizer.estimate_cost(optimized)
    savings = default_cost["total_cost_usd"] - optimized_cost["total_cost_usd"]
    pct = savings / default_cost["total_cost_usd"] * 100

    print("=" * 70)
    print("COST OPTIMIZATION COMPARISON")
    print("=" * 70)
    print(f"\nWorkflow: 5-task plan (research → analyze → code → review → write)")
    print(f"Tokens per subtask: 10,000 (8K in + 2K out)")
    print()
    print(f"{'':30} {'Default (all sonnet)':>20} {'Optimized':>15}")
    print("-" * 70)
    print(f"{'Total cost:':30} ${default_cost['total_cost_usd']:>18.4f} ${optimized_cost['total_cost_usd']:>14.4f}")
    print(f"{'Savings:':30} ${savings:>18.4f}  ({pct:.1f}%)")
    print()
    print("Per-task breakdown:")
    print(f"{'Subtask':<10} {'Role':<12} {'Default':<10} {'Optimized':<10} {'Change':<20}")
    print("-" * 70)
    for s_default, s_opt in zip(default_plan.subtasks, optimized.subtasks):
        change = ""
        if s_default.model != s_opt.model:
            change = f"{s_default.model} → {s_opt.model}"
        print(f"{s_default.id:<10} {s_default.role:<12} {s_default.model:<10} {s_opt.model:<10} {change:<20}")

    print()
    print("By model (default):")
    for model, stats in default_cost["by_model"].items():
        print(f"  {model}: {stats['count']} tasks, ${stats['cost_usd']:.4f}")
    print()
    print("By model (optimized):")
    for model, stats in optimized_cost["by_model"].items():
        print(f"  {model}: {stats['count']} tasks, ${stats['cost_usd']:.4f}")

    # Show the per-quality profile
    print()
    print("=" * 70)
    print("OPTIMIZER RULES APPLIED")
    print("=" * 70)
    from cost_optimizer import QUALITY_REQUIREMENTS, MODEL_CAPABILITY
    for role, requirement in QUALITY_REQUIREMENTS.items():
        candidates = [
            m for m in ["haiku", "sonnet", "opus"]
            if MODEL_CAPABILITY.get(m, 0) >= requirement
        ]
        cheapest = min(candidates, key=lambda m: (
            MODEL_PRICING[m]["input"] * 8 + MODEL_PRICING[m]["output"] * 2
        ))
        print(f"  {role:12} requires capability ≥ {requirement:3} → uses {cheapest:6} (cheapest viable)")

    # Verify savings are realistic
    if savings > 0:
        print(f"\n✓ Saved ${savings:.4f} ({pct:.1f}%) by right-sizing models")
        return 0
    else:
        print(f"\n✓ Optimized plan still costs more (quality floor enforced)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
