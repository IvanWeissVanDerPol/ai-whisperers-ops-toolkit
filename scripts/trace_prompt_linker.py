#!/usr/bin/env python3
"""
trace_prompt_linker.py — R20-2: Link traces to their source prompts.

Traces have session_id; cron jobs have prompts. This link means:
  - For each cron, we can compute prompt-specific metrics (calls, error rate, cost, latency)
  - For each prompt version, we can measure quality
  - When a prompt is updated, we can A/B test by comparing metrics between versions

Linkage strategy:
  1. session_id for cron traces starts with "cron_<id>_<date>"
  2. Match the cron_id to jobs.json
  3. For each cron, identify the prompt (either from prompt_registry or extract from jobs.json)
  4. Aggregate metrics per prompt

Output:
  - Human-readable table: prompt name, calls, error rate, cost, latency
  - JSON: same data, machine-readable

Usage:
  python3 trace_prompt_linker.py                 # last 7 days
  python3 trace_prompt_linker.py --days 30
  python3 trace_prompt_linker.py --json
  python3 trace_prompt_linker.py --prompt seo-client-ranking-audit
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRACES_DIR = Path("/root/.hermes/state/traces")
JOBS_PATH = Path("/root/.hermes/cron/jobs.json")
PROMPTS_DIR = Path("/root/.hermes/state/prompts")


def load_traces(days_back: int) -> list[dict]:
    """Load traces from the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    traces = []
    if not TRACES_DIR.exists():
        return traces
    for tf in sorted(TRACES_DIR.glob("*.jsonl")):
        try:
            file_date = datetime.strptime(tf.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff - timedelta(days=1):
                continue
        except Exception:
            continue
        with open(tf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts_str = d.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    continue
                if ts < cutoff:
                    continue
                traces.append(d)
    return traces


def load_cron_jobs() -> dict:
    """Load cron jobs as {id: job}."""
    if not JOBS_PATH.exists():
        return {}
    data = json.loads(JOBS_PATH.read_text())
    return {j.get("id"): j for j in data.get("jobs", [])}


def load_prompt_registry() -> dict:
    """Load registered prompts as {name: {version, content, ...}}."""
    registry = {}
    if not PROMPTS_DIR.exists():
        return registry
    for p in PROMPTS_DIR.iterdir():
        if not p.is_dir():
            continue
        meta_path = p / "_meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        # Get the latest version
        latest = meta.get("latest")
        if not latest:
            continue
        # Try stable tag first
        if "tags" in meta and "stable" in meta["tags"]:
            latest = meta["tags"]["stable"].get("version", latest)
        version_path = p / f"{latest}.md"
        if not version_path.exists():
            continue
        content = version_path.read_text()
        registry[meta["name"]] = {
            "version": latest,
            "content": content,
            "size_bytes": len(content),
            "tags": meta.get("tags", {}),
        }
    return registry


def link_traces_to_prompts(traces: list[dict], cron_jobs: dict) -> dict:
    """For each cron, aggregate trace metrics."""
    # Match: session_id "cron_<id>_<date>" → cron_id
    metrics: dict[str, dict] = defaultdict(lambda: {
        "calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "latencies": [],
        "errors": 0,
        "models": set(),
        "providers": set(),
        "timestamps": [],
    })

    # Also track unlinked prompts (heuristic)
    for trace in traces:
        session = trace.get("session", "")
        m = re.match(r"^cron_([a-z0-9]+)_", session)
        if not m:
            continue
        cron_id_prefix = m.group(1)
        # Find the matching cron
        target_id = None
        for jid in cron_jobs:
            if jid.startswith(cron_id_prefix):
                target_id = jid
                break
        if not target_id:
            continue
        job = cron_jobs[target_id]
        if not job.get("prompt") or job.get("no_agent"):
            continue

        prompt_name = extract_prompt_name(job)
        if not prompt_name:
            continue

        m = metrics[prompt_name]
        m["calls"] += 1
        m["tokens_in"] += trace.get("tokens_in", 0)
        m["tokens_out"] += trace.get("tokens_out", 0)
        m["cost_usd"] += trace.get("cost_usd", 0.0)
        m["latencies"].append(trace.get("latency_seconds", 0.0))
        m["models"].add(trace.get("model", ""))
        m["providers"].add(trace.get("provider", ""))
        m["timestamps"].append(trace.get("timestamp", ""))
        # Heuristic: empty output + cost > 0 = error
        if (trace.get("tokens_out") or 0) == 0 and (trace.get("cost_usd") or 0) > 0:
            m["errors"] += 1

    # Convert to final dict
    result = {}
    for prompt_name, m in metrics.items():
        lats = sorted(m["latencies"])
        p50 = lats[len(lats) // 2] if lats else 0
        p95 = lats[int(len(lats) * 0.95)] if lats else 0
        error_rate = m["errors"] / max(m["calls"], 1)
        result[prompt_name] = {
            "calls": m["calls"],
            "tokens_in": m["tokens_in"],
            "tokens_out": m["tokens_out"],
            "cost_usd": round(m["cost_usd"], 4),
            "latency_p50": round(p50, 2),
            "latency_p95": round(p95, 2),
            "errors": m["errors"],
            "error_rate": round(error_rate, 3),
            "models": sorted(m["models"]),
            "providers": sorted(m["providers"]),
            "first_seen": min(m["timestamps"]) if m["timestamps"] else None,
            "last_seen": max(m["timestamps"]) if m["timestamps"] else None,
        }
    return result


def extract_prompt_name(job: dict) -> str | None:
    """Derive a prompt name from a cron job."""
    # Use the cron name's normalized form
    name = job.get("name", "")
    if not name:
        return None
    # Prefer registry name if it matches
    # Otherwise use normalized cron name
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def compute_quality_score(metrics: dict) -> float:
    """Compute a quality score 0-100 based on metrics.
    Higher = better.
    Score = 100 - (error_rate*40) - (cost_per_call*5) - (latency_p95/100*10)
    """
    calls = metrics.get("calls", 0)
    if calls == 0:
        return 0
    error_rate = metrics.get("error_rate", 0)
    cost = metrics.get("cost_usd", 0)
    cost_per_call = cost / calls
    p95 = metrics.get("latency_p95", 0)
    score = 100 - (error_rate * 40) - (cost_per_call * 5) - (p95 / 100 * 10)
    return max(0, min(100, round(score, 1)))


def format_human(linked: dict, registry: dict, days: int) -> str:
    lines = [
        "=== Trace → Prompt Linker ===",
        "",
        f"Period:          last {days} days",
        f"Prompts tracked: {len(linked)}",
        f"Registered:      {len(registry)}",
        "",
    ]

    # Sort by cost (highest spenders first)
    sorted_prompts = sorted(linked.items(), key=lambda x: x[1]["cost_usd"], reverse=True)
    for prompt_name, m in sorted_prompts:
        quality = compute_quality_score(m)
        in_registry = "✓" if prompt_name in registry else "✗"
        reg_ver = registry.get(prompt_name, {}).get("version", "—")
        calls = m["calls"]
        cost = m["cost_usd"]
        err = m["error_rate"] * 100
        p95 = m["latency_p95"]

        # Quality emoji
        if quality >= 80:
            qmark = "🟢"
        elif quality >= 50:
            qmark = "🟡"
        else:
            qmark = "🔴"

        lines.append(f"  {qmark} {in_registry} {prompt_name[:40]:40} v{reg_ver}")
        lines.append(f"      calls: {calls:>4}  cost: ${cost:>6.2f}  err: {err:>5.1f}%  p95: {p95:>5.1f}s  score: {quality}")
        if m["models"]:
            lines.append(f"      model: {m['models'][0]}")

    # Show un-registered prompts
    unreg = [p for p in linked if p not in registry]
    if unreg:
        lines.append("")
        lines.append(f"  ⚠ {len(unreg)} prompt(s) NOT in registry — consider registering:")
        for p in unreg:
            lines.append(f"    - {p}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7, help="Look back N days")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--prompt", help="Show only this prompt")
    args = parser.parse_args()

    traces = load_traces(args.days)
    cron_jobs = load_cron_jobs()
    registry = load_prompt_registry()

    if not traces:
        print(f"No traces found in the last {args.days} days")
        return 0

    linked = link_traces_to_prompts(traces, cron_jobs)

    if args.prompt:
        if args.prompt not in linked:
            print(f"Prompt '{args.prompt}' not found in traces")
            return 1
        linked = {args.prompt: linked[args.prompt]}

    if args.json:
        print(json.dumps({
            "days": args.days,
            "traces_total": len(traces),
            "cron_jobs_total": len(cron_jobs),
            "registry_total": len(registry),
            "linked": linked,
            "registry": {k: v["version"] for k, v in registry.items()},
        }, indent=2, default=str))
    else:
        print(format_human(linked, registry, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
