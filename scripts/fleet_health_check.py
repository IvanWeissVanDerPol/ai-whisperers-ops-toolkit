#!/usr/bin/env python3
"""
Fleet health probe — Ai-Whisperers client sites

Discovers domains from Docker Swarm service labels, probes each in parallel,
writes JSONL + summary to /var/log/fleet_health.log.

Alerting channels (in order of preference):
  1. Custom webhook URL via FLEET_ALERT_WEBHOOK env (Slack/Discord/Teams compatible)
  2. Telegram via TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env
  3. Local alert log (always works, no deps)

Alert deduplication: keeps state in /var/lib/fleet_health/state.json. Only
fires alert when state changes (healthy→degraded or vice versa), AND at most
once per 30 min per (host, code) tuple.

Exit codes: 0 = all healthy, 1 = degraded, 2 = total failure
"""
import subprocess, json, re, sys, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed

LOG = "/var/log/fleet_health.log"
ALERT_LOG = "/var/log/ai-alerts.log"
STATE_DIR = "/var/lib/fleet_health"
STATE_FILE = f"{STATE_DIR}/state.json"
TIMEOUT = 10
CONCURRENCY = 15

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG), exist_ok=True)
os.makedirs(os.path.dirname(ALERT_LOG), exist_ok=True)

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"last_alert": {}, "last_status": {}}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, STATE_FILE)

def send_alert(alert_type, message, problems=None):
    """Send to webhook + telegram + log. Dedup based on (host, code) in 30min window."""
    state = load_state()
    now = time.time()
    last = state["last_alert"].get(alert_type, 0)
    # Fire only if state changed OR >30 min since last
    if problems:
        sig = "|".join(sorted(set(f"{p[1]}|{p[2]}" for p in problems)))
    else:
        sig = "ok"
    last_sig = state.get("last_sig", {}).get(alert_type, "")
    is_state_change = sig != last_sig
    is_30min = (now - last) > 1800
    if not (is_state_change or is_30min):
        return False
    state["last_alert"][alert_type] = now
    state.setdefault("last_sig", {})[alert_type] = sig
    save_state(state)
    # Log
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(ALERT_LOG, "a") as f:
        f.write(json.dumps({"ts": ts, "type": alert_type, "msg": message, "sig": sig}) + "\n")
    # Webhook (with HMAC-SHA256 signature if FLEET_ALERT_SECRET is set)
    webhook = os.environ.get("FLEET_ALERT_WEBHOOK")
    if webhook:
        try:
            import hmac, hashlib
            payload_str = json.dumps({"text": message, "type": alert_type, "problems": problems or []})
            cmd = ["curl", "-s", "-X", "POST", "-H", "Content-Type: application/json",
                   "-d", payload_str, webhook]
            secret = os.environ.get("FLEET_ALERT_SECRET", "")
            if secret:
                sig = "sha256=" + hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
                cmd.extend(["-H", f"X-Hub-Signature-256: {sig}"])
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except: pass
    # Telegram
    bot = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if bot and chat:
        try:
            subprocess.run(
                ["curl", "-s", "-X", "POST",
                 f"https://api.telegram.org/bot{bot}/sendMessage",
                 "-d", f"chat_id={chat}&text={message}&parse_mode=Markdown"],
                capture_output=True, text=True, timeout=10)
        except: pass
    return True

def discover():
    out = subprocess.run(["docker", "service", "ls", "--format", "{{.Name}}"],
                         capture_output=True, text=True).stdout
    svcs = [s for s in out.splitlines()
            if s.endswith("_web") and not s.startswith(
                ("traefik_", "evolution_", "loki_", "monitor_", "postgres_",
                 "node_", "openwebui_", "hermes_", "wa_", "static_",
                 "nexa-dev_", "nexa-preview_"))]
    result = {}
    for svc in svcs:
        r = subprocess.run(["docker", "service", "inspect", svc,
                            "--format", "{{json .Spec.Labels}}"],
                           capture_output=True, text=True).stdout.strip()
        try:
            labels = json.loads(r)
        except: continue
        rules = [v for k, v in labels.items() if k.endswith(".rule") and "traefik.http.routers." in k]
        if not rules: continue
        hosts = re.findall(r"Host\(`([^`]+)`\)", " ".join(rules))
        if hosts:
            result[svc] = hosts[0]
    # Always also probe the marketing site + dashboard
    result["__marketing"] = "paragu-ai.com"
    result["__dashboard"] = "dashboard.paragu-ai.com"
    return result

def probe(host):
    try:
        r = subprocess.run(
            ["curl", "-skL", "-o", "/dev/null", "-w", "%{http_code}|%{time_total}",
             "--max-time", str(TIMEOUT), f"https://{host}/"],
            capture_output=True, text=True, timeout=TIMEOUT + 3)
        out = r.stdout.strip()
        code, t = out.split("|", 1) if "|" in out else ("ERR", "0")
        return code, float(t)
    except Exception:
        return "000", 0.0

def main():
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    targets = discover()
    if not targets:
        with open(LOG, "a") as f:
            f.write(json.dumps({"ts": ts, "level": "error", "msg": "no services discovered"}) + "\n")
        sys.exit(2)

    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(probe, h): (s, h) for s, h in targets.items()}
        for f in as_completed(futs):
            svc, host = futs[f]
            code, t = f.result()
            results.append((svc, host, code, t))

    ok = redirect = degraded = down = 0
    problems = []
    with open(LOG, "a") as f:
        for svc, host, code, t in results:
            f.write(json.dumps({"ts": ts, "svc": svc, "host": host,
                                "code": int(code) if code.isdigit() else 0, "t": t}) + "\n")
            if code == "200": ok += 1
            elif code.startswith("3"): redirect += 1
            elif code in ("000",): down += 1; problems.append((svc, host, code, t))
            elif code in ("404", "502", "503", "504"): degraded += 1; problems.append((svc, host, code, t))
            else: degraded += 1; problems.append((svc, host, code, t))

        total = len(results)
        summary = {"ts": ts, "total": total, "ok": ok, "redirects": redirect,
                   "degraded": degraded, "down": down}
        f.write(json.dumps(summary) + "\n")

    print(f"{time.strftime('%H:%M:%S', time.localtime())}  total={total}  ok={ok}  3xx={redirect}  4xx/5xx={degraded}  down={down}")

    # Track state for change detection
    state = load_state()
    new_status = "healthy" if (degraded == 0 and down == 0) else "degraded"
    prev_status = state.get("overall", "unknown")
    state["overall"] = new_status
    save_state(state)

    if degraded > 0 or down > 0:
        examples = [f"{h} ({c})" for _, h, c, _ in problems[:5]]
        msg = f"\U0001F6A8 *Fleet degraded*: {degraded} errors, {down} unreachable.\n" + "\n".join(f"  - {e}" for e in examples)
        sent = send_alert("fleet_degraded", msg, [(s, h, c, t) for s, h, c, t in problems])
        if sent:
            print(f"  alert sent ({len(problems)} problems)")
        sys.exit(1)
    elif prev_status == "degraded":
        # Recovery
        send_alert("fleet_recovered",
                   f"\u2705 *Fleet recovered*: all {total} sites back to 200/3xx.")
    sys.exit(0)

if __name__ == "__main__":
    main()
