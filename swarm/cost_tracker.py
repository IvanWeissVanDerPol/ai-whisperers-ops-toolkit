#!/usr/bin/env python3
"""
swarm/cost_tracker.py — Track cost + token usage per worker / per swarm.

When a worker finishes, we extract its tokens + cost from:
1. JSON output (if claude emits it via --output-format=json)
2. llm_tracer (if the swarm is integrated with the broader Hermes tracer)

If neither is available, we estimate based on model + role + duration.

This module provides:
- **Per-worker cost tracking** (model, tokens, cost, duration)
- **Plan-level rollups** (total cost, breakdown by role)
- **Persistence** via shared memory

Usage:
    from cost_tracker import CostTracker
    tracker = CostTracker(memory_dir="/tmp/swarm-state/run-123")
    tracker.record_worker("w-1", "researcher", "haiku", duration_sec=15.0)
    tracker.record_worker("w-2", "coder", "sonnet", duration_sec=120.0,
                         tokens_in=8000, tokens_out=2000, cost_usd=0.15)
    summary = tracker.summary()
    print(summary)
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared_memory import SharedMemory  # noqa: E402


# Approximate costs per 1K tokens (USD) for common models.
# Update as pricing changes.
MODEL_PRICING = {
    "haiku": {"input": 0.00025, "output": 0.00125},
    "sonnet": {"input": 0.003, "output": 0.015},
    "opus": {"input": 0.015, "output": 0.075},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}

# Rough token estimate per second of work (fallback when no token data)
# Based on observation: haiku workers produce ~300 tokens/5sec, sonnet ~500 tokens/10sec
TOKENS_PER_SEC_ESTIMATE = {
    "haiku": 60,
    "sonnet": 50,
    "opus": 40,
}


@dataclass
class WorkerCost:
    """Cost + token record for a single worker invocation."""
    worker_id: str
    role: str
    model: str
    duration_sec: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    timestamp: str = ""
    estimated: bool = False  # True if numbers came from duration estimate

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "role": self.role,
            "model": self.model,
            "duration_sec": round(self.duration_sec, 1),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.tokens_in + self.tokens_out,
            "cost_usd": round(self.cost_usd, 4),
            "estimated": self.estimated,
            "timestamp": self.timestamp,
        }


class CostTracker:
    """Track + aggregate costs across a swarm run."""

    def __init__(self, memory_dir: str | Path):
        self.memory = SharedMemory(memory_dir)
        self.costs: list[WorkerCost] = []
        self.memory_dir = Path(memory_dir)

    def record_worker(
        self,
        worker_id: str,
        role: str,
        model: str,
        duration_sec: float,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> WorkerCost:
        """Record a worker invocation. Estimate missing values from duration."""
        estimated = tokens_in is None or tokens_out is None or cost_usd is None

        if tokens_in is None or tokens_out is None:
            # Estimate: assume 1/3 input, 2/3 output
            rate = TOKENS_PER_SEC_ESTIMATE.get(model, 50)
            total_tokens = int(duration_sec * rate)
            tokens_out = int(total_tokens * 0.4)
            tokens_in = total_tokens - tokens_out

        if cost_usd is None:
            pricing = MODEL_PRICING.get(model)
            if pricing:
                cost_usd = (
                    tokens_in / 1000 * pricing["input"]
                    + tokens_out / 1000 * pricing["output"]
                )
            else:
                cost_usd = 0.0

        cost = WorkerCost(
            worker_id=worker_id,
            role=role,
            model=model,
            duration_sec=duration_sec,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            timestamp=datetime.now(timezone.utc).isoformat(),
            estimated=estimated,
        )
        self.costs.append(cost)
        self.memory.log(worker_id, role, "cost_recorded", cost.to_dict())
        self.memory.publish("worker-cost", cost.to_dict())
        return cost

    def record_from_subprocess_output(
        self,
        worker_id: str,
        role: str,
        model: str,
        duration_sec: float,
        stdout: str,
    ) -> WorkerCost:
        """Try to extract cost + tokens from claude CLI JSON output."""
        tokens_in = None
        tokens_out = None
        cost_usd = None

        # claude CLI JSON output format: {"usage": {"input_tokens": N, "output_tokens": M}, "total_cost_usd": X}
        try:
            data = json.loads(stdout)
            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens", tokens_in)
            tokens_out = usage.get("output_tokens", tokens_out)
            cost_usd = data.get("total_cost_usd", cost_usd)
        except (json.JSONDecodeError, AttributeError):
            pass

        return self.record_worker(
            worker_id, role, model, duration_sec,
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd,
        )

    def summary(self) -> dict:
        """Aggregate summary across all recorded workers.

        Reads costs from in-memory list, falling back to shared memory
        cost_recorded events if the list is empty (different process).
        """
        if not self.costs:
            # Reconstruct from shared memory log
            events = self.memory.read_log(event="cost_recorded")
            for e in events:
                p = e.get("payload", {})
                self.costs.append(WorkerCost(
                    worker_id=p.get("worker_id", ""),
                    role=p.get("role", ""),
                    model=p.get("model", ""),
                    duration_sec=p.get("duration_sec", 0.0),
                    tokens_in=p.get("tokens_in", 0),
                    tokens_out=p.get("tokens_out", 0),
                    cost_usd=p.get("cost_usd", 0.0),
                    timestamp=e.get("ts", ""),
                    estimated=p.get("estimated", False),
                ))
        if not self.costs:
            return {"n_workers": 0}

        by_model: dict[str, dict] = {}
        by_role: dict[str, dict] = {}
        total_cost = 0.0
        total_tokens = 0
        total_duration = 0.0

        for c in self.costs:
            total_cost += c.cost_usd
            total_tokens += c.tokens_in + c.tokens_out
            total_duration += c.duration_sec

            for d, key in [(by_model, c.model), (by_role, c.role)]:
                if key not in d:
                    d[key] = {"count": 0, "cost_usd": 0.0, "tokens": 0, "duration_sec": 0.0}
                d[key]["count"] += 1
                d[key]["cost_usd"] += c.cost_usd
                d[key]["tokens"] += c.tokens_in + c.tokens_out
                d[key]["duration_sec"] += c.duration_sec

        return {
            "n_workers": len(self.costs),
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_duration_sec": round(total_duration, 1),
            "avg_cost_per_worker": round(total_cost / len(self.costs), 4),
            "by_model": {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in by_model.items()},
            "by_role": {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in by_role.items()},
            "n_estimated": sum(1 for c in self.costs if c.estimated),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def save(self) -> None:
        """Persist summary to shared memory."""
        summary = self.summary()
        self.memory.publish("cost-summary", summary)


def main():
    """CLI: simulate or summarize costs."""
    import argparse
    p = argparse.ArgumentParser(description="Cost tracker")
    p.add_argument("--memory-dir", required=True)
    p.add_argument("--record", help="JSON: {worker_id,role,model,duration_sec,tokens_in?,tokens_out?,cost_usd?}")
    p.add_argument("--summary", action="store_true", help="Print current summary")
    args = p.parse_args()

    tracker = CostTracker(args.memory_dir)

    if args.record:
        data = json.loads(args.record)
        cost = tracker.record_worker(**data)
        print(json.dumps(cost.to_dict(), indent=2))
        tracker.save()

    if args.summary:
        summary = tracker.summary()
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()