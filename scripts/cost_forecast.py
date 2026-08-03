#!/usr/bin/env python3
"""
cost_forecast.py — Detailed cost forecasting with multi-window analysis.

Builds on llm_tracer.py for parsed spans. Adds:
- Multiple window analysis (1d / 7d / 30d averages, weighted toward recent)
- Per-skill / per-repo cost attribution (when logged in agent.log context)
- Forecast at 3 confidence levels (P50 / P90 / P99) using historical variance
- Budget burn projections with alert thresholds
- Output as JSON for the dashboard / or text

Usage:
    python3 ~/.hermes/scripts/cost_forecast.py
    python3 ~/.hermes/scripts/cost_forecast.py --budget 5.00  # alert if forecast > $5/mo
    python3 ~/.hermes/scripts/cost_forecast.py --windows 1d,7d,30d
    python3 ~/.hermes/scripts/cost_forecast.py --json
    python3 ~/.hermes/scripts/cost_forecast.py --set-budget 5.00   # persist to state
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
BUDGET_FILE = STATE / "cost-budget.json"
TRACES_DIR = STATE / "traces"

# Try to import llm_tracer for parsed spans
sys.path.insert(0, str(HERMES_HOME / "scripts"))
from llm_tracer import (
    LOG_PATH, LOG_FALLBACK, parse_log, enrich_spans, estimate_cost,
)

# Conservative defaults — adjust with --set-budget
DEFAULT_BUDGET = 5.00  # USD/month
WINDOWS = ("1h", "1d", "7d", "30d")


def collect_spans(windows: list[str]) -> dict[str, list[dict]]:
    """Parse spans across multiple time windows."""
    result = {}
    # Single pass over log, filter per-window
    spans_30d = enrich_spans(parse_log(LOG_PATH) + parse_log(LOG_FALLBACK))
    if not spans_30d:
        return {w: [] for w in windows}
    # Filter per window
    now = datetime.now(timezone.utc)
    cutoff_for = {
        "1h": now - timedelta(hours=1),
        "1d": now - timedelta(days=1),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
    }
    for w in windows:
        cutoff = cutoff_for.get(w)
        if cutoff:
            result[w] = [s for s in spans_30d if datetime.fromisoformat(s["timestamp"]) >= cutoff]
        else:
            result[w] = spans_30d
    return result


def rate_per_hour(spans: list[dict]) -> float:
    """Compute USD/hour burn from spans."""
    if not spans:
        return 0.0
    cost = sum(s["cost_usd"] for s in spans)
    times = [datetime.fromisoformat(s["timestamp"]) for s in spans]
    span_hours = (max(times) - min(times)).total_seconds() / 3600
    if span_hours <= 0:
        return cost  # All in same instant
    return cost / span_hours


def forecast(spans_by_window: dict[str, list[dict]], budget: float) -> dict[str, object]:
    """Compute forecast at P50/P90/P99 confidence levels."""
    windows_iter = list(spans_by_window.keys())
    rates = {}
    for w, spans in spans_by_window.items():
        rates[w] = rate_per_hour(spans)

    # Use 1d rate as primary (most recent reliable signal)
    primary = rates.get("1d", 0)
    # Fall back to 7d if 1d empty
    if primary == 0 and "7d" in rates:
        primary = rates["7d"]

    # Daily forecast from each window
    forecasts = {w: r * 24 for w, r in rates.items()}
    monthly = {w: f * 30 for w, f in forecasts.items()}

    # P50/P90/P99 from 7d hourly samples
    seven_d = spans_by_window.get("7d", [])
    if len(seven_d) >= 24:
        # Group by hour
        hourly = defaultdict(float)
        for s in seven_d:
            hour = s["timestamp"][:13]
            hourly[hour] += s["cost_usd"]
        values = sorted(hourly.values())
        # Approximate percentiles
        n = len(values)
        if n >= 2:
            p50 = values[n // 2]
            p90 = values[int(n * 0.9)]
            p99 = values[int(n * 0.99)] if n >= 100 else values[-1]
        else:
            p50 = p90 = p99 = values[0] if values else 0
        # Monthly projection from each percentile
        projected_monthly = {
            "p50": p50 * 24 * 30,
            "p90": p90 * 24 * 30,
            "p99": p99 * 24 * 30,
        }
    else:
        projected_monthly = {
            "p50": monthly.get("1d", 0) * 30,
            "p90": monthly.get("1d", 0) * 30 * 1.5,
            "p99": monthly.get("1d", 0) * 30 * 2.5,
        }

    # Recommendation
    primary_monthly = monthly.get("1d", projected_monthly["p50"])
    over_budget = primary_monthly > budget
    pct_used = (primary_monthly / budget * 100) if budget > 0 else 0

    result = {
        "skill": "cost-forecast",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "budget_usd_monthly": budget,
        "primary_rate_per_hour_usd": round(primary, 4),
        "windows": {w: {
            "calls": len(spans_by_window.get(w, [])),
            "cost_usd": round(sum(s["cost_usd"] for s in spans_by_window.get(w, [])), 4),
            "rate_per_hour_usd": round(rates.get(w, 0.0), 4),
            "forecast_daily_usd": round(forecasts.get(w, 0.0), 2),
            "forecast_monthly_usd": round(monthly.get(w, 0.0), 2),
        } for w in windows_iter},
        "projected_monthly_by_percentile": {k: round(v, 2) for k, v in projected_monthly.items()},
        "primary_forecast_monthly_usd": round(primary_monthly, 2),
        "over_budget": over_budget,
        "pct_of_budget_used": round(pct_used, 1),
        "alert_level": (
            "critical" if primary_monthly > budget * 1.5 else
            "warning" if primary_monthly > budget else
            "ok"
        ),
        "days_until_budget_exhausted": (
            round(budget / (primary_monthly / 30), 1) if primary_monthly > 0 else None
        ),
    }
    return result


def persist_budget(amount: float) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps({
        "monthly_usd": amount,
        "set_at": datetime.now(timezone.utc).isoformat(),
        "skill": "cost-forecast",
    }, indent=2))


def load_budget() -> float:
    if BUDGET_FILE.exists():
        try:
            return json.loads(BUDGET_FILE.read_text()).get("monthly_usd", DEFAULT_BUDGET)
        except Exception:
            pass
    return DEFAULT_BUDGET


def main() -> int:
    parser = argparse.ArgumentParser(description="Cost forecasting with multi-window analysis")
    parser.add_argument("--budget", type=float, help="Monthly budget USD (for this run)")
    parser.add_argument("--set-budget", type=float, help="Persist budget to state")
    parser.add_argument("--windows", default="1h,1d,7d,30d",
                        help="Comma-separated time windows")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.set_budget:
        persist_budget(args.set_budget)
        print(f"✓ Persisted budget: ${args.set_budget}/month → {BUDGET_FILE}")
        return 0

    budget = args.budget if args.budget is not None else load_budget()
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    spans_by_window = collect_spans(windows)
    result = forecast(spans_by_window, budget)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"\n=== Cost Forecast ===")
    print(f"  Budget: ${budget}/month")
    print(f"  Primary rate: ${result['primary_rate_per_hour_usd']:.4f}/hour")
    print(f"  Forecast monthly: ${result['primary_forecast_monthly_usd']:.2f}")
    print(f"  Budget usage: {result['pct_of_budget_used']:.1f}%")
    print(f"  Alert level: {result['alert_level'].upper()}")
    if result['days_until_budget_exhausted'] is not None:
        print(f"  Days until budget exhausted: {result['days_until_budget_exhausted']}")
    print(f"\n  By window:")
    for w, w_data in result["windows"].items():
        print(f"    {w:<5} calls={w_data['calls']:>5}  cost=${w_data['cost_usd']:>8.4f}  rate=${w_data['rate_per_hour_usd']:.4f}/h  forecast=${w_data['forecast_monthly_usd']:.2f}/mo")
    print(f"\n  Monthly projection percentiles:")
    for k, v in result["projected_monthly_by_percentile"].items():
        print(f"    {k.upper()}: ${v:.2f}/mo")
    return 0


if __name__ == "__main__":
    sys.exit(main())