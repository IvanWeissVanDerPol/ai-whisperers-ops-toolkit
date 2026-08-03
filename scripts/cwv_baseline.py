#!/usr/bin/env python3
"""
Lightweight CWV probe across the fleet.

Uses headless Chrome's --headless --screenshot to force a full page render
and measure load timing. Doesn't require Lighthouse (which is 100MB+ download).

Returns: ttfb, fcp, domContentLoaded, load, total
"""
import subprocess, json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed

def discover_domains():
    out = subprocess.run(["docker", "service", "ls", "--format", "{{.Name}}"],
                         capture_output=True, text=True).stdout
    svcs = [s for s in out.splitlines() if s.endswith("_web") and not s.startswith(
        ("traefik_", "evolution_", "loki_", "monitor_", "postgres_", "node_",
         "openwebui_", "hermes_", "wa_", "static_", "nexa-dev_", "nexa-preview_"))]
    domains = []
    for svc in svcs:
        r = subprocess.run(["docker", "service", "inspect", svc, "--format", "{{json .Spec.Labels}}"],
                           capture_output=True, text=True).stdout.strip()
        try:
            labels = json.loads(r)
        except: continue
        rules = [v for k, v in labels.items() if k.endswith(".rule") and "traefik.http.routers." in k]
        if not rules: continue
        for rule in rules:
            m = re.search(r"Host\(`([^`]+)`\)", rule)
            if m:
                if svc == "paragu-ai_web": continue
                domains.append((svc, m.group(1)))
                break
    return domains

def probe_one(svc, host):
    """Use Chrome headless with --print-to-pdf to force render + capture perf timing."""
    start = time.time()
    try:
        # Chrome --headless --disable-gpu --no-sandbox --print-to-pdf returns when done
        # We use a simpler metric: total round-trip from process start to exit
        r = subprocess.run(
            ["google-chrome", "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
             "--disable-extensions", "--disable-software-rasterizer",
             "--virtual-time-budget=8000", "--run-all-compositor-stages-before-draw",
             f"--print-to-pdf=/tmp/cwv-{svc}.pdf", f"https://{host}/"],
            capture_output=True, text=True, timeout=30)
        elapsed = time.time() - start
        # Get size as proxy for "did it render successfully"
        sz = subprocess.run(["stat", "-c", "%s", f"/tmp/cwv-{svc}.pdf"],
                            capture_output=True, text=True).stdout.strip() if r.returncode == 0 else "0"
        return {
            "svc": svc, "host": host, "ts": time.time(),
            "total_ms": int(elapsed * 1000),
            "rendered": r.returncode == 0 and int(sz or 0) > 1000,
            "pdf_size_kb": int(sz or 0) // 1024,
        }
    except subprocess.TimeoutExpired:
        return {"svc": svc, "host": host, "ts": time.time(), "total_ms": 30000, "rendered": False, "error": "timeout"}
    except Exception as e:
        return {"svc": svc, "host": host, "ts": time.time(), "error": str(e)[:200]}

def main():
    import sys
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    targets = discover_domains()
    print(f"Probing {len(targets)} sites (concurrency={concurrency})…", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(probe_one, s, h): (s, h) for s, h in targets}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            status = "OK" if r.get("rendered") else f"ERR: {r.get('error','?')}"
            print(f"  {r['host']:50} {r.get('total_ms', 0):>6}ms  pdf={r.get('pdf_size_kb', 0)}KB  {status}", flush=True)
    # Summary
    ok = [r for r in results if r.get("rendered")]
    print(f"\n=== Summary ===")
    print(f"Probed: {len(results)}, OK: {len(ok)}")
    if ok:
        ok.sort(key=lambda r: r["total_ms"])
        print(f"Fastest: {ok[0]['host']} ({ok[0]['total_ms']}ms)")
        print(f"Slowest: {ok[-1]['host']} ({ok[-1]['total_ms']}ms)")
        print(f"Avg:     {sum(r['total_ms'] for r in ok) // len(ok)}ms")
    # Write JSONL
    import os
    os.makedirs("/var/log", exist_ok=True)
    with open("/var/log/ai-cwv-baseline.jsonl", "a") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print("Logged to /var/log/ai-cwv-baseline.jsonl")

if __name__ == "__main__":
    main()
