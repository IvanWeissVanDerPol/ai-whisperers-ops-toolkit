#!/usr/bin/env python3
"""
trace_anomaly_detector.py — Detect unusual patterns in trace data.

Compares today's trace metrics against a rolling 7-day baseline. Flags:
  - Daily call count change > 30% (more or fewer calls than baseline)
  - Token usage change > 50% (much higher or lower)
  - Error rate change > 5% (new errors appearing)
  - New model/provider appearing (sudden provider switch)
  - Latency p95 increase > 50% (slower)
  - Cost spike > $5/day (or 50% above baseline)

Outputs JSON or human-readable text.

Usage:
  python3 trace_anomaly_detector.py                 # last 24h vs 7-day baseline
  python3 trace_anomaly_detector.py --json
  python3 trace_anomaly_detector.py --threshold 0.3  # custom threshold
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


def load_traces_for_window(days_back: int, today_only: bool = False) -> list[dict]:
    """Load traces from the last N days."""
    if today_only:
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    traces = []
    if not TRACES_DIR.exists():
        return traces
    for tf in sorted(TRACES_DIR.glob("*.jsonl")):
        try:
            # Try to get date from filename
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
                d["_ts"] = ts
                traces.append(d)
    return traces


def daily_metrics(traces: list[dict]) -> dict:
    """Compute per-day aggregate metrics."""
    by_day: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        "errors": 0, "models": set(), "providers": set(), "latencies": [],
    })
    for t in traces:
        ts = t.get("_ts")
        if not ts:
            continue
        day = ts.strftime("%Y-%m-%d")
        m = by_day[day]
        m["calls"] += 1
        m["tokens_in"] += t.get("tokens_in", 0)
        m["tokens_out"] += t.get("tokens_out", 0)
        m["cost_usd"] += t.get("cost_usd", 0.0)
        if (t.get("cost_usd") or 0) > 0 and (t.get("tokens_out") or 0) == 0:
            # Heuristic: empty output + cost = failed call
            m["errors"] += 1
        m["models"].add(t.get("model", ""))
        m["providers"].add(t.get("provider", ""))
        m["latencies"].append(t.get("latency_seconds", 0.0))

    # Compute p95 per day
    for day, m in by_day.items():
        lats = sorted(m["latencies"])
        n = len(lats)
        m["p95_latency"] = lats[int(n * 0.95)] if n > 0 else 0
        m["all_models"] = sorted(m["models"])
        m["all_providers"] = sorted(m["providers"])
        del m["models"], m["providers"], m["latencies"]

    return dict(by_day)


def detect_anomalies(daily: dict, threshold: float = 0.3) -> list[dict]:
    """Compare today vs 7-day baseline. Return list of anomalies."""
    anomalies = []
    if not daily:
        return anomalies
    days = sorted(daily.keys())
    today_key = days[-1]
    baseline_days = days[:-1]
    if not baseline_days:
        return anomalies
    today = daily[today_key]

    # Compute baseline averages (excluding today)
    avg_calls = statistics.mean(daily[d]["calls"] for d in baseline_days)
    avg_tokens_in = statistics.mean(daily[d]["tokens_in"] for d in baseline_days)
    avg_tokens_out = statistics.mean(daily[d]["tokens_out"] for d in baseline_days)
    avg_cost = statistics.mean(daily[d]["cost_usd"] for d in baseline_days)
    avg_p95 = statistics.mean(daily[d]["p95_latency"] for d in baseline_days if daily[d]["p95_latency"] > 0)
    baseline_errors = sum(daily[d]["errors"] for d in baseline_days)

    # Baseline models/providers
    baseline_models = set()
    baseline_providers = set()
    for d in baseline_days:
        baseline_models.update(daily[d]["all_models"])
        baseline_providers.update(daily[d]["all_providers"])

    # Anomaly 1: call count change > threshold
    if avg_calls > 0:
        change = (today["calls"] - avg_calls) / avg_calls
        if abs(change) > threshold:
            anomalies.append({
                "type": "calls",
                "today": today["calls"],
                "baseline_avg": round(avg_calls, 1),
                "change_pct": round(change * 100, 1),
                "severity": "high" if abs(change) > 0.5 else "medium",
                "description": f"Call count {'up' if change > 0 else 'down'} {change*100:.0f}% from baseline",
            })

    # Anomaly 2: token usage change > 50%
    if avg_tokens_in > 0:
        change = (today["tokens_in"] - avg_tokens_in) / avg_tokens_in
        if abs(change) > 0.5:
            anomalies.append({
                "type": "tokens_in",
                "today": today["tokens_in"],
                "baseline_avg": int(avg_tokens_in),
                "change_pct": round(change * 100, 1),
                "severity": "medium",
                "description": f"Token usage {'up' if change > 0 else 'down'} {change*100:.0f}%",
            })

    # Anomaly 3: cost spike > $5 or 50%
    if avg_cost > 0:
        change = (today["cost_usd"] - avg_cost) / avg_cost
        cost_spike = today["cost_usd"] > 5.0
        if abs(change) > 0.5 or cost_spike:
            anomalies.append({
                "type": "cost",
                "today": round(today["cost_usd"], 2),
                "baseline_avg": round(avg_cost, 2),
                "change_pct": round(change * 100, 1),
                "severity": "high" if cost_spike else "medium",
                "description": f"Cost {'up' if change > 0 else 'down'} {change*100:.0f}% (${today['cost_usd']:.2f} vs baseline ${avg_cost:.2f})",
            })

    # Anomaly 4: error rate change > 5%
    if avg_calls > 0:
        baseline_error_rate = baseline_errors / sum(daily[d]["calls"] for d in baseline_days)
        today_error_rate = today["errors"] / max(today["calls"], 1)
        change = today_error_rate - baseline_error_rate
        if abs(change) > 0.05:
            anomalies.append({
                "type": "errors",
                "today": today["errors"],
                "baseline_avg": round(baseline_errors / max(len(baseline_days), 1), 1),
                "today_error_rate": round(today_error_rate * 100, 1),
                "baseline_error_rate": round(baseline_error_rate * 100, 1),
                "severity": "high" if change > 0.1 else "medium",
                "description": f"Error rate {'up' if change > 0 else 'down'} {abs(change)*100:.0f}pp ({today_error_rate*100:.1f}% vs baseline {baseline_error_rate*100:.1f}%)",
            })

    # Anomaly 5: new model or provider appeared
    new_models = set(today["all_models"]) - baseline_models
    new_providers = set(today["all_providers"]) - baseline_providers
    if new_models:
        anomalies.append({
            "type": "new_model",
            "models": sorted(new_models),
            "severity": "low",
            "description": f"New model(s) seen today: {', '.join(sorted(new_models))}",
        })
    if new_providers:
        anomalies.append({
            "type": "new_provider",
            "providers": sorted(new_providers),
            "severity": "low",
            "description": f"New provider(s) seen today: {', '.join(sorted(new_providers))}",
        })

    # Anomaly 6: latency p95 increase > 50%
    if avg_p95 > 0 and today["p95_latency"] > 0:
        change = (today["p95_latency"] - avg_p95) / avg_p95
        if change > 0.5:
            anomalies.append({
                "type": "latency",
                "today_p95": round(today["p95_latency"], 2),
                "baseline_p95": round(avg_p95, 2),
                "change_pct": round(change * 100, 1),
                "severity": "medium",
                "description": f"Latency p95 up {change*100:.0f}% ({today['p95_latency']:.1f}s vs baseline {avg_p95:.1f}s)",
            })

    return anomalies


def format_human(data: dict) -> str:
    s = data["summary"]
    lines = [
        "=== Trace Anomaly Detection ===",
        "",
        f"Period:          {s['baseline_days']} baseline day(s) + today",
        f"Today:           {s['today']}",
        f"Today calls:     {s['today_calls']:,}",
        f"Today cost:      ${s['today_cost']:.4f}",
        f"Anomalies found: {len(data['anomalies'])}",
        "",
    ]
    if data["anomalies"]:
        lines.append("--- Anomalies ---")
        for a in data["anomalies"]:
            sev = a.get("severity", "?")
            mark = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(sev, "⚪")
            lines.append(f"  {mark} [{sev.upper()}] {a['type']}: {a['description']}")
    else:
        lines.append("  ✓ No anomalies detected")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=0.3,
                        help="Call-count change threshold (default 0.3 = 30%)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    traces = load_traces_for_window(days_back=7)
    if not traces:
        print("No traces found in the last 7 days")
        return 0

    daily = daily_metrics(traces)
    anomalies = detect_anomalies(daily, threshold=args.threshold)

    days = sorted(daily.keys())
    today = daily[days[-1]] if days else {}
    data = {
        "summary": {
            "baseline_days": len(days) - 1,
            "today": days[-1] if days else None,
            "today_calls": today.get("calls", 0),
            "today_cost": today.get("cost_usd", 0.0),
        },
        "anomalies": anomalies,
    }

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(format_human(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())