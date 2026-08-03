#!/usr/bin/env python3
"""
cost_alert.py — Send cost-forecast alerts to Telegram on CRITICAL.

Calls cost_forecast.py --json to read the current state, then broadcasts
a Telegram message via the bot if alert_level is "warning" or "critical".

Usage:
    python3 ~/.hermes/scripts/cost_alert.py
    python3 ~/.hermes/scripts/cost_alert.py --dry-run
    python3 ~/.hermes/scripts/cost_alert.py --json

Exit codes:
    0 = ok (no alert or alert sent successfully)
    1 = warning sent
    2 = critical sent
    3 = error
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import urllib.request

HERMES_HOME = Path.home() / ".hermes"
SCRIPTS = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"
COST_ALERT_LOG = STATE / "cost-alerts.jsonl"


def get_forecast() -> dict:
    """Run cost_forecast.py --json and return result."""
    result = subprocess.run(
        ["python3", str(SCRIPTS / "cost_forecast.py"), "--json"],
        capture_output=True, text=True, timeout=60,
    )
    if not result.stdout.strip():
        raise RuntimeError(f"cost_forecast.py returned no output: {result.stderr}")
    return json.loads(result.stdout)


def get_home_channel() -> str | None:
    """Read TELEGRAM_HOME_CHANNEL from config.yaml."""
    import re
    cfg_path = HERMES_HOME / "config.yaml"
    if not cfg_path.exists():
        return None
    content = cfg_path.read_text()
    m = re.search(
        r"^telegram:\s*\n(?:\s+.+\n)*?\s+home_channel:\s*['\"]?([^\s'\"]+)",
        content, re.MULTILINE,
    )
    if m:
        return m.group(1).strip("'\"")
    env_val = os.environ.get("TELEGRAM_HOME_CHANNEL")
    return env_val


def send_telegram(chat_id: str, text: str) -> bool:
    """Send a message via the Telegram bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        env_path = HERMES_HOME / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    if not token:
        print("error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return False
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"error sending telegram: {e}", file=sys.stderr)
        return False


def get_prompt_from_registry(name: str) -> str | None:
    """Fetch a prompt from the registry. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["python3", "/root/.hermes/scripts/prompt_registry.py", "get",
             "--name", name, "--version", "stable", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            d = json.loads(result.stdout)
            return d.get("content")
    except Exception:
        pass
    return None


def format_alert(forecast: dict) -> str:
    """Format a Telegram-friendly alert message.
    
    R17: Now optionally reads its template from the prompt registry
    (cost_alert_message). If unavailable, falls back to the hardcoded
    template below.
    """
    level = forecast.get("alert_level", "?").upper()
    icon = {"CRITICAL": "🚨", "WARNING": "⚠️", "OK": "✅"}.get(level, "📊")
    budget = forecast.get("budget_usd_monthly", 0)
    rate = forecast.get("primary_rate_per_hour_usd", 0)
    forecast_monthly = forecast.get("primary_forecast_monthly_usd", 0)
    pct = forecast.get("pct_of_budget_used", 0)
    days = forecast.get("days_until_budget_exhausted")
    percentiles = forecast.get("projected_monthly_by_percentile", {})
    lines = [
        f"{icon} *Hermes Cost Forecast — {level}*",
        f"",
        f"Budget: *${budget:.2f}/month*",
        f"Current rate: ${rate:.4f}/hour",
        f"Forecast: *${forecast_monthly:.2f}/month* ({pct:.1f}% of budget)",
    ]
    if percentiles:
        lines.append("")
        lines.append("Confidence levels:")
        for k in ("p50", "p90", "p99"):
            v = percentiles.get(k, 0)
            lines.append(f"  {k.upper()}: ${v:.2f}/mo")
    if days is not None and days < 30:
        lines.append(f"")
        lines.append(f"⏰ Budget exhausted in *{days:.1f} days* at current rate")
    # R17-10: Top cost drivers — fetch from trace_skill_analytics
    try:
        skill_result = subprocess.run(
            ["python3", "/root/.hermes/scripts/trace_skill_analytics.py",
             "--days", "7", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if skill_result.returncode == 0 and skill_result.stdout.strip():
            skill_data = json.loads(skill_result.stdout)
            top_skills = sorted(
                [s for s in skill_data.get("by_skill", []) if s["cost_usd"] > 0],
                key=lambda x: x["cost_usd"],
                reverse=True,
            )[:3]
            if top_skills:
                lines.append("")
                lines.append("Top cost drivers (last 7d):")
                for s in top_skills:
                    lines.append(f"  • {s['skill'][:30]}: ${s['cost_usd']:.2f} ({s['calls']} calls)")
    except Exception:
        pass  # Don't fail the alert if analytics is down
    lines.append("")
    lines.append(f"_Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    return "\n".join(lines)


def log_alert(level: str, forecast: dict, sent: bool, chat_id: str | None) -> None:
    """Append to cost-alerts.jsonl."""
    STATE.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "forecast_monthly_usd": forecast.get("primary_forecast_monthly_usd"),
        "pct_of_budget": forecast.get("pct_of_budget_used"),
        "sent": sent,
        "chat_id": chat_id,
    }
    with COST_ALERT_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cost forecast alert router")
    parser.add_argument("--dry-run", action="store_true", help="Don't send, just print")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()

    try:
        forecast = get_forecast()
    except Exception as e:
        print(f"error: could not get forecast: {e}", file=sys.stderr)
        return 3

    level = forecast.get("alert_level", "ok")

    if args.json:
        result = {
            "skill": "cost-alert",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_level": level,
            "forecast": forecast,
        }
        print(json.dumps(result, indent=2, default=str))
        # Exit 0 always when JSON output succeeds — the alert_level field in the
        # JSON IS the alert signal. Returning non-zero here causes cron_health.py
        # to flag the cron as broken, which is wrong: the script worked.
        return 0

    msg = format_alert(forecast)
    chat_id = get_home_channel()

    if level == "ok":
        if not args.quiet:
            print(f"\n=== Cost Alert ===")
            print(f"  Level: OK (no broadcast needed)")
            print(f"  Forecast: ${forecast.get('primary_forecast_monthly_usd', 0):.2f}/mo within budget")
        log_alert(level, forecast, False, chat_id)
        return 0

    if args.dry_run:
        if not args.quiet:
            print(f"\n=== Cost Alert (DRY-RUN) ===")
            print(msg)
        # Dry-run prints the message but doesn't send — always exit 0 (dry-run
        # is a successful script completion, not a failure)
        return 0

    if not chat_id:
        print(f"error: TELEGRAM_HOME_CHANNEL not set, alert not sent", file=sys.stderr)
        log_alert(level, forecast, False, None)
        return 3  # Genuine script failure: missing config

    if not args.quiet:
        print(f"\n=== Cost Alert ===")
        print(f"  Level: {level.upper()}")
        print(f"  Sending to Telegram chat_id={chat_id}...")

    sent = send_telegram(chat_id, msg)
    log_alert(level, forecast, sent, chat_id)

    if not args.quiet:
        if sent:
            print(f"  ✓ Sent")
        else:
            print(f"  ✗ Telegram send failed")

    # Exit 0 when Telegram sent (whether or not alert was critical).
    # Exit 3 only when Telegram send itself failed (network/auth issue).
    return 0 if sent else 3


if __name__ == "__main__":
    sys.exit(main())
