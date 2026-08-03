#!/usr/bin/env python3
"""
Cloudflare proxy monitor for ai-whisperers.org.

Polls the apex and www DNS records every 5 minutes via the CF API.
If `proxied` flips to false on either, writes an alert file that
a Telegram cron can pick up.

Run as a Hermes no_agent cron (zero LLM cost).
"""
import json
import urllib.request
import urllib.error
import sys
import os

ZONE_ID = "67dbf0fb5cf9989be4ce01d1062f4aab"
ALERT_HOSTS = {"ai-whisperers.org", "www.ai-whisperers.org"}
ALERT_FILE = "/tmp/cf_proxy_alert.txt"
TOKEN_FILE = "/tmp/.cf_token"

def get_token():
    # Prefer env, fall back to /tmp token file
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if token:
        return token
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        sys.exit("ERROR: CLOUDFLARE_API_TOKEN not set and /tmp/.cf_token not found. Add to /root/.hermes/.env.")

def cf_get(path, token):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def send_to_hermes_telegram(msg):
    """Write a telegram alert that the next cron tick picks up via the
    bridge. Uses ntfy as a low-friction alternative if Telegram isn't wired."""
    ntfy_topic = "ai-whisperers-alerts"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://ntfy.sh/{ntfy_topic}",
            data=msg.encode(),
            method="POST",
            headers={"Title": "CF Proxy DOWN", "Priority": "urgent", "Tags": "warning,cf"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            pass
    except Exception as e:
        # Fall back to file
        with open(ALERT_FILE, "a") as f:
            f.write(msg + "\n")

def main():
    token = get_token()
    d = cf_get("/dns_records?type=A", token)
    issues = []
    for rec in d.get("result", []):
        if rec["name"] in ALERT_HOSTS:
            if not rec.get("proxied", False):
                issues.append(f"  {rec['name']} -> {rec['content']}  proxied=False")

    if issues:
        msg = "CF PROXY ALERT - ai-whisperers.org\n\n" + "\n".join(issues)
        with open(ALERT_FILE, "w") as f:
            f.write(msg + "\n")
        send_to_hermes_telegram(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)
    else:
        # Clear stale alerts
        if os.path.exists(ALERT_FILE):
            os.remove(ALERT_FILE)
        print("OK: apex + www are orange-cloud proxied")

if __name__ == "__main__":
    main()
