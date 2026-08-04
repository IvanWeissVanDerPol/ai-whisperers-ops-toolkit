#!/usr/bin/env python3
"""
swarm/llm_reflection.py — LLM-driven reflection summaries (Atlas C-2 upgrade).

Heuristic reflections catch obvious patterns (retries > 0, failures > 0)
but miss the WHY behind them. This module asks an LLM to analyze the same
data and generate **deep insights**:

- What went well / what didn't
- Why the failed subtasks failed (if log entries have hints)
- What to try differently next time
- Patterns that span multiple runs

Strategy:
- Send the run summary + log entries (compact) as a structured prompt
- Ask for 3-5 actionable insights in JSON format
- Fall back to heuristic reflections if no API key

CLI:
    python3 llm_reflection.py reflect --memory-dir /tmp/swarm-state/run-123
    python3 llm_reflection.py reflect --reflection-log ~/.hermes/state/reflections.jsonl
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).parent))
from shared_memory import SharedMemory  # noqa: E402
from reflection_loop import extract_lessons_from_run, ReflectionLog  # noqa: E402

REFLECTION_PROMPT = """You are analyzing a completed swarm run for actionable insights.

Swarm run summary:
{summary}

Heuristic lessons already extracted:
{heuristic_lessons}

Recent log entries (last 30):
{recent_logs}

Generate 3-5 deep insights. Each insight should be:
- ACTIONABLE (suggest a specific change to make next time)
- SPECIFIC (reference actual subtasks, retries, or failures)
- CONCISE (1-2 sentences)

Return a JSON array with this structure:
[
  {{
    "category": "failure_pattern" | "success_pattern" | "process_improvement" | "tooling_issue",
    "insight": "The specific insight here",
    "suggestion": "What to do differently next time",
    "confidence": "low" | "medium" | "high"
  }}
]

