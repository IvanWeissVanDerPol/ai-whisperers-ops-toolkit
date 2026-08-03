#!/usr/bin/env python3
"""
trace_skill_analytics.py — R17-9: Post-hoc skill tagging from trace metadata.

Traces don't have explicit skill names, but session IDs follow patterns:
  - cron_<job_id>_<date>     → cron job (look up name via hermes cron)
  - YYYYMMDD_HHMMSS_<hash>   → user session (no skill)

For cron sessions, we can tag each call with the cron job's script (proxy for skill).

Builds per-skill usage:
  - calls
  - tokens_in, tokens_out
  - cost
  - latency stats
  - cache hit rate

Usage:
  python3 trace_skill_analytics.py                  # human-readable
  python3 trace_skill_analytics.py --days 30        # look back N days
  python3 trace_skill_analytics.py --json           # JSON output
  python3 trace_skill_analytics.py --by-skill       # group by skill (cron name)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRACES_DIR = Path("/root/.hermes/state/traces")


def load_cron_jobs() -> dict:
    """Build a map of cron job_id -> name + script."""
    try:
        r = subprocess.run(["hermes", "cron", "list"], capture_output=True, text=True, timeout=15)
        jobs = {}
        current_id = None
        current_name = None
        current_script = None
        for line in r.stdout.split("\n"):
            line = line.rstrip()
            # New job: id + status (with possible leading whitespace)
            m = re.match(r"^\s*(\w{10,})\s+\[(\w+)\]", line)
            if m:
                if current_id:
                    jobs[current_id] = {"name": current_name, "script": current_script}
                current_id = m.group(1)
                current_name = None
                current_script = None
                continue
            # Strip leading whitespace for Name/Script matching
            stripped = line.strip()
            if stripped.startswith("Name:") and current_id:
                current_name = stripped.split("Name:", 1)[1].strip()
            elif stripped.startswith("Script:") and current_id:
                current_script = stripped.split("Script:", 1)[1].strip()
        if current_id:
            jobs[current_id] = {"name": current_name, "script": current_script}
        return jobs
    except Exception as e:
        print(f"Warning: failed to load cron jobs: {e}", file=sys.stderr)
        return {}


def load_traces(days: int) -> list[dict]:
    """Load recent traces."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    traces = []
    if not TRACES_DIR.exists():
        return traces
    for trace_file in sorted(TRACES_DIR.glob("*.jsonl")):
        try:
            with open(trace_file) as f:
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
                    d["_ts"] = ts
                    traces.append(d)
        except Exception:
            pass
    return traces


def tag_skill(session: str, cron_jobs: dict) -> str:
    """Extract skill/cron name from session ID."""
    # Format observed: cron_<10-char-id>_<date>
    # Cron list IDs are 10-12 chars; match the prefix
    m = re.match(r"^cron_(\w{10,14})_", session)
    if m:
        # Try exact match first, then prefix match (cron list uses 10-12 char IDs)
        job_id = m.group(1)
        if job_id in cron_jobs:
            return cron_jobs[job_id].get("name", f"cron:{job_id[:8]}")
        # Try prefix match
        for cid, job in cron_jobs.items():
            if cid.startswith(job_id[:10]) or job_id.startswith(cid[:10]):
                return job.get("name", f"cron:{cid[:8]}")
        return f"unknown_cron:{job_id[:10]}"
    # User sessions
    if re.match(r"^\d{8}_\d{6}_", session):
        return "user_session"
    return f"other:{session[:16]}"


def aggregate(traces: list[dict], cron_jobs: dict) -> dict:
    """Aggregate by skill/cron name."""
    by_skill: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        "latencies": [], "cache_hits": 0,
    })
    for t in traces:
        session = t.get("session", "")
        skill = tag_skill(session, cron_jobs)
        s = by_skill[skill]
        s["calls"] += 1
        s["tokens_in"] += t.get("tokens_in", 0)
        s["tokens_out"] += t.get("tokens_out", 0)
        s["cost_usd"] += t.get("cost_usd", 0.0)
        s["latencies"].append(t.get("latency_seconds", 0.0))
        if t.get("cache_pct", 0) >= 50:
            s["cache_hits"] += 1

    # Add stats
    result = []
    for name, s in sorted(by_skill.items()):
        lats = s.pop("latencies")
        result.append({
            "skill": name,
            "calls": s["calls"],
            "tokens_in": s["tokens_in"],
            "tokens_out": s["tokens_out"],
            "cost_usd": round(s["cost_usd"], 4),
            "avg_latency": round(sum(lats) / len(lats), 2) if lats else 0,
            "p95_latency": round(sorted(lats)[int(len(lats) * 0.95)], 2) if lats else 0,
            "cache_hit_rate": round(100 * s["cache_hits"] / s["calls"], 1) if s["calls"] else 0,
        })

    return {
        "summary": {
            "total_skills": len(result),
            "total_calls": sum(r["calls"] for r in result),
            "total_cost": round(sum(r["cost_usd"] for r in result), 4),
        },
        "by_skill": result,
    }


def format_human(data: dict) -> str:
    """Format as readable text."""
    s = data["summary"]
    lines = [
        "=== Skill/Cron Usage Analytics ===",
        "",
        f"Skills identified: {s['total_skills']}",
        f"Total calls:       {s['total_calls']:,}",
        f"Total cost (USD):  ${s['total_cost']:.4f}",
        "",
        f"{'Skill':40} {'Calls':>6} {'Tokens in':>11} {'Tokens out':>11} "
        f"{'Cost':>9} {'Avg lat':>8} {'P95 lat':>8} {'Cache%':>7}",
        "-" * 110,
    ]
    for r in data["by_skill"]:
        lines.append(
            f"{r['skill'][:40]:40} {r['calls']:>6} {r['tokens_in']:>11,} "
            f"{r['tokens_out']:>11,} ${r['cost_usd']:>7.4f} "
            f"{r['avg_latency']:>7.1f}s {r['p95_latency']:>7.1f}s {r['cache_hit_rate']:>6}%"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7, help="Look back N days")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--by-skill", action="store_true", help="Group by skill (default)")
    args = parser.parse_args()

    cron_jobs = load_cron_jobs()
    traces = load_traces(args.days)
    if not traces:
        print(f"No traces found in last {args.days} days")
        return 0

    data = aggregate(traces, cron_jobs)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_human(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())