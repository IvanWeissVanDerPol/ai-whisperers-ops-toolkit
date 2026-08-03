#!/usr/bin/env python3
"""
token_cost_by_bot — surface per-bot token spend and budget health.

Parses:
  1. Bot runner state (last run timestamps, today's quota used)
  2. budget per bot (from skill_metadata.py)
  3. optional: gateway logs (if available — for LLM cost)

Output: text table per bot.

Usage:
  token_cost_by_bot.py           # show summary
  token_cost_by_bot.py --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import (
    HUMAN_PEOPLE, AGENT_PEOPLE, INBOX_DIR, today_iso,
)


RUNNER_STATE = INBOX_DIR / ".kanban-bot-runner-state.json"


def load_runner_state() -> dict:
    if not RUNNER_STATE.exists():
        return {"date": today_iso(), "bots": {}}
    try:
        return json.loads(RUNNER_STATE.read_text())
    except Exception:
        return {"date": today_iso(), "bots": {}}


def get_bot_state(state: dict, bot: str) -> dict:
    if state.get("date") != today_iso():
        return {"used": 0, "failures": 0, "last_run": None}
    return state.get("bots", {}).get(bot, {"used": 0, "failures": 0, "last_run": None})


def fmt_int(n: int) -> str:
    if n < 10_000:
        return f"{n:,}"
    if n < 1_000_000:
        return f"{n/1000:.0f}k"
    return f"{n/1_000_000:.1f}M"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = p.parse_args()

    state = load_runner_state()

    # Try to import skill_metadata for budget
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import skill_metadata
        budgets = {bot: skill_metadata.get_bot_token_budget(bot) for bot in AGENT_PEOPLE}
    except Exception:
        budgets = {bot: 1_000_000 for bot in AGENT_PEOPLE}  # default

    rows = []
    for bot, info in AGENT_PEOPLE.items():
        bot_state = get_bot_state(state, bot)
        budget = budgets.get(bot, 1_000_000)
        # Rough estimate: each runner invocation uses ~5k tokens (heuristic)
        runs_today = bot_state.get("used", 0)
        est_spend = runs_today * 5_000
        pct = (est_spend / budget * 100) if budget > 0 else 0
        rows.append({
            "bot": bot,
            "role": info.get("role", ""),
            "budget": budget,
            "estimated_spend": est_spend,
            "pct_used": pct,
            "runs_today": runs_today,
            "failures": bot_state.get("failures", 0),
            "last_run": bot_state.get("last_run"),
        })

    if args.json:
        print(json.dumps({"date": today_iso(), "bots": rows}, indent=2))
        return

    # Text output
    print(f"\n{'='*80}")
    print(f"Token Cost by Bot — {today_iso()}")
    print(f"{'='*80}\n")
    print(f"  {'Bot':<22} {'Budget':>10} {'Spend':>10} {'%':>6} {'Runs':>5} {'Fail':>4}  Status")
    print(f"  {'-'*22} {'-'*10} {'-'*10} {'-'*6} {'-'*5} {'-'*4}  {'-'*20}")
    for r in rows:
        status = "✓ healthy"
        if r["pct_used"] > 80:
            status = "⚠ OVER BUDGET"
        elif r["failures"] >= 2:
            status = "🛑 HALTED (failures)"
        elif r["runs_today"] >= 4:
            status = "⚠ NEAR QUOTA"
        elif r["runs_today"] >= 1:
            status = "● active"
        print(f"  {r['bot']:<22} {fmt_int(r['budget']):>10} {fmt_int(r['estimated_spend']):>10} {r['pct_used']:>5.1f}% {r['runs_today']:>5} {r['failures']:>4}  {status}")

    print()
    total_budget = sum(r["budget"] for r in rows)
    total_spend = sum(r["estimated_spend"] for r in rows)
    print(f"  {'TOTAL':<22} {fmt_int(total_budget):>10} {fmt_int(total_spend):>10} {(total_spend/total_budget*100 if total_budget else 0):>5.1f}%")
    print()

    # Best-effort link to gateway costs
    print("  Note: Spend is estimated from runner invocations × 5k tokens each.")
    print("        Real cost comes from gateway logs (parse later if needed).")
    print()


if __name__ == "__main__":
    main()
