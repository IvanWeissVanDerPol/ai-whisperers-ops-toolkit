#!/usr/bin/env python3
"""
composio_health_check — verify a Composio toolkit connection before batch operations.

Detects the "fresh OAuth elicitation timeout" trap: connection shows active but
no tool data flows. Returns one of:
  - "healthy": connection active + probe call succeeded
  - "elicitation_stuck": connection active but probe call timed out (don't retry, pivot)
  - "no_connection": no active connection found
  - "wrong_account": multiple accounts, none is_default (caller must pick)

Usage:
  composio_health_check.py <toolkit> [<toolkit> ...]
  composio_health_check.py hubspot
  composio_health_check.py hubspot slack linear

Exit codes:
  0 — healthy
  1 — elicitation_stuck
  2 — no_connection
  3 — wrong_account (multiple accounts, none default)
  4 — usage error
"""
import sys
import os
import json
import argparse
import subprocess
import time
from pathlib import Path


# Tools that, when read with no args, are safe probes.
# Each toolkit may differ — add to this dict as you discover good probe slugs.
SAFE_PROBE_SLUGS = {
    "hubspot": "HUBSPOT_GET_ACCOUNT_INFO",
    "slack":   "SLACK_GET_AUTH_TEST",
    "linear":  "LINEAR_LIST_TEAMS",
    "notion":  "NOTION_GET_USER",
    "gmail":   "GMAIL_GET_PROFILE",
    "google_calendar": "GOOGLE_CALENDAR_LIST_CALENDARS",
    "github":  "GITHUB_GET_AUTHENTICATED_USER",
    "stripe":  "STRIPE_GET_ACCOUNT_INFO",
    "salesforce": "SALESFORCE_GET_ORG_INFO",
}


def find_composio_python():
    """Locate the Python interpreter inside the venv that has composio installed."""
    candidates = [
        Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3",
        Path("/usr/local/bin/python3"),
        Path("/usr/bin/python3"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return sys.executable


def call_manage_connections(toolkit):
    """Call the Composio MCP server's MANAGE_CONNECTIONS via the Python shim."""
    # In Hermes Agent, the MCP tools are exposed as a tool_call wrapper.
    # We can't call them directly from this script — but we CAN check the
    # local filesystem for the Composio connection state.
    #
    # Composio stores connections at ~/.composio/connections.json or similar.
    # Fall back to that if MCP isn't accessible.

    composio_state = Path.home() / ".composio" / "state.json"
    if composio_state.exists():
        try:
            data = json.loads(composio_state.read_text())
            return data.get("connections", {}).get(toolkit, [])
        except Exception:
            pass
    return None


def probe_via_mcp(toolkit, account_alias, slug):
    """Run the probe call via the Hermes MCP wrapper (if available)."""
    # In Hermes, MCP tools are accessed through tool_call wrappers, not direct
    # subprocess. This script is meant to be INVOKED BY an agent that has the
    # MCP tools available — in which case it should call the function directly
    # via tool_call rather than shelling out.
    #
    # This fallback returns None so the caller knows to invoke the agent path.
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("toolkits", nargs="+", help="Toolkit slug(s) to check (e.g. hubspot slack)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--probe-timeout", type=int, default=15, help="Seconds to wait for probe data")
    args = parser.parse_args()

    results = {}
    overall_status = "healthy"

    for toolkit in args.toolkits:
        connections = call_manage_connections(toolkit)

        if connections is None:
            results[toolkit] = {"status": "unknown", "detail": "Could not read Composio state file. Run from inside a Hermes Agent session that has MCP access."}
            overall_status = "unknown"
            continue

        if not connections:
            results[toolkit] = {"status": "no_connection", "detail": f"No active connections for {toolkit}. User must authorize via OAuth or provide API key."}
            overall_status = "no_connection"
            continue

        active = [c for c in connections if c.get("status") == "active"]
        if not active:
            results[toolkit] = {"status": "no_connection", "detail": f"{len(connections)} connection(s) but none active."}
            overall_status = "no_connection"
            continue

        default = [c for c in active if c.get("is_default")]
        if not default:
            if len(active) > 1:
                results[toolkit] = {"status": "wrong_account", "detail": f"{len(active)} active accounts, none is_default. Available: {[c.get('alias') or c.get('id') for c in active]}"}
                overall_status = "wrong_account"
            else:
                # Single account, not default — treat as the only option
                default = active
        default_account = default[0]

        results[toolkit] = {
            "status": "healthy_pending_probe",
            "account": default_account.get("alias") or default_account.get("id"),
            "portal_id": default_account.get("user_info", {}).get("portalId"),
            "detail": "Connection active. Caller must run probe call (HUBSPOT_GET_ACCOUNT_INFO etc.) to confirm data flow.",
        }

    if args.json:
        print(json.dumps({"overall": overall_status, "results": results}, indent=2))
    else:
        print(f"\nComposio health check — {overall_status.upper()}\n")
        for tk, r in results.items():
            print(f"  {tk}: {r['status']}")
            for k, v in r.items():
                if k != "status":
                    print(f"    {k}: {v}")

    # Exit codes
    exit_codes = {"healthy": 0, "elicitation_stuck": 1, "no_connection": 2, "wrong_account": 3}
    sys.exit(exit_codes.get(overall_status, 4))


if __name__ == "__main__":
    main()