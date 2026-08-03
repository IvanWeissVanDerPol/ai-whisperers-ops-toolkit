#!/usr/bin/env python3
"""
Daily uptime SLA report. Reads /var/log/fleet_health.log (JSONL, one entry per
probe every 5 min = 288 probes/day) and calculates per-site uptime %.

Output: /root/.hermes/analysis/<date>/uptime-sla.md (markdown)
        /var/log/ai-uptime-sla.jsonl (machine-readable, append)
"""
import json, os, sys, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

LOG = "/var/log/fleet_health.log"
PERIOD_HOURS = int(os.environ.get("PERIOD_HOURS", "24"))

def parse_log(since_ts):
    """Return {host: [(ts, code), ...]}"""
    by_host = defaultdict(list)
    if not os.path.exists(LOG):
        return by_host
    with open(LOG) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except: continue
            # Probe entry: has "host" + "code" + "ts"
            if "host" in entry and "code" in entry and "ts" in entry:
                ts = entry["ts"]
                # Skip summary lines (no per-probe data)
                if isinstance(entry.get("code"), list): continue
                if ts < since_ts: continue
                by_host[entry["host"]].append((entry["ts"], int(entry["code"])))
    return by_host

def calc_uptime(probes):
    """probes: [(ts_str, code), ...]"""
    if not probes: return None
    total = len(probes)
    healthy = sum(1 for _, c in probes if c == 200 or (300 <= c < 400))
    if total == 0: return None
    return {
        "probes": total,
        "healthy": healthy,
        "uptime_pct": round(100.0 * healthy / total, 3),
        "errors": [c for _, c in probes if c not in (200,) and not (300 <= c < 400)][:10],
        "first_probe": probes[0][0],
        "last_probe": probes[-1][0],
    }

def main():
    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=PERIOD_HOURS)).isoformat().replace("+00:00", "Z")
    by_host = parse_log(since)
    
    if not by_host:
        print(f"No probes found since {since}. Run fleet_health_check.sh first.")
        return
    
    lines = [
        f"# Uptime SLA Report — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"_Period: last {PERIOD_HOURS}h | Probes: every 5 min | Sites: {len(by_host)}_",
        "",
        "## Tier 1: 99.9% SLA (production sites)",
        "",
        "| Site | Probes | Healthy | Uptime % | Status |",
        "|---|---|---|---|---|",
    ]
    sla_data = {}
    for host, probes in sorted(by_host.items()):
        u = calc_uptime(probes)
        if not u: continue
        sla_data[host] = u
        status = "🟢" if u["uptime_pct"] >= 99.9 else "🟡" if u["uptime_pct"] >= 99.0 else "🔴"
        lines.append(f"| {host} | {u['probes']} | {u['healthy']} | {u['uptime_pct']}% | {status} |")
    lines.extend([
        "",
        "## Aggregate",
        "",
    ])
    uptimes = [u["uptime_pct"] for u in sla_data.values() if u]
    if uptimes:
        avg = sum(uptimes) / len(uptimes)
        lines.extend([
            f"- Total sites monitored: {len(sla_data)}",
            f"- Average uptime: {round(avg, 3)}%",
            f"- Sites at 100% (perfect): {sum(1 for u in uptimes if u == 100.0)}",
            f"- Sites at >=99.9% (SLA met): {sum(1 for u in uptimes if u >= 99.9)}",
            f"- Sites at <99% (degraded): {sum(1 for u in uptimes if u < 99.0)}",
            "",
        ])
    # Date dir
    date = now.strftime("%Y-%m-%d")
    out_dir = f"/root/.hermes/analysis/{date}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/uptime-sla.md"
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    # JSONL
    with open("/var/log/ai-uptime-sla.jsonl", "a") as f:
        f.write(json.dumps({"ts": now.isoformat(), "period_hours": PERIOD_HOURS, "by_host": sla_data}, default=str) + "\n")
    print(f"Report: {out_path}")
    print(f"  Sites: {len(sla_data)}")
    if uptimes:
        print(f"  Avg uptime: {round(avg, 3)}%")
        bad = [h for h, u in sla_data.items() if u["uptime_pct"] < 99.0]
        if bad:
            print(f"  Sites below 99%: {bad}")
        else:
            print(f"  All sites at >=99%")

if __name__ == "__main__":
    main()
