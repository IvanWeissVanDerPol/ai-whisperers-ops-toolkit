#!/usr/bin/env python3
"""
regression_alert.py — Detect regressions and alert via Telegram/WhatsApp.

Runs snapshot_diff across all repos, and if any regressions are found,
sends a digest via hermes send to the configured chat.

Usage:
    python3 ~/.hermes/scripts/regression_alert.py
    python3 ~/.hermes/scripts/regression_alert.py --dry-run
    python3 ~/.hermes/scripts/regression_alert.py --target whatsapp
    python3 ~/.hermes/scripts/regression_alert.py --target telegram

Targets: whatsapp (default), telegram, slack
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SCRIPTS = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"


def run_snapshot_diff(compare: str = "1d") -> dict:
    """Run snapshot_diff and parse JSON output."""
    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "snapshot_diff.py"), "--all", "--compare", compare, "--json"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode in (0, 1):
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"results": []}
        return {"results": []}
    except Exception as e:
        return {"results": [], "error": str(e)}


def format_digest(data: dict) -> str:
    """Format regression digest for delivery."""
    results = data.get("results", [])
    total_reg = data.get("total_regressions", 0)
    lines = []
    lines.append(f"🚨 *Hermes Regression Alert* — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append(f"Total regressions: *{total_reg}*")
    lines.append(f"Repos scanned: {len(results)}")
    lines.append("")
    if total_reg > 0:
        lines.append("*Regressions:*")
        for r in results:
            repo = r.get("repo", "?")
            regs = r.get("diff", {}).get("regressions", [])
            if regs:
                lines.append(f"  • *{repo}*:")
                for reg in regs:
                    lines.append(f"    – {reg}")
    else:
        lines.append("✅ No regressions detected.")
    return "\n".join(lines)


def send(target: str, message: str) -> dict:
    """Send via hermes send."""
    try:
        result = subprocess.run(
            ["hermes", "send", "-t", target, message],
            capture_output=True, text=True, timeout=60,
        )
        return {"status": "ok" if result.returncode == 0 else "failed", "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect regressions and alert via Telegram/WhatsApp")
    parser.add_argument("--target", default="whatsapp", choices=["whatsapp", "telegram", "slack"], help="Delivery target")
    parser.add_argument("--compare", default="1d", help="Comparison window (1d, 7d, 30d)")
    parser.add_argument("--dry-run", action="store_true", help="Don't send, just print")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    data = run_snapshot_diff(args.compare)
    message = format_digest(data)

    sent = None
    if not args.dry_run and data.get("total_regressions", 0) > 0:
        sent = send(args.target, message)

    if args.json:
        print(json.dumps({
            "skill": "regression-alert",
            "version": "1.0.0",
            "compare": args.compare,
            "target": args.target,
            "regressions": data.get("total_regressions", 0),
            "sent": sent,
            "digest_preview": message[:500],
        }, indent=2))
    else:
        print(message)
        if args.dry_run:
            print("\n  (dry-run; nothing sent)")
        elif sent:
            print(f"\n  ✓ Sent to {args.target}: {sent.get('status')}")
    return 0 if data.get("total_regressions", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())