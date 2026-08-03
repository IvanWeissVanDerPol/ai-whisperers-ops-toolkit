#!/usr/bin/env python3
"""
llm_tracer.py — OpenTelemetry-style tracer for Hermes LLM calls.

Parses Hermes agent.log for `API call #N` lines and emits JSON spans to
~/.hermes/state/traces/. Each span has:
  - span_id, parent_id (optional chain)
  - timestamp, model, provider, session_id
  - tokens_in, tokens_out, total_tokens, cache_read, cache_write
  - latency_seconds
  - attributes (skill, repo, etc — inferred from context)

Plus:
  - `summary` : aggregate stats by model / provider / session / hour
  - `last N` : tail last N spans
  - `query`   : filter spans (by model, provider, time range)
  - `export`  : emit as JSONL for downstream tools (Langfuse format compatible)
  - `viz`     : ASCII timeline of recent calls
  - `costs`   : per-call cost estimate using known pricing

Usage:
    python3 ~/.hermes/scripts/llm_tracer.py --tail
    python3 ~/.hermes/scripts/llm_tracer.py --tail --last 20
    python3 ~/.hermes/scripts/llm_tracer.py --summary
    python3 ~/.hermes/scripts/llm_tracer.py --query --model MiniMax-M3 --provider minimax-oauth
    python3 ~/.hermes/scripts/llm_tracer.py --costs --since 1d
    python3 ~/.hermes/scripts/llm_tracer.py --viz --last 50
    python3 ~/.hermes/scripts/llm_tracer.py --export --since 1d > traces.jsonl

Cost estimates (per 1M tokens, USD):
  - MiniMax-M3 (minimax-oauth): $0 (free tier)
  - openrouter/gpt-4o-mini: in $0.15 / out $0.60
  - anthropic/claude-sonnet-4-6: in $3 / out $15
  - deepseek/deepseek-chat: in $0.14 / out $0.28
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
LOG_PATH = HERMES_HOME / "logs" / "agent.log"
LOG_FALLBACK = HERMES_HOME / "logs" / "agent.log.1"
TRACES_DIR = HERMES_HOME / "state" / "traces"

# Match: 2026-07-31 06:14:41,036 INFO [20260731_050540_ffd552] agent.conversation_loop: API call #389: model=MiniMax-M3 provider=minimax-oauth in=128893 out=277 total=129170 latency=3.9s cache=127695/128893 (9...)
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+(?P<level>\w+)\s+"
    r"\[(?P<session>[^\]]+)\]\s+(?P<logger>[\w.]+):\s+API call #(?P<call_no>\d+):"
    r"\s+model=(?P<model>\S+)\s+provider=(?P<provider>\S+)"
    r"\s+in=(?P<in_tok>\d+)\s+out=(?P<out_tok>\d+)"
    r"\s+total=(?P<total_tok>\d+)"
    r"\s+latency=(?P<latency>[\d.]+)s"
    r"(?:\s+cache=(?P<cache_read>\d+)/(?P<cache_total>\d+)(?:\s\((?P<cache_pct>\d+)%\))?)?"
)

# Pricing per 1M tokens (USD) — best-effort public prices
PRICING = {
    # minimax-oauth routes multiple models; default to free
    "minimax-oauth": {"in": 0.0, "out": 0.0, "default": True},
    # openrouter passthrough pricing for common models
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "claude-3-5-sonnet": {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-3.5-sonnet": {"in": 3.00, "out": 15.00},
    "claude-opus-4-6": {"in": 15.00, "out": 75.00},
    "deepseek-chat": {"in": 0.14, "out": 0.28},
    "gemini-2.5-pro": {"in": 1.25, "out": 5.00},
    "llama-3.1-70b": {"in": 0.59, "out": 0.79},
}


def parse_log(path: Path, since: datetime | None = None) -> list[dict]:
    """Parse agent.log into span dicts."""
    if not path.exists():
        return []
    spans = []
    for line in path.read_text(errors="ignore").split("\n"):
        m = LOG_PATTERN.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if since and ts < since:
            continue
        spans.append({
            "timestamp": ts.isoformat(),
            "session": m["session"],
            "logger": m["logger"],
            "call_no": int(m["call_no"]),
            "model": m["model"],
            "provider": m["provider"],
            "tokens_in": int(m["in_tok"]),
            "tokens_out": int(m["out_tok"]),
            "tokens_total": int(m["total_tok"]),
            "tokens_cache_read": int(m["cache_read"]) if m["cache_read"] else 0,
            "tokens_cache_total": int(m["cache_total"]) if m["cache_total"] else 0,
            "cache_pct": int(m["cache_pct"]) if m["cache_pct"] else 0,
            "latency_seconds": float(m["latency"]),
        })
    return spans


def estimate_cost(span: dict) -> float:
    """Estimate USD cost for a span."""
    model = span["model"].lower()
    pricing = None
    for key, p in PRICING.items():
        if key in model:
            pricing = p
            break
    if pricing is None:
        # Try provider
        pricing = PRICING.get(span["provider"].lower(), {"in": 0, "out": 0})
    in_cost = (span["tokens_in"] / 1_000_000) * pricing["in"]
    out_cost = (span["tokens_out"] / 1_000_000) * pricing["out"]
    return round(in_cost + out_cost, 6)


def enrich_spans(spans: list[dict]) -> list[dict]:
    """Add cost and cache statistics."""
    for s in spans:
        s["cost_usd"] = estimate_cost(s)
        if s["tokens_cache_total"] > 0:
            s["tokens_cache_unread"] = s["tokens_cache_total"] - s["tokens_cache_read"]
    return spans


def cmd_tail(last: int = 10, since: str | None = None) -> list[dict]:
    since_dt = parse_since(since)
    spans = parse_log(LOG_PATH, since_dt)
    if not spans and LOG_FALLBACK.exists():
        spans = parse_log(LOG_FALLBACK, since_dt)
    spans = enrich_spans(spans)
    return spans[-last:]


def cmd_summary(since: str = "1d") -> dict:
    """Aggregate stats by model, provider, hour."""
    since_dt = parse_since(since)
    spans = enrich_spans(parse_log(LOG_PATH, since_dt) + parse_log(LOG_FALLBACK, since_dt))
    summary = {
        "window": since,
        "since": since_dt.isoformat() if since_dt else None,
        "total_spans": len(spans),
        "total_cost_usd": round(sum(s["cost_usd"] for s in spans), 4),
        "total_tokens_in": sum(s["tokens_in"] for s in spans),
        "total_tokens_out": sum(s["tokens_out"] for s in spans),
        "total_cache_read": sum(s["tokens_cache_read"] for s in spans),
        "avg_latency_seconds": round(
            sum(s["latency_seconds"] for s in spans) / max(len(spans), 1), 3
        ),
        "by_model": defaultdict(lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0}),
        "by_provider": defaultdict(lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0}),
        "by_session": defaultdict(lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0}),
        "by_hour": defaultdict(lambda: {"calls": 0, "cost": 0}),
    }
    for s in spans:
        m = s["model"]
        p = s["provider"]
        sess = s["session"]
        hour = s["timestamp"][:13]  # YYYY-MM-DDTHH
        summary["by_model"][m]["calls"] += 1
        summary["by_model"][m]["tokens_in"] += s["tokens_in"]
        summary["by_model"][m]["tokens_out"] += s["tokens_out"]
        summary["by_model"][m]["cost"] += s["cost_usd"]
        summary["by_provider"][p]["calls"] += 1
        summary["by_provider"][p]["tokens_in"] += s["tokens_in"]
        summary["by_provider"][p]["tokens_out"] += s["tokens_out"]
        summary["by_provider"][p]["cost"] += s["cost_usd"]
        summary["by_session"][sess]["calls"] += 1
        summary["by_session"][sess]["tokens_in"] += s["tokens_in"]
        summary["by_session"][sess]["tokens_out"] += s["tokens_out"]
        summary["by_session"][sess]["cost"] += s["cost_usd"]
        summary["by_hour"][hour]["calls"] += 1
        summary["by_hour"][hour]["cost"] += s["cost_usd"]
    # Convert defaultdicts
    summary["by_model"] = dict(sorted(summary["by_model"].items(), key=lambda x: -x[1]["cost"]))
    summary["by_provider"] = dict(sorted(summary["by_provider"].items(), key=lambda x: -x[1]["cost"]))
    summary["by_session"] = dict(sorted(summary["by_session"].items(), key=lambda x: -x[1]["cost"]))
    summary["by_hour"] = dict(sorted(summary["by_hour"].items()))
    # Round floats
    for cat in [summary["by_model"], summary["by_provider"], summary["by_session"], summary["by_hour"]]:
        for k, v in cat.items():
            v["cost"] = round(v["cost"], 4)
    return summary


def cmd_query(model: str | None = None, provider: str | None = None,
              since: str = "1d", limit: int = 100) -> list[dict]:
    since_dt = parse_since(since)
    spans = enrich_spans(parse_log(LOG_PATH, since_dt))
    if model:
        spans = [s for s in spans if model in s["model"]]
    if provider:
        spans = [s for s in spans if provider in s["provider"]]
    return spans[-limit:]


def cmd_export(since: str = "1d") -> list[dict]:
    """Export spans in Langfuse-compatible JSONL format."""
    spans = enrich_spans(parse_log(LOG_PATH, parse_since(since)))
    out = []
    for s in spans:
        out.append({
            "id": f"trace-{s['timestamp']}-{s['call_no']}",
            "timestamp": s["timestamp"],
            "name": "llm.call",
            "model": s["model"],
            "modelParameters": {"provider": s["provider"]},
            "usage": {
                "promptTokens": s["tokens_in"],
                "completionTokens": s["tokens_out"],
                "totalTokens": s["tokens_total"],
            },
            "metadata": {
                "session": s["session"],
                "latency_seconds": s["latency_seconds"],
                "cache_read": s["tokens_cache_read"],
                "cost_usd": s["cost_usd"],
            },
        })
    return out


def cmd_viz(last: int = 30) -> str:
    """ASCII timeline of recent calls."""
    spans = enrich_spans(parse_log(LOG_PATH)[-last:])
    if not spans:
        return "No spans found."
    max_latency = max(s["latency_seconds"] for s in spans) or 1.0
    lines = [f"Recent LLM calls (n={len(spans)}, max latency={max_latency:.1f}s):"]
    lines.append("")
    for s in spans[-last:]:
        bar_len = int((s["latency_seconds"] / max_latency) * 30)
        bar = "█" * bar_len
        ts = s["timestamp"][11:19]
        cost = f"${s['cost_usd']:.4f}" if s["cost_usd"] else "  $0  "
        lines.append(f"  {ts} |{bar:<30}| {s['latency_seconds']:.1f}s  {cost}  {s['model'][:20]:<20}  in={s['tokens_in']:>6} out={s['tokens_out']:>4}")
    return "\n".join(lines)


def cmd_costs(since: str = "1d") -> dict:
    """Cost analysis with monthly forecast."""
    since_dt = parse_since(since)
    spans = enrich_spans(parse_log(LOG_PATH, since_dt))
    total_cost = sum(s["cost_usd"] for s in spans)
    hours = max(
        (datetime.now(timezone.utc) - (since_dt or datetime.now(timezone.utc))).total_seconds() / 3600,
        1.0,
    )
    rate_per_hour = total_cost / hours
    forecast_daily = rate_per_hour * 24
    forecast_monthly = rate_per_hour * 24 * 30
    by_model_cost = defaultdict(float)
    for s in spans:
        by_model_cost[s["model"]] += s["cost_usd"]
    return {
        "window": since,
        "spans": len(spans),
        "total_cost_usd": round(total_cost, 4),
        "rate_per_hour_usd": round(rate_per_hour, 4),
        "forecast_daily_usd": round(forecast_daily, 2),
        "forecast_monthly_usd": round(forecast_monthly, 2),
        "by_model": dict(sorted(by_model_cost.items(), key=lambda x: -x[1])),
        "free_tier_safe": forecast_monthly < 5.0,  # flag if > $5/mo
    }


def cmd_persist(since: str = "1d") -> int:
    """Persist spans to traces/ directory (per day)."""
    since_dt = parse_since(since)
    spans = enrich_spans(parse_log(LOG_PATH, since_dt))
    if not spans:
        return 0
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    # One file per day
    by_day = defaultdict(list)
    for s in spans:
        day = s["timestamp"][:10]
        by_day[day].append(s)
    written = 0
    for day, day_spans in by_day.items():
        out = TRACES_DIR / f"{day}.jsonl"
        with out.open("a") as f:
            for s in day_spans:
                f.write(json.dumps(s) + "\n")
                written += 1
    return written


def parse_since(s: str | None) -> datetime | None:
    if not s:
        return None
    m = re.match(r"(\d+)([smhdw])", s)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    delta = {
        "s": timedelta(seconds=n),
        "m": timedelta(minutes=n),
        "h": timedelta(hours=n),
        "d": timedelta(days=n),
        "w": timedelta(weeks=n),
    }[unit]
    return datetime.now(timezone.utc) - delta


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes LLM tracer — parse agent.log into spans")
    parser.add_argument("--tail", action="store_true", help="Tail recent spans")
    parser.add_argument("--last", type=int, default=10, help="How many (with --tail or --viz)")
    parser.add_argument("--summary", action="store_true", help="Aggregate summary")
    parser.add_argument("--query", action="store_true", help="Filtered query")
    parser.add_argument("--model", help="Filter by model substring (with --query)")
    parser.add_argument("--provider", help="Filter by provider substring (with --query)")
    parser.add_argument("--export", action="store_true", help="Export as Langfuse JSONL")
    parser.add_argument("--viz", action="store_true", help="ASCII timeline")
    parser.add_argument("--costs", action="store_true", help="Cost analysis with monthly forecast")
    parser.add_argument("--persist", action="store_true", help="Write spans to ~/.hermes/state/traces/")
    parser.add_argument("--since", default="1d", help="Time window (1d, 7d, 1h, 30m, 2w)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not (args.tail or args.summary or args.query or args.export or args.viz or args.costs or args.persist):
        parser.print_help()
        return 1

    if args.persist:
        n = cmd_persist(args.since)
        print(f"Persisted {n} spans to {TRACES_DIR}/")
        return 0

    if args.costs:
        result = cmd_costs(args.since)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Cost Analysis (window: {args.since}) ===")
            print(f"  Spans: {result['spans']}")
            print(f"  Total cost: ${result['total_cost_usd']:.4f}")
            print(f"  Rate: ${result['rate_per_hour_usd']:.4f}/hour")
            print(f"  Forecast: ${result['forecast_daily_usd']:.2f}/day, ${result['forecast_monthly_usd']:.2f}/month")
            print(f"  Free-tier safe: {'YES' if result['free_tier_safe'] else 'NO (> $5/mo)'}")
            print(f"\n  By model:")
            for model, cost in result["by_model"].items():
                print(f"    {model:<30} ${cost:.4f}")
        return 0

    if args.viz:
        print(cmd_viz(args.last))
        return 0

    if args.tail:
        result = cmd_tail(args.last, args.since)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Last {len(result)} spans ===")
            for s in result:
                print(f"  {s['timestamp']} #{s['call_no']:<3} {s['model']:<25} {s['provider']:<20} in={s['tokens_in']:>6} out={s['tokens_out']:>4} latency={s['latency_seconds']:.1f}s cost=${s['cost_usd']:.4f}")
        return 0

    if args.summary:
        result = cmd_summary(args.since)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\n=== Summary (window: {args.since}) ===")
            print(f"  Total spans: {result['total_spans']}")
            print(f"  Total cost: ${result['total_cost_usd']:.4f}")
            print(f"  Total tokens in/out: {result['total_tokens_in']:,} / {result['total_tokens_out']:,}")
            print(f"  Cache reads: {result['total_cache_read']:,}")
            print(f"  Avg latency: {result['avg_latency_seconds']:.3f}s")
            print(f"\n  By model (top 5 by cost):")
            for model, stats in list(result["by_model"].items())[:5]:
                print(f"    {model:<35} calls={stats['calls']:>4} tokens={stats['tokens_in']+stats['tokens_out']:>10,} cost=${stats['cost']:.4f}")
            print(f"\n  By provider:")
            for provider, stats in result["by_provider"].items():
                print(f"    {provider:<25} calls={stats['calls']:>4} cost=${stats['cost']:.4f}")
        return 0

    if args.query:
        result = cmd_query(args.model, args.provider, args.since, args.last)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Query (model={args.model}, provider={args.provider}) ===")
            for s in result:
                print(f"  {s['timestamp']} {s['model']} {s['provider']} in={s['tokens_in']} out={s['tokens_out']} ${s['cost_usd']:.4f}")
        return 0

    if args.export:
        for span in cmd_export(args.since):
            print(json.dumps(span))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())