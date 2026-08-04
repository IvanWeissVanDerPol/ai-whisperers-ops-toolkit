#!/usr/bin/env python3
"""
swarm/reflection_loop.py — Atlas C-2: Swarm self-improvement loop.

After each swarm run, this module extracts "lessons learned" and stores them
in a dedicated reflection log. Future swarm runs can query this log to avoid
repeating the same mistakes.

Three types of reflection:
1. **Per-subtask lessons**: what worked / what failed for each role
2. **Per-plan patterns**: common task structures that succeeded
3. **Cross-run observations**: aggregated stats over many runs

Stored in a JSONL file (one JSON object per line):
- Easy to grep / append
- Easy to convert to a vector store index later
- Easy to ship to a memory file or commit

Usage:
    from reflection_loop import ReflectionLog, extract_lessons_from_run
    log = ReflectionLog("~/.hermes/state/reflections.jsonl")
    lessons = extract_lessons_from_run(memory_dir)
    log.add(lessons)
    # Later:
    relevant = log.query("how to handle auth retries", top_k=3)
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).parent))
from shared_memory import SharedMemory  # noqa: E402


DEFAULT_LOG = Path("~/.hermes/state/reflections.jsonl").expanduser()


def extract_lessons_from_run(memory_dir: Union[str, Path]) -> list[dict]:
    """Extract lessons learned from a swarm run.

    Looks at the run's memory log + snapshots + blackboard to generate
    structured observations:
    - Which subtasks succeeded / failed
    - Patterns in retry counts (high retries = something was hard)
    - Cost data per role
    - Subtasks that escalated (hints at complexity)
    """
    memory_dir = Path(memory_dir)
    if not memory_dir.exists():
        return []
    memory = SharedMemory(memory_dir)
    lessons = []
    run_goal = None

    # Get run goal + metadata
    try:
        plan = memory.read("plan")
        if isinstance(plan, dict):
            run_goal = plan.get("goal", "unknown")
    except Exception:
        pass

    # Find retries + escalations + failures
    log = memory.read_log()
    subtask_results: dict[str, dict] = {}
    for e in log:
        if e.get("event") in ("subtask_finished", "subtask_launched", "retry_added",
                              "escalation_added", "plan_finished"):
            payload = e.get("payload", {})
            sid = payload.get("id") or payload.get("subtask_id", "")
            if not sid:
                continue
            if sid not in subtask_results:
                subtask_results[sid] = {
                    "agent_id": e.get("agent_id"),
                    "events": [],
                }
            subtask_results[sid]["events"].append(e)

    # Build lessons per subtask
    for sid, info in subtask_results.items():
        status = None
        role = None
        retries = 0
        escalated = False
        for ev in info["events"]:
            if ev.get("event") == "subtask_launched":
                # role is in agent_id? No, it is in payload as role from swarm
                pass
            if ev.get("event") == "subtask_finished":
                status = ev.get("payload", {}).get("status")
                role = ev.get("role") or info["agent_id"]  # fallback
            if ev.get("event") == "retry_added":
                retries += 1
            if ev.get("event") == "escalation_added":
                escalated = True
        if status:
            lessons.append({
                "type": "subtask_outcome",
                "subtask_id": sid,
                "role": role,
                "status": status,
                "retries": retries,
                "escalated": escalated,
                "run_goal": run_goal,
            })

    # Summarize the overall run
    successes = sum(1 for l in lessons if l.get("status") == "succeeded")
    failures = sum(1 for l in lessons if l.get("status") == "failed")
    skipped = sum(1 for l in lessons if l.get("status") == "skipped")
    total_retries = sum(l.get("retries", 0) for l in lessons)
    n_escalations = sum(1 for l in lessons if l.get("escalated"))

    summary = {
        "type": "run_summary",
        "run_goal": run_goal,
        "n_subtasks": len(lessons),
        "succeeded": successes,
        "failed": failures,
        "skipped": skipped,
        "total_retries": total_retries,
        "n_escalations": n_escalations,
        "memory_dir": str(memory_dir),
    }
    lessons.insert(0, summary)

    # Extract simple heuristic lessons based on patterns
    if failures > 0:
        lessons.append({
            "type": "observation",
            "observation": f"Run had {failures} failures out of {len(lessons)-1} subtasks",
            "pattern": "failures_present",
        })
    if total_retries > 0:
        lessons.append({
            "type": "observation",
            "observation": f"Run required {total_retries} retries (consider lower timeouts or clearer tasks)",
            "pattern": "retries_present",
        })
    if n_escalations > 0:
        lessons.append({
            "type": "observation",
            "observation": f"Run had {n_escalations} escalations (some tasks may need review early)",
            "pattern": "escalations_present",
        })

    return lessons


class ReflectionLog:
    """Append-only log of lessons learned from swarm runs."""

    def __init__(self, log_path: Union[str, Path] = DEFAULT_LOG):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def add(self, lessons: list[dict]) -> int:
        """Append lessons to the log. Returns count added."""
        if not lessons:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        with open(self.log_path, "a") as f:
            for lesson in lessons:
                if "timestamp" not in lesson:
                    lesson["timestamp"] = now
                f.write(json.dumps(lesson) + "\n")
        return len(lessons)

    def query(
        self,
        pattern: Optional[str] = None,
        lesson_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query reflection log by pattern or type."""
        results = []
        with open(self.log_path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    lesson = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if lesson_type and lesson.get("type") != lesson_type:
                    continue
                if pattern and pattern.lower() not in json.dumps(lesson).lower():
                    continue
                results.append(lesson)
        # Newest first
        results.reverse()
        return results[:limit]

    def stats(self) -> dict:
        """Aggregate stats across all reflections."""
        all_lessons = []
        with open(self.log_path) as f:
            for line in f:
                if line.strip():
                    try:
                        all_lessons.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        types = {}
        runs = set()
        for l in all_lessons:
            types[l.get("type", "?")] = types.get(l.get("type", "?"), 0) + 1
            if l.get("memory_dir"):
                runs.add(l["memory_dir"])
        return {
            "n_lessons": len(all_lessons),
            "by_type": types,
            "n_runs": len(runs),
            "log_path": str(self.log_path),
        }


def main():
    """CLI: extract lessons from a swarm run, or query past lessons."""
    import argparse
    p = argparse.ArgumentParser(description="Swarm reflection log")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_learn = sub.add_parser("learn", help="Extract lessons from a swarm run")
    p_learn.add_argument("--memory-dir", required=True)

    sub.add_parser("stats", help="Print reflection log stats")

    p_query = sub.add_parser("query", help="Query past reflections")
    p_query.add_argument("--type", help="Filter by lesson type")
    p_query.add_argument("--pattern", help="Substring match across lessons")
    p_query.add_argument("--limit", type=int, default=10)

    args = p.parse_args()
    log = ReflectionLog()
    if args.cmd == "learn":
        lessons = extract_lessons_from_run(args.memory_dir)
        n = log.add(lessons)
        print(f"Added {n} lessons to {log.log_path}")
        # Show summary
        for l in lessons[:3]:
            t = l.get("type", "")
            print(f"  - {t}: {json.dumps(l)[:100]}")
    elif args.cmd == "stats":
        print(json.dumps(log.stats(), indent=2))
    elif args.cmd == "query":
        results = log.query(pattern=args.pattern, lesson_type=args.type, limit=args.limit)
        print(f"Found {len(results)} results:")
        for r in results[:args.limit]:
            t = r.get("type", "?")
            print(f"  [{t}] {json.dumps(r)[:200]}")


if __name__ == "__main__":
    main()
