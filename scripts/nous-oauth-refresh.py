#!/usr/bin/env python3
"""
nous-oauth-refresh.py — refreshes OAuth token before expiry.

Originally for Nous Portal (which now uses API key auth via NOUS_PORTAL_KEY),
this script has been generalized to handle any OAuth provider with a refresh_token.
Currently handles the minimax-oauth provider which DOES use OAuth refresh.

Usage:
    python3 nous-oauth-refresh.py            # refresh if needed
    python3 nous-oauth-refresh.py --force    # force refresh

Schedule via cron:
    */10 * * * * python3 /root/.hermes/scripts/nous-oauth-refresh.py

Exit codes:
    0 = refreshed OR no refresh needed OR no OAuth configured (silent)
    1 = refresh failed
    2 = no refresh token available
"""
import os
import sys
import json
import argparse
import datetime
import urllib.request
import urllib.error

HERMES_HOME = os.path.expanduser("~/.hermes")
AUTH_FILE = os.path.join(HERMES_HOME, "auth.json")
LOG_FILE = os.path.join(HERMES_HOME, "logs/nous-oauth-refresh.log")
REFRESH_URL = "https://portal.nousresearch.com/api/oauth/token"
# Refresh when remaining < 5 min (token lasts 15 min, cron runs every 10 min)
REFRESH_THRESHOLD_MIN = 5


def log(level, msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.datetime.now().isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} [{level}] {msg}\n")
    if level == "ERROR":
        print(f"❌ {msg}", file=sys.stderr)
    else:
        print(f"{'✅' if level == 'INFO' else 'ℹ️'} {msg}")


def get_minutes_remaining(expires_at_str):
    """Calculate minutes until token expires."""
    expires_at = datetime.datetime.fromisoformat(expires_at_str.replace("Z", "++00:00"))
    now = datetime.datetime.now(expires_at.tzinfo)
    return (expires_at - now).total_seconds() / 60


def refresh_token(client_id, refresh_token, url=None):
    """POST to OAuth token endpoint."""
    data = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }).encode()

    req = urllib.request.Request(url or REFRESH_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}")


def find_oauth_provider(auth):
    """Find any provider in auth.json that has OAuth refresh capability.

    Priority order:
    1. providers.nous (legacy)
    2. providers.minimax-oauth (current)
    3. credential_pool[].minimax-oauth entries
    """
    providers = auth.get("providers", {})

    # 1. Legacy nous
    for key in ["nous", "minimax-oauth"]:
        p = providers.get(key, {})
        if p.get("refresh_token"):
            return key, p, "providers"

    # 2. Credential pool (array form)
    for key, creds in auth.get("credential_pool", {}).items():
        for i, cred in enumerate(creds):
            if cred.get("refresh_token"):
                return f"{key}[{i}]", cred, "credential_pool"

    return None, None, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Force refresh even if not expiring")
    args = p.parse_args()

    if not os.path.exists(AUTH_FILE):
        log("ERROR", f"{AUTH_FILE} not found")
        return 2

    with open(AUTH_FILE) as f:
        auth = json.load(f)

    provider_name, oauth, location = find_oauth_provider(auth)
    if not oauth or not oauth.get("refresh_token"):
        # Nothing to refresh — silent success
        return 0

    refresh = oauth.get("refresh_token")
    client_id = oauth.get("client_id")
    expires_at = oauth.get("expires_at")

    if not args.force and expires_at:
        try:
            remaining = get_minutes_remaining(expires_at)
        except Exception:
            remaining = 0
        if remaining > REFRESH_THRESHOLD_MIN:
            log("INFO", f"Token valid for {remaining:.1f} min — no refresh needed ({provider_name})")
            return 0

    log("INFO", f"Refreshing OAuth token ({provider_name}, force={args.force})...")
    try:
        result = refresh_token(client_id, refresh)
    except Exception as e:
        log("ERROR", f"Refresh failed: {e}")
        return 1

    new_access = result.get("access_token")
    new_refresh = result.get("refresh_token", refresh)
    expires_in = result.get("expires_in", 900)
    new_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)

    oauth["access_token"] = new_access
    oauth["refresh_token"] = new_refresh
    oauth["expires_at"] = new_expires.isoformat()

    # Write back to correct location
    if location == "providers":
        auth["providers"][provider_name] = oauth
    elif location == "credential_pool":
        # Re-find the entry (already a reference, but write back the array)
        key, idx = provider_name.rstrip("]").split("[")
        auth["credential_pool"][key][int(idx)] = oauth

    with open(AUTH_FILE, "w") as f:
        json.dump(auth, f, indent=2)

    log("INFO", f"Refreshed — expires in {expires_in // 60} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
