#!/usr/bin/env python3
"""
Read the latest client-sites-health.json and post a digest to WhatsApp via
the existing bridge. No-op if there are zero failures.

Usage:
  healthcheck_alert.py [--state PATH] [--max-fail N] [--dry-run]

Default state file: ~/.hermes/state/client-sites-health.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STATE = Path.home() / ".hermes" / "state" / "client-sites-health.json"
BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:3000")
TO = os.environ.get("WHATSAPP_ALERT_TO", "")  # E.164 like 59599xxxxxxx


def post_whatsapp(to: str, text: str) -> tuple[int, str]:
    body = json.dumps({"to": to, "message": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{BRIDGE_URL}/send",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")[:200]
    except Exception as e:
        return 0, f"error: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--max-fail", type=int, default=0,
                    help="only alert when fail count > N (default 0 = any failure)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not Path(args.state).exists():
        print(f"no state file at {args.state}", file=sys.stderr)
        return 1

    data = json.loads(Path(args.state).read_text())
    fail_count = data.get("fail", 0)
    total = data.get("total", 0)
    ok = data.get("ok", 0)
    results = data.get("results", [])
    failed = [r for r in results if not r.get("ok")]

    if fail_count <= args.max_fail:
        print(f"clean: {ok}/{total} ok, {fail_count} fail — no alert")
        return 0

    lines = [f"🚨 Client sites: {fail_count}/{total} down"]
    lines.append(f"as of {datetime.now(timezone.utc).isoformat()[:19]}")
    for r in failed[:20]:
        status = r.get("status") or r.get("error", "?")
        lines.append(f"  ✗ {r.get('name', '?')} — {status}")
    if len(failed) > 20:
        lines.append(f"  … and {len(failed) - 20} more")

    msg = "\n".join(lines)
    print(msg)
    if args.dry_run:
        print("\n[dry-run] would send via WhatsApp")
        return 0
    if not TO:
        print("\nWHATSAPP_ALERT_TO not set — skipping send")
        return 0
    code, body = post_whatsapp(TO, msg)
    print(f"\nposted: {code} | {body}")
    return 0 if code in (200, 201) else 1


if __name__ == "__main__":
    sys.exit(main())
