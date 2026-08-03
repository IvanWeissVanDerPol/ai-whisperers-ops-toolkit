#!/usr/bin/env python3
"""
prompt_version_recorder.py — R22-2: Sidecar file that records which prompt version each session used.

Traces don't have a prompt_version field. This tool maintains a sidecar file
that records the mapping:
  session_id -> prompt_name -> prompt_version

When a script uses prompt_registry.get(), it should call:
  recorder.record(session_id, prompt_name, version, tag)

This data is then JOIN-able with traces by session_id to enable per-version
A/B comparison.

Sidecar file: /root/.hermes/state/prompt_version_map.jsonl
Each line: {"timestamp", "session_id", "prompt_name", "version", "tag"}

Usage:
  python3 prompt_version_recorder.py record --session SESSION_ID --name NAME --version VERSION [--tag stable]
  python3 prompt_version_recorder.py status [--session SESSION_ID] [--name NAME]
  python3 prompt_version_recorder.py join [--days N] [--name NAME] [--json]
  python3 prompt_version_recorder.py stats [--name NAME]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SIDECAR_PATH = Path("/root/.hermes/state/prompt_version_map.jsonl")
TRACES_DIR = Path("/root/.hermes/state/traces")


def record(session_id: str, prompt_name: str, version: str, tag: str | None = None) -> None:
    """Append a record to the sidecar file."""
    SIDECAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "prompt_name": prompt_name,
        "version": version,
        "tag": tag,
    }
    with open(SIDECAR_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_sidecar(session: str | None = None, name: str | None = None) -> list[dict]:
    """Load sidecar records, optionally filtered."""
    if not SIDECAR_PATH.exists():
        return []
    records = []
    with open(SIDECAR_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if session and d.get("session_id") != session:
                continue
            if name and d.get("prompt_name") != name:
                continue
            records.append(d)
    return records


def load_traces_for_session(session_id: str) -> list[dict]:
    """Load all traces for a given session_id."""
    if not TRACES_DIR.exists():
        return []
    traces = []
    for tf in sorted(TRACES_DIR.glob("*.jsonl")):
        with open(tf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("session") == session_id:
                    traces.append(d)
    return traces


def join_traces_with_sidecar(days: int = 7, name: str | None = None,
                              only_with_versions: bool = False) -> list[dict]:
    """Join traces with sidecar by session_id. Returns enriched trace records."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = load_sidecar(name=name)
    if not records:
        return []
    # Index sidecar by session_id
    by_session: dict[str, dict] = {}
    for r in records:
        sid = r.get("session_id", "")
        if not sid:
            continue
        # Latest record wins (last one wins)
        by_session[sid] = r
    # Load all traces in time range, enrich with sidecar data
    enriched = []
    if not TRACES_DIR.exists():
        return []
    for tf in sorted(TRACES_DIR.glob("*.jsonl")):
        try:
            file_date = datetime.strptime(tf.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff - timedelta(days=1):
                continue
        except Exception:
            continue
        with open(tf) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts_str = d.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    continue
                if ts < cutoff:
                    continue
                session = d.get("session", "")
                sidecar = by_session.get(session)
                if sidecar:
                    d["prompt_name"] = sidecar["prompt_name"]
                    d["prompt_version"] = sidecar["version"]
                    d["prompt_tag"] = sidecar.get("tag")
                elif only_with_versions:
                    continue
                enriched.append(d)
    return enriched


def stats_for_name(name: str, days: int = 7) -> dict:
    """Get per-version stats for a prompt name."""
    enriched = join_traces_with_sidecar(days=days, name=name)
    by_version: dict[str, dict] = defaultdict(lambda: {
        "calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "latencies": [],
        "errors": 0,
        "models": set(),
    })
    for t in enriched:
        v = t.get("prompt_version", "unknown")
        m = by_version[v]
        m["calls"] += 1
        m["tokens_in"] += t.get("tokens_in", 0)
        m["tokens_out"] += t.get("tokens_out", 0)
        m["cost_usd"] += t.get("cost_usd", 0.0)
        m["latencies"].append(t.get("latency_seconds", 0.0))
        if (t.get("tokens_out") or 0) == 0 and (t.get("cost_usd") or 0) > 0:
            m["errors"] += 1
        if t.get("model"):
            m["models"].add(t["model"])
    # Compute quality score per version
    result = {}
    for v, m in by_version.items():
        lats = sorted(m["latencies"])
        p50 = lats[len(lats) // 2] if lats else 0
        p95 = lats[int(len(lats) * 0.95)] if lats else 0
        error_rate = m["errors"] / max(m["calls"], 1)
        score = 100 - (error_rate * 40) - (m["cost_usd"] / max(m["calls"], 1) * 5) - (p95 / 100 * 10)
        score = max(0, min(100, round(score, 1)))
        result[v] = {
            "calls": m["calls"],
            "tokens_in": m["tokens_in"],
            "tokens_out": m["tokens_out"],
            "cost_usd": round(m["cost_usd"], 4),
            "latency_p50": round(p50, 2),
            "latency_p95": round(p95, 2),
            "errors": m["errors"],
            "error_rate": round(error_rate, 3),
            "models": sorted(m["models"]),
            "score": score,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Record a prompt version usage")
    rec.add_argument("--session", required=True)
    rec.add_argument("--name", required=True)
    rec.add_argument("--version", required=True)
    rec.add_argument("--tag", help="Tag (e.g., stable, prod)")

    stat = sub.add_parser("status", help="Show all sidecar records")
    stat.add_argument("--session", help="Filter by session")
    stat.add_argument("--name", help="Filter by prompt name")

    j = sub.add_parser("join", help="Join traces with sidecar and show")
    j.add_argument("--days", type=int, default=7)
    j.add_argument("--name", help="Filter by prompt name")
    j.add_argument("--only-with-versions", action="store_true")
    j.add_argument("--json", action="store_true")

    st = sub.add_parser("stats", help="Per-version stats for a prompt")
    st.add_argument("--name", required=True)
    st.add_argument("--days", type=int, default=7)
    st.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.cmd == "record":
        record(args.session, args.name, args.version, args.tag)
        print(f"✓ Recorded: session={args.session} name={args.name} version={args.version} tag={args.tag}")
        return 0

    if args.cmd == "status":
        records = load_sidecar(session=args.session, name=args.name)
        if not records:
            print("No records found")
            return 0
        print(f"=== Sidecar Records ({len(records)} entries) ===")
        for r in records[-20:]:  # last 20
            ts = r.get("timestamp", "")[:19]
            print(f"  {ts}  session={r.get('session_id', '')[:20]:20} {r.get('prompt_name', '?'):30} v={r.get('version', '?')}")
        return 0

    if args.cmd == "join":
        enriched = join_traces_with_sidecar(days=args.days, name=args.name,
                                            only_with_versions=args.only_with_versions)
        if args.json:
            print(json.dumps({
                "days": args.days,
                "count": len(enriched),
                "traces": enriched,
            }, indent=2, default=str))
        else:
            print(f"=== Joined Traces (last {args.days} days) ===")
            print(f"Total: {len(enriched)}")
            for t in enriched[:20]:
                v = t.get("prompt_version", "—")
                p = t.get("prompt_name", "—")
                ts = t.get("timestamp", "")[:19]
                sess = t.get("session", "")[:16]
                print(f"  {ts}  {sess:16} {p[:25]:25} v={v}  ${t.get('cost_usd', 0):.4f}")
        return 0

    if args.cmd == "stats":
        result = stats_for_name(args.name, days=args.days)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== Per-version stats for {args.name} ===")
            if not result:
                print("No data with version tags yet")
                return 0
            for v, m in sorted(result.items()):
                marker = "🟢" if m["score"] >= 80 else "🟡" if m["score"] >= 50 else "🔴"
                print(f"  {marker} v={v}")
                print(f"      calls: {m['calls']}, cost: ${m['cost_usd']}, p95: {m['latency_p95']}s, score: {m['score']}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
