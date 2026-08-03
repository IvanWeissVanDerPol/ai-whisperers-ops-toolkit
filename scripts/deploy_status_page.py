#!/usr/bin/env python3
"""
deploy_status_page.py — Deploy the status page to Cloudflare Pages.

Wraps `wrangler pages deploy` with:
1. Re-runs status_page.py to get the latest HTML
2. Copies to a staging dir
3. Runs wrangler pages deploy
4. Reports the deployed URL

Usage:
    python3 ~/.hermes/scripts/deploy_status_page.py
    python3 ~/.hermes/scripts/deploy_status_page.py --project hermes-status
    python3 ~/.hermes/scripts/deploy_status_page.py --dry-run
    python3 ~/.hermes/scripts/deploy_status_page.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
STAGING = Path("/tmp/hermes-status-staging")


def regenerate_page() -> Path:
    """Run status_page.py to ensure latest HTML."""
    result = subprocess.run(
        ["python3", str(HERMES_HOME / "scripts" / "status_page.py")],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"status_page.py failed: {result.stderr}")
    return STATE / "status.html"


def stage_html(html_src: Path, project: str) -> Path:
    """Copy HTML to staging dir as index.html."""
    STAGING.mkdir(parents=True, exist_ok=True)
    idx = STAGING / "index.html"
    shutil.copy(html_src, idx)
    return STAGING


def wrangler_deploy(staging: Path, project: str, dry_run: bool) -> dict:
    """Run wrangler pages deploy.

    Important: when CLOUDFLARE_API_TOKEN is unset in env, wrangler falls back
    to /root/.wrangler/config/default.toml which contains a Wrangler v1
    deprecated config format. Wrangler logs a warning, but if the v1 config
    has stale credentials, the actual API call fails with auth error code 9109.

    The fix: explicitly read the v1 api_token from default.toml and inject it
    into CLOUDFLARE_API_TOKEN so wrangler uses the modern env var and skips
    its v1 config detection entirely.
    """
    if dry_run:
        return {"status": "dry-run", "staged": str(staging), "project": project}
    env = os.environ.copy()
    # Force the token via env so wrangler does NOT read the v1 default.toml
    if not env.get("CLOUDFLARE_API_TOKEN"):
        token_path = Path("/root/.wrangler/config/default.toml")
        if token_path.exists():
            for line in token_path.read_text().split("\n"):
                if "api_token" in line:
                    # Parse: api_token = "cfut_XXX"
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        token = parts[1].strip().strip('"').strip("'")
                        if token:
                            env["CLOUDFLARE_API_TOKEN"] = token
                            break
    if not env.get("CLOUDFLARE_API_TOKEN"):
        return {"status": "error", "error": "no CLOUDFLARE_API_TOKEN found in env or ~/.wrangler/config/default.toml"}
    # Also unset the wrangler config env var if it points to v1 format
    # (prevents wrangler from complaining about deprecated config)
    env.pop("WRANGLER_CONFIG", None)
    try:
        result = subprocess.run(
            ["wrangler", "pages", "deploy", str(staging),
             "--project-name", project, "--commit-dirty=true"],
            capture_output=True, text=True, timeout=300,
            env=env,
        )
        return {
            "status": "ok" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout": 300}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy status page to Cloudflare Pages")
    parser.add_argument("--project", default="hermes-status", help="Pages project name")
    parser.add_argument("--dry-run", action="store_true", help="Stage but don't deploy")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    try:
        html_src = regenerate_page()
        staging = stage_html(html_src, args.project)
        deploy = wrangler_deploy(staging, args.project, args.dry_run)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Parse URL from deploy output
    deployed_url = None
    if deploy.get("stdout"):
        for line in deploy["stdout"].split("\n"):
            if "https://" in line and ".pages.dev" in line:
                # Find URL in line
                for word in line.split():
                    if word.startswith("https://") and ".pages.dev" in word:
                        deployed_url = word.rstrip(".,;:")
                        break
                if deployed_url:
                    break

    result = {
        "skill": "deploy-status-page",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "html_source": str(html_src),
        "staging_dir": str(staging),
        "html_size_bytes": html_src.stat().st_size,
        "deploy": deploy,
        "deployed_url": deployed_url,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n=== Status Page Deploy ===")
        print(f"  Project: {args.project}")
        print(f"  HTML: {html_src} ({result['html_size_bytes']} bytes)")
        print(f"  Staging: {staging}")
        if args.dry_run:
            print(f"  Mode: dry-run (not deployed)")
        else:
            print(f"  Status: {deploy.get('status')}")
            if deployed_url:
                print(f"  URL: {deployed_url}")
            if deploy.get("status") == "failed":
                print(f"  Error: {deploy.get('stderr', '')[:300]}")
    return 0 if deploy.get("status") in ("ok", "dry-run") else 1


if __name__ == "__main__":
    sys.exit(main())