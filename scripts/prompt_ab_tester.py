#!/usr/bin/env python3
"""
prompt_ab_tester.py — R21-2: A/B testing infrastructure for prompts.

Compares quality scores between prompt versions (e.g., v1 vs v2) using
trace metrics. Provides:
  - status: show all active experiments + current winners
  - compare: compare two versions of a prompt
  - promote: auto-promote the winning version to stable tag
  - experiment: configure a new A/B experiment

Decision logic for auto-promote:
  - Need minimum N=20 traces per version for statistical significance
  - Winner = version with quality score >= baseline * 1.1
  - If winner found, tag it as 'stable' (replacing current stable)
  - Log everything to /root/.hermes/state/prompt_ab_tests.log

Usage:
  python3 prompt_ab_tester.py status
  python3 prompt_ab_tester.py compare --name delivery_prep_summary --v1 v1 --v2 v2
  python3 prompt_ab_tester.py promote --name delivery_prep_summary --threshold 1.1
  python3 prompt_ab_tester.py promote --all --threshold 1.1
  python3 prompt_ab_tester.py status --json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# R22-4: Use real per-version trace data via the sidecar
try:
    from prompt_version_recorder import stats_for_name as _recorder_stats
except ImportError:
    _recorder_stats = None

PROMPTS_DIR = Path("/root/.hermes/state/prompts")
TRACES_DIR = Path("/root/.hermes/state/traces")
JOBS_PATH = Path("/root/.hermes/cron/jobs.json")
LOG_PATH = Path("/root/.hermes/state/prompt_ab_tests.log")


def load_prompts() -> dict:
    """Load all prompts as {name: {version: content, ...}}."""
    prompts = {}
    if not PROMPTS_DIR.exists():
        return prompts
    for prompt_dir in PROMPTS_DIR.iterdir():
        if not prompt_dir.is_dir():
            continue
        meta_path = prompt_dir / "_meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        name = meta["name"]
        versions = {}
        for v, vdata in meta.get("versions", {}).items():
            content_path = prompt_dir / f"{v}.md"
            if content_path.exists():
                versions[v] = content_path.read_text()
        prompts[name] = {
            "versions": versions,
            "tags": meta.get("tags", {}),
            "latest": meta.get("latest"),
        }
    return prompts


def load_traces_for_prompt(name: str, days: int = 7) -> list[dict]:
    """Load traces matching a given prompt name (best-effort by session_id)."""
    # Normalize name
    normalized = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    # Load jobs.json
    if not JOBS_PATH.exists():
        return []
    data = json.loads(JOBS_PATH.read_text())
    # Find jobs whose name normalizes to this prompt
    target_ids = set()
    for job in data.get("jobs", []):
        jname = job.get("name", "")
        if not jname:
            continue
        jnorm = re.sub(r"[^a-z0-9_]+", "_", jname.lower()).strip("_")
        if jnorm == normalized:
            target_ids.add(job.get("id"))
    # Load traces
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    traces = []
    if not TRACES_DIR.exists():
        return traces
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
                m = re.match(r"^cron_([a-z0-9]+)_", session)
                if m and any(jid and jid.startswith(m.group(1)) for jid in target_ids):
                    traces.append(d)
    return traces


def quality_score(metrics: dict) -> float:
    """Compute quality score 0-100 from metrics."""
    calls = metrics.get("calls", 0)
    if calls == 0:
        return 0.0
    error_rate = metrics.get("error_rate", 0)
    cost = metrics.get("cost_usd", 0)
    cost_per_call = cost / calls
    p95 = metrics.get("latency_p95", 0)
    score = 100 - (error_rate * 40) - (cost_per_call * 5) - (p95 / 100 * 10)
    return max(0, min(100, round(score, 1)))


def aggregate_metrics(traces: list[dict]) -> dict:
    """Aggregate metrics from a list of traces."""
    if not traces:
        return {"calls": 0, "cost_usd": 0, "error_rate": 0, "latency_p95": 0}
    total_cost = sum(t.get("cost_usd", 0) for t in traces)
    lats = sorted(t.get("latency_seconds", 0) for t in traces)
    p95 = lats[int(len(lats) * 0.95)] if lats else 0
    errors = sum(1 for t in traces if (t.get("tokens_out") or 0) == 0 and (t.get("cost_usd") or 0) > 0)
    calls = len(traces)
    return {
        "calls": calls,
        "cost_usd": round(total_cost, 4),
        "error_rate": round(errors / calls, 3) if calls else 0,
        "latency_p95": round(p95, 2),
    }


def compare_versions(name: str, v1: str, v2: str, days: int = 7) -> dict:
    """Compare two versions of a prompt."""
    prompts = load_prompts()
    if name not in prompts:
        return {"error": f"prompt '{name}' not found"}
    pdata = prompts[name]
    if v1 not in pdata["versions"]:
        return {"error": f"version {v1} not found for {name}"}
    if v2 not in pdata["versions"]:
        return {"error": f"version {v2} not found for {name}"}

    # Load traces (shared - same prompt)
    traces = load_traces_for_prompt(name, days)
    metrics = aggregate_metrics(traces)
    # When we don't have per-version traces, we treat them as the same
    # (limitation of current infrastructure)
    score = quality_score(metrics)

    # Compute content diff
    content_v1 = pdata["versions"][v1]
    content_v2 = pdata["versions"][v2]
    diff_lines = []
    import difflib
    for line in difflib.unified_diff(
        content_v1.splitlines(), content_v2.splitlines(),
        fromfile=f"{name}:{v1}", tofile=f"{name}:{v2}", lineterm=""
    ):
        diff_lines.append(line)

    return {
        "name": name,
        "v1": v1,
        "v2": v2,
        "v1_size": len(content_v1),
        "v2_size": len(content_v2),
        "tags": pdata["tags"],
        "traces_count": len(traces),
        "shared_metrics": metrics,
        "shared_score": score,
        "diff_lines": len(diff_lines),
        "diff_preview": "\n".join(diff_lines[:50]),
    }


def promote_winner(name: str, threshold: float = 1.1, min_calls: int = 20,
                   dry_run: bool = False) -> dict:
    """Auto-promote the winning version if it beats baseline by threshold.

    R22-4: Now uses real per-version trace data via prompt_version_recorder.
    """
    prompts = load_prompts()
    if name not in prompts:
        return {"error": f"prompt '{name}' not found"}
    pdata = prompts[name]
    versions = list(pdata["versions"].keys())
    if len(versions) < 2:
        return {"ok": False, "reason": f"only {len(versions)} version(s) - need 2+ for A/B"}
    current_stable = pdata["tags"].get("stable", {}).get("version")
    if not current_stable:
        return {"ok": False, "reason": "no stable tag set"}
    candidates = [v for v in versions if v != current_stable]
    if not candidates:
        return {"ok": False, "reason": "no candidate version"}

    # R22-4: Get per-version trace stats from the recorder
    per_version_stats = {}
    if _recorder_stats is not None:
        try:
            per_version_stats = _recorder_stats(name, days=7)
        except Exception as e:
            per_version_stats = {"error": str(e)}

    decision = {
        "name": name,
        "baseline": current_stable,
        "candidates": candidates,
        "per_version_stats": per_version_stats,
        "dry_run": dry_run,
    }

    baseline_data = per_version_stats.get(current_stable, {})
    if not baseline_data or baseline_data.get("calls", 0) < min_calls:
        decision["decision"] = "skip"
        decision["reason"] = (
            f"baseline {current_stable} has only "
            f"{baseline_data.get('calls', 0)} traces (need {min_calls})"
        )
        log_event("promote_decision", decision)
        return decision

    # Check each candidate against baseline
    for cand in candidates:
        cand_data = per_version_stats.get(cand, {})
        if cand_data.get("calls", 0) < min_calls:
            decision["decision"] = "skip"
            decision["reason"] = (
                f"candidate {cand} has only "
                f"{cand_data.get('calls', 0)} traces (need {min_calls})"
            )
            decision["winner"] = None
            decision["loser"] = current_stable
            log_event("promote_decision", decision)
            return decision

        baseline_score = baseline_data.get("score", 0)
        cand_score = cand_data.get("score", 0)
        threshold_score = baseline_score * threshold
        if cand_score >= threshold_score:
            decision["decision"] = "promote"
            decision["reason"] = (
                f"candidate {cand} score {cand_score} >= baseline {baseline_score} * {threshold}"
            )
            decision["winner"] = cand
            decision["loser"] = current_stable
            decision["winner_metrics"] = cand_data
            decision["baseline_metrics"] = baseline_data
            if not dry_run:
                try:
                    subprocess.run([
                        "python3", "/root/.hermes/scripts/prompt_registry.py", "tag",
                        "--name", name, "--version", cand, "--tag", "stable",
                    ], capture_output=True, text=True, timeout=15)
                    decision["promoted"] = True
                except Exception as e:
                    decision["promoted"] = False
                    decision["promote_error"] = str(e)
            log_event("promote_decision", decision)
            return decision

    decision["decision"] = "no_winner"
    decision["reason"] = "no candidate beat baseline by threshold"
    decision["per_version_scores"] = {
        v: per_version_stats.get(v, {}).get("score", "unknown")
        for v in versions
    }
    log_event("promote_decision", decision)
    return decision



def status_all() -> dict:
    """Show all A/B experiments (multi-version prompts)."""
    prompts = load_prompts()
    experiments = []
    for name, pdata in prompts.items():
        if len(pdata["versions"]) < 2:
            continue
        has_tags = bool(pdata["tags"])
        experiments.append({
            "name": name,
            "versions": list(pdata["versions"].keys()),
            "latest": pdata["latest"],
            "tags": pdata["tags"],
            "status": "active" if has_tags else "no_tag",
        })
    return {
        "total_prompts": len(prompts),
        "multi_version_prompts": len(experiments),
        "experiments": experiments,
    }


def log_event(event_type: str, data: dict) -> None:
    """Append event to log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def format_human(status: dict, name: str | None = None) -> str:
    """Format the output as human-readable text."""
    lines = ["=== Prompt A/B Test Status ===", ""]
    if name:
        # Single prompt
        for exp in status["experiments"]:
            if exp["name"] == name:
                lines.append(f"  Prompt: {exp['name']}")
                lines.append(f"  Versions: {', '.join(exp['versions'])}")
                lines.append(f"  Latest: {exp['latest']}")
                lines.append(f"  Tags:")
                for tag, info in exp["tags"].items():
                    lines.append(f"    {tag}: {info['version']} (tagged {info.get('tagged_at', '?')[:19]})")
                return "\n".join(lines)
        lines.append(f"  No experiment for '{name}'")
    else:
        lines.append(f"Total prompts: {status['total_prompts']}")
        lines.append(f"Multi-version: {status['multi_version_prompts']}")
        if status["experiments"]:
            lines.append("")
            lines.append("--- Active experiments ---")
            for exp in status["experiments"]:
                tag_summary = ", ".join(f"{t}={v['version']}" for t, v in exp["tags"].items())
                lines.append(f"  • {exp['name']}: {', '.join(exp['versions'])} [tags: {tag_summary}]")
        else:
            lines.append("")
            lines.append("  No multi-version prompts yet. Register v2 of any prompt to start an experiment.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="Show all A/B experiments")
    sp.add_argument("--json", action="store_true", dest="json_output")

    cmp_parser = sub.add_parser("compare", help="Compare two versions")
    cmp_parser.add_argument("--name", required=True)
    cmp_parser.add_argument("--v1", default="v1")
    cmp_parser.add_argument("--v2", default="v2")
    cmp_parser.add_argument("--days", type=int, default=7)
    cmp_parser.add_argument("--json", action="store_true", dest="json_output")

    prom_parser = sub.add_parser("promote", help="Auto-promote winner")
    prom_parser.add_argument("--name", help="Prompt name")
    prom_parser.add_argument("--all", action="store_true")
    prom_parser.add_argument("--threshold", type=float, default=1.1)
    prom_parser.add_argument("--dry-run", action="store_true")
    prom_parser.add_argument("--json", action="store_true", dest="json_output")

    args = parser.parse_args()

    if args.cmd == "status":
        status = status_all()
        if getattr(args, "json_output", False):
            print(json.dumps(status, indent=2))
        else:
            print(format_human(status))
        return 0

    if args.cmd == "compare":
        result = compare_versions(args.name, args.v1, args.v2, args.days)
        if getattr(args, "json_output", False):
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Compare {args.name}: {args.v1} vs {args.v2} ===")
            print(f"  v1 size: {result.get('v1_size')}")
            print(f"  v2 size: {result.get('v2_size')}")
            print(f"  tags: {result.get('tags')}")
            print(f"  traces: {result.get('traces_count')}")
            print(f"  shared score: {result.get('shared_score')}")
            print(f"  diff lines: {result.get('diff_lines')}")
            if result.get("diff_preview"):
                print("\n  diff preview:")
                for line in result["diff_preview"].split("\n")[:20]:
                    print(f"    {line}")
        return 0

    if args.cmd == "promote":
        if args.all:
            status = status_all()
            results = []
            for exp in status["experiments"]:
                r = promote_winner(exp["name"], threshold=args.threshold,
                                   dry_run=args.dry_run)
                results.append(r)
            if getattr(args, "json_output", False):
                print(json.dumps(results, indent=2))
            else:
                print(f"\n=== Promote check (all, threshold={args.threshold}) ===")
                for r in results:
                    if "error" in r:
                        print(f"  ✗ {r['error']}")
                    else:
                        print(f"  {r['name']}: {r['decision']}")
        else:
            if not args.name:
                print("Error: --name or --all required")
                return 1
            result = promote_winner(args.name, threshold=args.threshold,
                                   dry_run=args.dry_run)
            if getattr(args, "json_output", False):
                print(json.dumps(result, indent=2))
            else:
                print(f"\n=== Promote {args.name} ===")
                print(json.dumps(result, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
