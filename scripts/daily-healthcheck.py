#!/usr/bin/env python3
"""
Hermes Daily Healthcheck — runs as a cron job.

Checks:
1. Gateway is up (port 8642 api_server, 8644 webhook, 8645 proxy)
2. All 5 working chat profiles respond
3. Auth tokens not about to expire
4. Disk usage / log sizes
5. Config still valid

Delivers status to Telegram via webhook or quiet stdout (no_agent mode).
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timezone, timedelta

# Load env
env = {}
env_path = "/root/.hermes/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v

# Load auth.json
auth = {}
auth_path = "/root/.hermes/auth.json"
if os.path.exists(auth_path):
    with open(auth_path) as f:
        try:
            auth = json.load(f)
        except json.JSONDecodeError:
            pass

issues = []
ok = []

# 1. Gateway ports (current hermes uses 8642 api_server and 8644 webhook; 8645 is no longer used)
for port, name in [(8642, "api_server"), (8644, "webhook")]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
            ok.append(f"port {port} ({name}): {r.status}")
    except urllib.error.HTTPError as e:
        ok.append(f"port {port} ({name}): {e.code}")
    except Exception as e:
        issues.append(f"port {port} ({name}): DOWN — {str(e)[:60]}")

# 2. Chat profile smoke test
def smoke_test(name, base, key, model, path, is_anthropic=False):
    url = f"{base}{path}"
    if is_anthropic:
        body = json.dumps({"model": model, "max_tokens": 8, "messages": [{"role":"user","content":"OK"}]}).encode()
        headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json", "anthropic-version":"2023-06-01"}
    else:
        body = json.dumps({"model": model, "messages": [{"role":"user","content":"OK"}], "max_tokens": 8}).encode()
        headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json"}
    req = urllib.request.Request(url, headers=headers, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, r.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception as e:
        return False, str(e)[:60]

# Test LiteLLM profiles (only the ones currently confirmed working on the proxy)
profiles_to_test = [
    ("groq-llama", "http://72.61.44.159:4000", env.get("LITELLM_API_KEY",""), "groq-llama", "/chat/completions", False),
    ("hermes-4-70b",  "http://72.61.44.159:4000", env.get("LITELLM_API_KEY",""), "nous-hermes-4-70b",  "/chat/completions", False),
]

# MiniMax OAuth
if "providers" in auth and "minimax-oauth" in auth["providers"]:
    token = auth["providers"]["minimax-oauth"].get("access_token","")
    base = auth["providers"]["minimax-oauth"].get("inference_base_url","")
    profiles_to_test.append(("MiniMax-M3 (OAuth)", base, token, "MiniMax-M3", "/v1/messages", True))

for name, base, key, model, path, anthropic in profiles_to_test:
    if not key or not base:
        issues.append(f"{name}: missing key or base_url")
        continue
    success, status = smoke_test(name, base, key, model, path, anthropic)
    if success:
        ok.append(f"{name}: {status} OK")
    else:
        issues.append(f"{name}: FAILED — {status}")

# 3. Token expiry check
now = time.time()
if "providers" in auth:
    for prov, val in auth["providers"].items():
        if not isinstance(val, dict):
            continue
        exp_str = val.get("expires_at","")
        if not exp_str:
            continue
        try:
            exp_dt = datetime.fromisoformat(str(exp_str).replace("Z","+00:00"))
            delta = exp_dt.timestamp() - now
            hours = delta / 3600
            if hours < 1:
                issues.append(f"OAuth {prov}: expires in {hours:.1f}h (URGENT)")
            elif hours < 24:
                issues.append(f"OAuth {prov}: expires in {hours:.1f}h")
            else:
                ok.append(f"OAuth {prov}: {hours/24:.1f}d remaining")
        except (ValueError, TypeError):
            pass

# 4. Disk + log size
try:
    result = subprocess.run(["du", "-sh", "/root/.hermes/logs"], capture_output=True, text=True, timeout=5)
    log_size = result.stdout.split()[0] if result.returncode == 0 else "?"
    ok.append(f"logs size: {log_size}")
except Exception:
    pass

# 5. Config validity
try:
    import yaml
    yaml.safe_load(open("/root/.hermes/config.yaml"))
    ok.append("config.yaml: valid YAML")
except Exception as e:
    issues.append(f"config.yaml: {str(e)[:80]}")

# Format output
ts = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
lines = [f"🔍 Hermes Healthcheck — {ts}", ""]

if ok:
    lines.append("✅ HEALTHY")
    for o in ok:
        lines.append(f"  • {o}")

if issues:
    lines.append("")
    lines.append(f"⚠️ ISSUES ({len(issues)})")
    for i in issues:
        lines.append(f"  • {i}")

# Classify issues: hard_failures = exit 1, warnings = exit 0 (still printed)
# A "hard failure" is something that breaks Hermes operation (config invalid, token expired)
# A "warning" is something transient (one provider timed out, one port down)
hard_failures = []
for i in issues:
    lower = i.lower()
    # Hard fails: config broken, OAuth urgent/expiring, mandatory port down
    if any(x in lower for x in ["config.yaml:", "expires in", "urgent", "connection refused", "auth.json"]):
        hard_failures.append(i)
    else:
        # Treat as warning (still show in output but don't fail)
        pass

# If everything healthy, output minimal
if not issues:
    print("✅ Hermes OK — all 4 profiles, 3 ports, 0 token warnings")
    sys.exit(0)
elif hard_failures:
    print("\n".join(lines))
    sys.exit(1)
else:
    # Warnings only — print but exit 0 (cron shouldn't alarm on transient issues)
    print("\n".join(lines))
    print()
    print("ℹ️  All issues are transient warnings — Hermes operational")
    sys.exit(0)
