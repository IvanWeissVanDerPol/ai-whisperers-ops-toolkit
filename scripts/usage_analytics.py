#!/usr/bin/env python3
"""
usage_analytics.py — Atlas L-1: Aggregate LLM usage from trace files.

Reads ~/.hermes/state/traces/*.jsonl and produces:
  - Per-model breakdown (calls, tokens in/out, cost)
  - Per-provider breakdown
  - Per-day breakdown
  - Per-session (top 10 by cost)
  - Cache hit rate
  - Latency stats (p50, p95, p99)
  - Hourly heatmap (calls per hour-of-day)

Outputs JSON or human-readable text.

Usage:
  python3 usage_analytics.py                  # last 7 days, human readable
  python3 usage_analytics.py --days 30        # last 30 days
  python3 usage_analytics.py --json           # JSON output
  python3 usage_analytics.py --top-sessions 10
  python3 usage_analytics.py --by-day         # show daily breakdown
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRACES_DIR = Path("/root/.hermes/state/traces")


def load_traces(days: int) -> list[dict]:
    """Load traces from the last N days."""
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
        except Exception as e:
            print(f"Warning: failed to read {trace_file}: {e}", file=sys.stderr)
    return traces


def aggregate(traces: list[dict]) -> dict:
    """Aggregate traces into multiple breakdowns."""
    by_model: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0, "tokens_cache_read": 0,
        "cost_usd": 0.0, "latency_sum": 0.0, "latencies": [],
    })
    by_provider: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
    })
    by_day: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
    })
    by_session: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        "first_at": None, "last_at": None,
    })
    by_hour: dict[int, int] = defaultdict(int)
    by_logger: dict[str, int] = defaultdict(int)
    all_latencies = []
    total_cost = 0.0
    total_calls = 0
    total_in = 0
    total_out = 0
    total_cache_read = 0
    total_cache_unread = 0
    cache_hits = 0

    for t in traces:
        model = t.get("model", "unknown")
        provider = t.get("provider", "unknown")
        ts = t.get("_ts")
        day = ts.strftime("%Y-%m-%d") if ts else "unknown"
        hour = ts.hour if ts else 0
        logger = t.get("logger", "unknown")
        tokens_in = t.get("tokens_in", 0)
        tokens_out = t.get("tokens_out", 0)
        cost = t.get("cost_usd", 0.0)
        latency = t.get("latency_seconds", 0.0)
        cache_read = t.get("tokens_cache_read", 0)
        cache_unread = t.get("tokens_cache_unread", 0)
        cache_pct = t.get("cache_pct", 0)
        session = t.get("session", "unknown")

        by_model[model]["calls"] += 1
        by_model[model]["tokens_in"] += tokens_in
        by_model[model]["tokens_out"] += tokens_out
        by_model[model]["tokens_cache_read"] += cache_read
        by_model[model]["cost_usd"] += cost
        by_model[model]["latency_sum"] += latency
        by_model[model]["latencies"].append(latency)

        by_provider[provider]["calls"] += 1
        by_provider[provider]["tokens_in"] += tokens_in
        by_provider[provider]["tokens_out"] += tokens_out
        by_provider[provider]["cost_usd"] += cost

        by_day[day]["calls"] += 1
        by_day[day]["tokens_in"] += tokens_in
        by_day[day]["tokens_out"] += tokens_out
        by_day[day]["cost_usd"] += cost

        by_session[session]["calls"] += 1
        by_session[session]["tokens_in"] += tokens_in
        by_session[session]["tokens_out"] += tokens_out
        by_session[session]["cost_usd"] += cost
        if by_session[session]["first_at"] is None or (ts and ts.isoformat() < by_session[session]["first_at"]):
            by_session[session]["first_at"] = ts.isoformat() if ts else None
        if by_session[session]["last_at"] is None or (ts and ts.isoformat() > by_session[session]["last_at"]):
            by_session[session]["last_at"] = ts.isoformat() if ts else None

        by_hour[hour] += 1
        by_logger[logger] += 1
        all_latencies.append(latency)

        if cache_pct >= 50:
            cache_hits += 1

        total_cost += cost
        total_calls += 1
        total_in += tokens_in
        total_out += tokens_out
        total_cache_read += cache_read
        total_cache_unread += cache_unread

    # Compute latency percentiles
    p50 = p95 = p99 = 0.0
    if all_latencies:
        sorted_lat = sorted(all_latencies)
        n = len(sorted_lat)
        p50 = sorted_lat[n // 2] if n > 0 else 0
        p95 = sorted_lat[int(n * 0.95)] if n > 0 else 0
        p99 = sorted_lat[int(n * 0.99)] if n > 0 else 0

    # Clean up latencies list (don't include in JSON)
    for m in by_model.values():
        del m["latencies"]
        m["avg_latency"] = m["latency_sum"] / m["calls"] if m["calls"] else 0
        del m["latency_sum"]

    return {
        "summary": {
            "total_calls": total_calls,
            "total_tokens_in": total_in,
            "total_tokens_out": total_out,
            "total_cost_usd": round(total_cost, 4),
            "cache_hit_rate_pct": round(100 * cache_hits / total_calls, 1) if total_calls else 0,
            "latency_p50_seconds": round(p50, 2),
            "latency_p95_seconds": round(p95, 2),
            "latency_p99_seconds": round(p99, 2),
            "period_days": len(by_day),
            "models_used": len(by_model),
        },
        "by_model": dict(by_model),
        "by_provider": dict(by_provider),
        "by_day": dict(sorted(by_day.items())),
        "by_hour": {str(h): c for h, c in sorted(by_hour.items())},
        "by_logger": dict(by_logger),
        "top_sessions": sorted(
            [{"session": s, **v} for s, v in by_session.items()],
            key=lambda x: x["cost_usd"],
            reverse=True,
        )[:10],
    }


def format_human(data: dict, top_sessions_n: int = 10) -> str:
    """Format analytics as human-readable text."""
    s = data["summary"]
    lines = [
        "=== Usage Analytics ===",
        "",
        f"Period:         {s['period_days']} day(s)",
        f"Total calls:    {s['total_calls']:,}",
        f"Tokens in:      {s['total_tokens_in']:,}",
        f"Tokens out:     {s['total_tokens_out']:,}",
        f"Cost (USD):     ${s['total_cost_usd']:.4f}",
        f"Cache hit rate: {s['cache_hit_rate_pct']}%",
        f"Latency p50/p95/p99: {s['latency_p50_seconds']}s / {s['latency_p95_seconds']}s / {s['latency_p99_seconds']}s",
        f"Models used:    {s['models_used']}",
        "",
        "--- By Model ---",
    ]
    for model, stats in sorted(data["by_model"].items(), key=lambda x: -x[1]["calls"]):
        lines.append(
            f"  {model:30} calls={stats['calls']:>4} "
            f"in={stats['tokens_in']:>9,} out={stats['tokens_out']:>6,} "
            f"cost=${stats['cost_usd']:.4f} avg_lat={stats['avg_latency']:.1f}s"
        )

    lines.extend(["", "--- By Provider ---"])
    for prov, stats in sorted(data["by_provider"].items(), key=lambda x: -x[1]["calls"]):
        lines.append(
            f"  {prov:25} calls={stats['calls']:>4} "
            f"cost=${stats['cost_usd']:.4f}"
        )

    lines.extend(["", "--- By Day ---"])
    for day, stats in data["by_day"].items():
        lines.append(
            f"  {day}  calls={stats['calls']:>4} "
            f"cost=${stats['cost_usd']:.4f}"
        )

    lines.extend(["", f"--- Top {top_sessions_n} Sessions by Cost ---"])
    for sess in data["top_sessions"][:top_sessions_n]:
        lines.append(
            f"  {sess['session'][:24]:24} calls={sess['calls']:>3} "
            f"cost=${sess['cost_usd']:.4f}"
        )

    lines.extend(["", "--- Hourly Heatmap (UTC) ---"])
    max_count = max(data["by_hour"].values()) if data["by_hour"] else 1
    for h in range(24):
        c = data["by_hour"].get(str(h), 0)
        bar_len = int(40 * c / max_count) if max_count else 0
        bar = "█" * bar_len
        lines.append(f"  {h:02d}:00  {c:>4} {bar}")

    lines.extend(["", "--- By Logger ---"])
    for logger, count in sorted(data["by_logger"].items(), key=lambda x: -x[1]):
        lines.append(f"  {logger:40} {count:>5}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7, help="Look back N days (default 7)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--top-sessions", type=int, default=10, help="Number of top sessions to show")
    args = parser.parse_args()

    traces = load_traces(args.days)
    if not traces:
        print(f"No traces found in the last {args.days} day(s) in {TRACES_DIR}")
        return 0

    data = aggregate(traces)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(format_human(data, args.top_sessions))

    return 0


if __name__ == "__main__":
    sys.exit(main())
