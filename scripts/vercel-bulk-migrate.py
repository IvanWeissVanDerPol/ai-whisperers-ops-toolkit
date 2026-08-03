#!/usr/bin/env python3
"""
Vercel bulk-migration script for paragu-ai-platform.

For each app in apps/ that has a docker-compose.yml (and thus a Traefik
Host() rule with a paragu-ai.com subdomain), create a Vercel project
configured as:
  - Root Directory: apps/<app>
  - Build Command: cd ../.. && pnpm install --frozen-lockfile && pnpm --filter=<app> build
  - Install Command: cd ../.. && pnpm install --frozen-lockfile
  - Framework Preset: Next.js
  - Custom Domain: <host>

REQUIRES: a valid Vercel API token with scope to create projects + domains.
The current ~/.hermes/.env VERCEL_API_TOKEN returns 403 — Ivan must
reactivate Vercel and replace the token first.

Usage:
  python3 vercel_bulk_migrate.py [--dry-run] [--team <team_id>] [--only <app1,app2>]
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import argparse
import glob

# Load token from .env
def load_token():
    with open(os.path.expanduser("~/.hermes/.env")) as f:
        for line in f:
            if line.startswith("VERCEL_API_TOKEN"):
                return line.strip().split("=", 1)[1]
    return os.environ.get("VERCEL_API_TOKEN")

API = "https://api.vercel.com"
REPO_ROOT = "/root/paragu-ai-platform"
APPS_DIR = os.path.join(REPO_ROOT, "apps")

def vercel(method, path, token, body=None, query=None):
    url = API + path
    if query:
        from urllib.parse import urlencode
        url += "?" + urlencode(query)
    data = None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="ignore")
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, {"raw": body_text[:500]}

def discover_apps():
    """Return list of (app_name, primary_host) for every app with a compose file.

    Prefer *.paragu-ai.com subdomains as the primary Vercel target (matches the
    fleet convention). Fall back to whatever the first Host() rule is.
    """
    out = []
    for compose_path in sorted(glob.glob(os.path.join(APPS_DIR, "*/docker-compose.yml"))):
        app = os.path.basename(os.path.dirname(compose_path))
        with open(compose_path) as f:
            text = f.read()
        # Find all Host(`...`) matches
        hosts = re.findall(r"Host\(`([^`]+)`\)", text)
        if not hosts:
            continue
        # Strip || Host() alternatives — pick the first host for each router,
        # then prefer the paragu-ai.com subdomain if available
        # Split the compound rule into individual hosts
        all_hosts = set()
        for h in hosts:
            for piece in h.split("||"):
                piece = piece.strip()
                if piece:
                    all_hosts.add(piece)
        # Prefer *.paragu-ai.com over other domains
        preferred = sorted(h for h in all_hosts if "paragu-ai.com" in h)
        if preferred:
            host = preferred[0]
        else:
            host = sorted(all_hosts)[0]
        out.append((app, host))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--team", help="Vercel team ID (for team-scoped deploys)")
    ap.add_argument("--only", help="Comma-separated app names to migrate (default: all)")
    ap.add_argument("--skip-existing", action="store_true", default=True,
                    help="Skip apps that already have a Vercel project (default: True)")
    args = ap.parse_args()

    token = load_token()
    if not token:
        print("ERROR: no Vercel API token. Set VERCEL_API_TOKEN in ~/.hermes/.env")
        sys.exit(1)

    apps = discover_apps()
    if args.only:
        wanted = set(args.only.split(","))
        apps = [a for a in apps if a[0] in wanted]

    print(f"Discovered {len(apps)} apps to migrate")
    print()

    # Verify token (skip in dry-run mode)
    if not args.dry_run:
        code, resp = vercel("GET", "/v2/user", token)
        if code != 200:
            print(f"ERROR: Vercel auth failed ({code}): {resp}")
            sys.exit(1)
        user_obj = resp.get("user") if isinstance(resp, dict) else None
        user = (user_obj or {}).get("username") or (user_obj or {}).get("email")
        print(f"Authenticated as: {user}")
        # Get or detect team
        code, resp = vercel("GET", "/v2/teams", token)
        teams = resp.get("teams", []) if isinstance(resp, dict) else []
        if args.team:
            team_id = args.team
        elif teams:
            # Use first team (or skip if user is personal)
            team_id = teams[0].get("id")
            print(f"Using team: {teams[0].get('slug')} ({team_id})")
        else:
            team_id = None
            print("Using personal account (no team)")
    else:
        team_id = None
        print("[DRY RUN] Would authenticate and detect team")

    # List existing projects to skip
    existing = set()
    if not args.dry_run:
        params = {"limit": 200}
        if team_id:
            params["teamId"] = team_id
        code, resp = vercel("GET", "/v9/projects", token, query=params)
        if code == 200 and isinstance(resp, dict):
            for p in resp.get("projects", []):
                existing.add(p.get("name"))
        print(f"Existing projects: {len(existing)} ({', '.join(sorted(existing)[:10])}...)")
    print()

    results = {"created": [], "skipped": [], "failed": []}

    for app, host in apps:
        if app in existing and args.skip_existing:
            print(f"  SKIP {app} (project already exists)")
            results["skipped"].append(app)
            continue

        # Vercel project name: ai-whisperers/<app> if team, else just <app>
        project_name = app
        # Build the project creation payload
        body = {
            "name": project_name,
            "framework": "nextjs",
            "rootDirectory": f"apps/{app}",
            "buildCommand": f"cd ../.. && pnpm install --frozen-lockfile && pnpm --filter={app} build",
            "installCommand": "cd ../.. && pnpm install --frozen-lockfile",
            "outputDirectory": f"apps/{app}/.next",
            "gitRepository": {
                "type": "github",
                "repo": "Ai-Whisperers/paragu-ai-platform",
                "productionBranch": "main",
            },
        }
        if team_id:
            body["teamId"] = team_id

        print(f"  CREATE {app} -> https://{host}")
        if args.dry_run:
            print(f"    payload: {json.dumps(body, indent=2)[:400]}...")
            results["created"].append(app)
            continue

        # Create project
        code, resp = vercel("POST", "/v10/projects", token, body=body)
        if code not in (200, 201):
            print(f"    FAIL ({code}): {resp}")
            results["failed"].append((app, code, resp))
            continue
        project_id = resp.get("id")
        print(f"    OK project_id={project_id}")
        results["created"].append(app)

        # Add custom domain
        time.sleep(0.5)  # rate limit politeness
        domain_body = {"name": host}
        if team_id:
            domain_body["teamId"] = team_id
        code, resp = vercel("POST", f"/v10/projects/{project_id}/domains", token, body=domain_body)
        if code not in (200, 201):
            print(f"    DOMAIN FAIL ({code}): {resp}")
        else:
            print(f"    DOMAIN OK -> {host}")
        time.sleep(0.5)

    print()
    print(f"Summary: {len(results['created'])} created, {len(results['skipped'])} skipped, {len(results['failed'])} failed")
    if results["failed"]:
        print("Failures:")
        for app, code, resp in results["failed"]:
            print(f"  {app}: {code} {str(resp)[:200]}")

if __name__ == "__main__":
    main()
