#!/usr/bin/env python3
import json, os, shutil, socket, subprocess, urllib.request, urllib.error, shlex

alerts = []

def run(cmd, timeout=15):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()
    except subprocess.CalledProcessError as e:
        return e.output.strip()
    except Exception as e:
        return f"ERROR: {e}"

# Disk threshold
usage = shutil.disk_usage("/")
used_pct = int((usage.used / usage.total) * 100)
if used_pct >= 75:
    alerts.append(f"Disk high: / is {used_pct}% used ({usage.free//(1024**3)}GB free)")

# Docker builder cache threshold
out = run("docker system df --format '{{json .}}' 2>/dev/null", 30)
for line in out.splitlines():
    try:
        row = json.loads(line)
    except Exception:
        continue
    if row.get("Type") == "Build Cache":
        size = row.get("Size", "")
        # human string parsing, alert on GB > 20 when possible
        import re
        m = re.match(r"([0-9.]+)GB", size)
        if m and float(m.group(1)) > 20:
            alerts.append(f"Docker build cache high: {size}")

# Core processes/endpoints
if run("systemctl is-active cloudflared") != "active":
    alerts.append("cloudflared is not active")

bridge_state = run("systemctl --user is-active hermes-gateway-docker-bridge.service 2>/dev/null")
if bridge_state != "active":
    alerts.append(f"Hermes Docker bridge inactive: {bridge_state}")

for label, url in [
    ("Hermes gateway", "http://127.0.0.1:8642/health"),
    ("Hermes Docker bridge", "http://172.17.0.1:8642/health"),
]:
    try:
        body = urllib.request.urlopen(url, timeout=5).read().decode()
        if '"status": "ok"' not in body and '"status":"ok"' not in body:
            alerts.append(f"{label} health unexpected: {body[:120]}")
    except Exception as e:
        alerts.append(f"{label} health failed: {e}")

try:
    req = urllib.request.Request("http://127.0.0.1:8789/api/auth-check")
    body = urllib.request.urlopen(req, timeout=8).read().decode()
    if "authRequired" not in body:
        alerts.append(f"Workspace auth-check unexpected: {body[:120]}")
except Exception as e:
    alerts.append(f"Workspace auth-check failed: {e}")

# Authenticated file API regression check. This catches the former /api/files 500
# caused by a missing/wrong workspace root inside the Swarm container.
try:
    cid = run("docker ps --filter label=com.docker.swarm.service.name=hermes-ws_hermes-workspace -q | head -1", 10)
    if not cid:
        alerts.append("Workspace container not found")
    else:
        js = r'''
(async()=>{
  const password = process.env.HERMES_PASSWORD || '';
  const auth = await fetch('http://127.0.0.1:3000/api/auth', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({password})});
  const cookie = (auth.headers.get('set-cookie') || '').split(';')[0];
  const files = await fetch('http://127.0.0.1:3000/api/files?action=list&maxDepth=1&maxEntries=50', {headers:{cookie}});
  console.log(files.status);
})();
'''
        status = run("docker exec " + shlex.quote(cid) + " node -e " + shlex.quote(js), 15).splitlines()[-1].strip()
        if status != "200":
            alerts.append(f"Workspace files API returned HTTP {status}")
except Exception as e:
    alerts.append(f"Workspace files API check failed: {e}")

# WhatsApp bridge: report only if cron jobs still target WhatsApp and gateway logs show reconnect failures
cron_jobs = "/root/.hermes/cron/jobs.json"
if os.path.exists(cron_jobs):
    try:
        data = json.load(open(cron_jobs))
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        wa_jobs = [j for j in jobs if "whatsapp" in str(j.get("deliver", ""))]
        if wa_jobs:
            log = run("tail -80 /root/.hermes/logs/gateway.log 2>/dev/null | grep -i 'Reconnect whatsapp error\|whatsapp error' | tail -3", 10)
            if log:
                alerts.append(f"WhatsApp delivery risk: {len(wa_jobs)} cron jobs target WhatsApp; recent reconnect errors present")
    except Exception as e:
        alerts.append(f"Could not inspect cron delivery: {e}")

if alerts:
    print("AIW ops watchdog alert:\n" + "\n".join(f"- {a}" for a in alerts))
