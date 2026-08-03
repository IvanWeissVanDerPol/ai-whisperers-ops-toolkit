#!/usr/bin/env python3
"""
dns_setup.py — Configure DNS for hermes services via Cloudflare API.

Creates CNAME records for:
  - hermes-dashboard.<zone>  → Traefik hostname
  - hermes-status.<zone>     → Cloudflare Pages subdomain

Usage:
    python3 ~/.hermes/scripts/dns_setup.py --zone solstein.cloud
    python3 ~/.hermes/scripts/dns_setup.py --zone solstein.cloud --list
    python3 ~/.hermes/scripts/dns_setup.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WRANGLER_CONFIG = Path("/root/.wrangler/config/default.toml")


def get_token() -> str | None:
    """Get CF API token from env or wrangler config."""
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if token:
        return token
    if WRANGLER_CONFIG.exists():
        for line in WRANGLER_CONFIG.read_text().split("\n"):
            if "api_token" in line and '"' in line:
                return line.split('"')[1]
    return None


def get_account_id() -> str | None:
    """Get CF account ID from env."""
    return os.environ.get("CLOUDFLARE_ACCOUNT_ID")


def cf_api(path: str, method: str = "GET", body: dict | None = None, token: str = "") -> dict:
    """Call Cloudflare API."""
    import urllib.request
    url = f"https://api.cloudflare.com/client/v4{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = None
    if body:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"success": False, "errors": [{"message": str(e)}]}


def list_zones(token: str) -> list[dict]:
    result = cf_api("/zones", token=token)
    return result.get("result", [])


def list_records(zone_id: str, token: str) -> list[dict]:
    result = cf_api(f"/zones/{zone_id}/dns_records", token=token)
    return result.get("result", [])


def create_record(zone_id: str, name: str, content: str, record_type: str, proxied: bool, token: str) -> dict:
    body = {"type": record_type, "name": name, "content": content, "proxied": proxied}
    return cf_api(f"/zones/{zone_id}/dns_records", method="POST", body=body, token=token)


def setup_dashboard(zone_id: str, zone_name: str, token: str) -> dict:
    """Create CNAME for hermes-dashboard.<zone> pointing to VPS."""
    hostname = f"hermes-dashboard.{zone_name}"
    # Get the VPS hostname from /etc/hosts or existing records
    vps = "hermes.sunstein.cloud"  # Traefik entrypoint for the VPS
    result = create_record(zone_id, hostname, vps, "CNAME", proxied=True, token=token)
    return {"hostname": hostname, "target": vps, "result": result}


def setup_status(zone_id: str, zone_name: str, token: str) -> dict:
    """Create CNAME for hermes-status.<zone> pointing to Pages."""
    hostname = f"hermes-status.{zone_name}"
    target = "hermes-status-4fw.pages.dev"
    result = create_record(zone_id, hostname, target, "CNAME", proxied=True, token=token)
    return {"hostname": hostname, "target": target, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure DNS for hermes services")
    parser.add_argument("--zone", help="Zone name (e.g. solstein.cloud)")
    parser.add_argument("--list", action="store_true", help="List all zones")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    token = get_token()
    if not token:
        print("error: no CF API token found", file=sys.stderr)
        return 2

    if args.list:
        zones = list_zones(token)
        if args.json:
            print(json.dumps({"zones": [{"id": z["id"], "name": z["name"]} for z in zones]}, indent=2))
        else:
            print(f"\n=== Available Zones ===")
            for z in zones:
                print(f"  {z['name']:<30} ({z['id']})")
        return 0

    if not args.zone:
        parser.error("--zone is required (use --list to see options)")

    # Find zone ID
    zones = list_zones(token)
    zone = next((z for z in zones if z["name"] == args.zone), None)
    if not zone:
        print(f"error: zone '{args.zone}' not found", file=sys.stderr)
        return 2
    zone_id = zone["id"]

    # Setup records
    dashboard = setup_dashboard(zone_id, args.zone, token)
    status = setup_status(zone_id, args.zone, token)

    summary = {
        "skill": "dns-setup",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone": args.zone,
        "zone_id": zone_id,
        "dashboard": dashboard,
        "status_page": status,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n=== DNS Setup ({args.zone}) ===")
        for name, record in [("Dashboard", dashboard), ("Status page", status)]:
            print(f"\n  {name}:")
            print(f"    Hostname: {record['hostname']}")
            print(f"    Target:   {record['target']}")
            res = record.get("result", {})
            if res.get("success"):
                print(f"    ✓ Created: id={res['result']['id'][:8]}")
            else:
                err = res.get("errors", [{}])[0].get("message", "?")
                print(f"    ✗ Failed: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())