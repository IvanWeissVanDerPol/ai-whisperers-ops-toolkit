#!/usr/bin/env python3
"""
anomaly_detector.py — AI-powered anomaly detection on health-snapshots.

Uses a small LLM call to detect anomalies that rule-based diffs miss.

Workflow:
1. Load all 45 health snapshots
2. Build a structured prompt with the data
3. Send to the LLM (via hermes CLI or direct provider)
4. Parse JSON response (anomalies + recommendations)
5. Save to ~/.hermes/state/anomalies.json

Cost-controlled: uses cheap model, max 1 call per run.

Usage:
    python3 ~/.hermes/scripts/anomaly_detector.py
    python3 ~/.hermes/scripts/anomaly_detector.py --repo psycology
    python3 ~/.hermes/scripts/anomaly_detector.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
STATE = HERMES_HOME / "state"
SNAPSHOTS_DIR = STATE / "health-snapshots"
ANOMALIES_PATH = STATE / "anomalies.json"


def load_snapshots(repo_filter: str | None = None) -> list[dict]:
    """Load snapshots, optionally filtered."""
    snapshots = []
    for path in sorted(SNAPSHOTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            if repo_filter and data.get("repo") != repo_filter:
                continue
            snapshots.append(data)
        except Exception:
            continue
    return snapshots


def build_prompt(snapshots: list[dict]) -> str:
    """Build a structured prompt for the LLM."""
    # Truncate to fit token budget
    slim = []
    for s in snapshots:
        slim.append({
            "repo": s.get("repo"),
            "score": s.get("health_score"),
            "branch": s.get("current_branch"),
            "coverage": s.get("coverage", {}).get("final_coverage"),
            "days_since_commit": s.get("git_status", {}).get("days_since_commit"),
            "uncommitted": s.get("git_status", {}).get("uncommitted_files"),
            "gate_passed": s.get("quality_gate", {}).get("gate_passed"),
        })
    snap_str = json.dumps(slim, indent=2)
    return f"""You are an SRE analyzing health snapshots of {len(snapshots)} software projects.

For each project, you have: score (0-100), coverage (0-1), days since last commit, uncommitted files count, gate pass/fail.

Identify:
1. Anomalies — repos with unusual patterns (e.g., high score but stale, low coverage despite recent commits, etc.)
2. Risks — repos likely to break soon (e.g., long-stale, high uncommitted count)
3. Recommendations — top 3 actionable next steps

Output as JSON only:
{{
  "anomalies": [
    {{"repo": "...", "kind": "...", "explanation": "..."}}
  ],
  "risks": [
    {{"repo": "...", "severity": "low|medium|high", "explanation": "..."}}
  ],
  "recommendations": [
    "...",
    "...",
    "..."
  ]
}}

Snapshots:
{snap_str}"""


def call_llm(prompt: str, model: str = "deepseek-chat") -> dict:
    """Call LLM via hermes CLI in --cli mode. Cost-controlled via cheap model."""
    try:
        result = subprocess.run(
            ["hermes", "chat", "-m", model, "--cli"],
            input=prompt,
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            return {"ok": False, "error": f"exit={result.returncode}: {result.stderr[-500:]}"}
        text = result.stdout.strip()
        # The output contains a tools panel + response. Look for the response after
        # the panel by finding the JSON block we requested.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start:end + 1]
            try:
                parsed = json.loads(candidate)
                return {"ok": True, "result": parsed, "raw": text[max(0, start - 50):end + 1][:500]}
            except json.JSONDecodeError:
                # Fallback: use whole text as a recommendation
                return {"ok": True, "result": {"raw_response": text[-500:]}, "raw": text[-500:]}
        return {"ok": False, "error": "no JSON block in response", "raw": text[-500:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "LLM call timed out (>3m)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-powered anomaly detection")
    parser.add_argument("--repo", help="Single repo (default: all)")
    parser.add_argument("--model", default="openrouter/google/gemma-4-31b-it:free", help="LLM model")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM call (rule-based only)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    snapshots = load_snapshots(args.repo)
    if not snapshots:
        print("error: no snapshots found", file=sys.stderr)
        return 2

    # Always include rule-based detection
    rule_anomalies = []
    for s in snapshots:
        score = s.get("health_score", 0)
        cov = s.get("coverage", {}).get("final_coverage", 0)
        days = s.get("git_status", {}).get("days_since_commit")
        uncommitted = s.get("git_status", {}).get("uncommitted_files", 0)
        repo = s.get("repo", "?")
        # Rule 1: stale but high score (suspicious)
        if isinstance(days, (int, float)) and days > 30 and score >= 70:
            rule_anomalies.append({
                "repo": repo, "kind": "stale-but-healthy",
                "explanation": f"score={score} but last commit {days}d ago — likely false positive from old metrics",
            })
        # Rule 2: recent activity but low coverage
        if isinstance(days, (int, float)) and days < 7 and isinstance(cov, (int, float)) and cov < 0.3:
            rule_anomalies.append({
                "repo": repo, "kind": "active-without-tests",
                "explanation": f"active ({days}d) but coverage={cov*100:.0f}% — adding features without tests",
            })
        # Rule 3: many uncommitted files
        if uncommitted > 20:
            rule_anomalies.append({
                "repo": repo, "kind": "many-uncommitted",
                "explanation": f"{uncommitted} uncommitted files — likely work-in-progress",
            })
        # Rule 4: zero coverage with gate passing
        gate_passed = s.get("quality_gate", {}).get("gate_passed")
        if gate_passed and cov == 0:
            rule_anomalies.append({
                "repo": repo, "kind": "gate-without-coverage",
                "explanation": "quality gate passed but 0% coverage — gate may be lenient",
            })

    # LLM-based detection (best-effort, may be unavailable)
    llm_result = None
    if not args.no_llm:
        prompt = build_prompt(snapshots)
        try:
            llm_result = call_llm(prompt, model=args.model)
            # Mark as unavailable if no JSON was produced
            if not llm_result.get("ok"):
                llm_result["available"] = False
            else:
                llm_result["available"] = True
        except Exception as e:
            llm_result = {"ok": False, "error": str(e), "available": False}

    # Combine
    output = {
        "skill": "anomaly-detector",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshots_analyzed": len(snapshots),
        "rule_anomalies": rule_anomalies,
        "rule_anomaly_count": len(rule_anomalies),
        "llm_result": llm_result,
        "model_used": args.model if not args.no_llm else None,
    }
    ANOMALIES_PATH.write_text(json.dumps(output, indent=2))

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"\n=== Anomaly Detector ===")
        print(f"  Snapshots analyzed: {len(snapshots)}")
        print(f"  Rule anomalies: {len(rule_anomalies)}")
        for a in rule_anomalies[:10]:
            print(f"    • [{a['kind']}] {a['repo']}: {a['explanation']}")
        if llm_result:
            if llm_result.get("ok"):
                print(f"\n  LLM call: ✓ (saved anomalies.json)")
            else:
                print(f"\n  LLM call: ✗ {llm_result.get('error', 'unknown')}")
        else:
            print(f"\n  LLM call: skipped (--no-llm)")
        print(f"\n  Report saved to {ANOMALIES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())