Be honest: if the run was straightforward, say so. Don't invent issues.
Output ONLY valid JSON (no markdown code blocks, no prose around it)."""


def get_openai_client():
    """Get OpenAI client if API key is set."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import openai
        return openai.OpenAI(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    except ImportError:
        return None


def build_summary_for_prompt(memory_dir: Path) -> str:
    """Build a compact summary suitable for the LLM prompt."""
    memory = SharedMemory(memory_dir)
    log = memory.read_log()
    if not log:
        return "No log entries found."

    # Aggregate stats
    plan_finished = None
    started = 0
    finished = 0
    retries = 0
    escalations = 0
    failures = 0
    successes = 0
    for e in log:
        if e.get("event") == "plan_started":
            started += 1
        elif e.get("event") == "plan_finished":
            finished += 1
            plan_finished = e.get("payload", {})
        elif e.get("event") == "retry_added":
            retries += 1
        elif e.get("event") == "escalation_added":
            escalations += 1
        elif e.get("event") == "subtask_finished":
            status = e.get("payload", {}).get("status", "")
            if status == "failed":
                failures += 1
            elif status == "succeeded":
                successes += 1

    plan = memory.read("plan")
    goal = plan.get("goal", "unknown") if isinstance(plan, dict) else "unknown"

    lines = [
        f"Goal: {goal}",
        f"Started: {started} plan, Finished: {finished} plan",
        f"Subtasks: {successes} succeeded, {failures} failed",
        f"Retries: {retries}",
        f"Escalations: {escalations}",
    ]
    if plan_finished:
        lines.append(f"Final summary: {json.dumps(plan_finished, default=str)}")
    return "\n".join(lines)


def build_recent_logs_for_prompt(memory_dir: Path, limit: int = 30) -> str:
    """Get last N log entries, formatted compactly."""
    memory = SharedMemory(memory_dir)
    log = memory.read_log()
    if not log:
        return ""
    lines = []
    for e in log[-limit:]:
        ts = e.get("ts", "?")
        agent = e.get("agent_id", "?")[:20]
        event = e.get("event", "?")
        payload = e.get("payload", {})
        # Compact: skip noisy events
        if event in ("started", "completed", "subtask_launched"):
            continue
        lines.append(f"[{ts}] {agent}/{event}: {json.dumps(payload, default=str)[:200]}")
    return "\n".join(lines)


def generate_llm_insights(
    memory_dir: Union[str, Path],
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Generate LLM-driven insights from a swarm run.

    Returns list of insight dicts (each with category/insight/suggestion/confidence).
    Returns [] if no API key available.
    """
    client = get_openai_client()
    if client is None:
        return []
    memory_dir = Path(memory_dir)
    summary = build_summary_for_prompt(memory_dir)
    heuristic_lessons = extract_lessons_from_run(memory_dir)
    recent_logs = build_recent_logs_for_prompt(memory_dir)
    prompt = REFLECTION_PROMPT.format(
        summary=summary,
        heuristic_lessons=json.dumps(heuristic_lessons, indent=2, default=str)[:3000],
        recent_logs=recent_logs[:3000],
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You generate concise, actionable insights about swarm runs."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"} if "gpt-4" in model else None,
        )
        content = response.choices[0].message.content.strip()
        # Try to parse as JSON object or array
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "insights" in parsed:
                return parsed["insights"]
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            # Try to extract JSON from text
            import re
            m = re.search(r"\[.*\]", content, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        return []
    except Exception as e:
        return [{"error": f"LLM call failed: {str(e)[:200]}"}]


def add_llm_insights_to_log(
    memory_dir: Union[str, Path],
    reflection_log: ReflectionLog,
    model: str = "gpt-4o-mini",
) -> int:
    """Generate LLM insights and append them to the reflection log.

    Returns number of insights added (0 if no API key or call failed).
    """
    insights = generate_llm_insights(memory_dir, model=model)
    if not insights:
        return 0
    lessons = []
    for insight in insights:
        lessons.append({
            "type": "llm_insight",
            "category": insight.get("category", "unknown"),
            "insight": insight.get("insight", ""),
            "suggestion": insight.get("suggestion", ""),
            "confidence": insight.get("confidence", "medium"),
            "model": model,
            "memory_dir": str(memory_dir),
        })
    return reflection_log.add(lessons)


def main():
    """CLI: generate LLM insights for a swarm run."""
    import argparse
    p = argparse.ArgumentParser(description="LLM-driven reflection")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_reflect = sub.add_parser("reflect", help="Generate insights for a run")
    p_reflect.add_argument("--memory-dir", required=True)
    p_reflect.add_argument("--log-path", default=None, help="Reflection log path")
    p_reflect.add_argument("--model", default="gpt-4o-mini")
    p_reflect.add_argument("--print-only", action="store_true", help="Don't save, just print")

    args = p.parse_args()
    if not get_openai_client():
        print("✗ No OPENAI_API_KEY set. Cannot generate LLM insights.")
        print("  Set OPENAI_API_KEY env var to enable.")
        print("  Use swarm/reflection_loop.py for heuristic-only reflections.")
        sys.exit(1)
    insights = generate_llm_insights(args.memory_dir, model=args.model)
    if not insights:
        print("No insights generated (empty result or error).")
        sys.exit(0)
    if args.print_only:
        print(json.dumps(insights, indent=2))
    else:
        log = ReflectionLog(log_path=args.log_path) if args.log_path else ReflectionLog()
        n = log.add([{
            "type": "llm_insight",
            "category": i.get("category", "unknown"),
            "insight": i.get("insight", ""),
            "suggestion": i.get("suggestion", ""),
            "confidence": i.get("confidence", "medium"),
            "model": args.model,
            "memory_dir": args.memory_dir,
        } for i in insights])
        print(f"Added {n} LLM insights to {log.log_path}")
        for i in insights:
            print(f"\n  [{i.get('category')}] (confidence: {i.get('confidence')})")
            print(f"    {i.get('insight')}")
            print(f"    → {i.get('suggestion')}")


if __name__ == "__main__":
    main()