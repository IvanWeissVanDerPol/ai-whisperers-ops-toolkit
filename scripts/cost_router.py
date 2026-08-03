#!/usr/bin/env python3
"""
cost_router.py — Atlas followup: Auto-pick the cheapest working model for cron LLM calls.

Strategy:
  1. Maintain a tier list of (provider, model) pairs ordered by cost
  2. For each tier, attempt a small probe request
  3. Use the FIRST tier that responds successfully
  4. Return the chosen (provider, model, base_url) tuple

Tier ordering (cheapest first):
  T1: cerebras/gpt-oss-20b (free tier, fast)
  T2: cerebras/gpt-oss-120b (free tier, larger)
  T3: anthropic/claude-sonnet-4-6 (paid, $3/MTok)
  T4: anthropic/claude-sonnet-4-5 (paid, fallback)

Usage:
  python3 cost_router.py probe              # run probes, show results
  python3 cost_router.py recommend         # print recommended (provider, model, base_url)
  python3 cost_router.py recommend --json
  python3 cost_router.py set-cron <id>     # apply recommendation to a cron job
  python3 cost_router.py audit             # audit all LLM-driven crons
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


# Tier list — (provider, model, base_url, api_key_env)
# Ordered cheapest first
# R19-2: Updated with base_url defaults for minimax-oauth and anthropic
TIERS = [
    ("cerebras", "gpt-oss-20b", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    ("cerebras", "gpt-oss-120b", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    ("minimax-oauth", "MiniMax-M3", "https://api.minimax.io/v1", "MINIMAX_API_KEY"),
    ("anthropic", "claude-sonnet-4-6", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    ("anthropic", "claude-sonnet-4-5", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
]

PROBE_MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Reply with the single word: OK"},
]


def _load_env() -> None:
    """Load API keys from ~/.hermes/.env into os.environ (one-time)."""
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().split(chr(10)):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # Don't override existing env
        os.environ.setdefault(key, val)


def probe_tier(provider: str, model: str, base_url: str, api_key_env: str, timeout: int = 10) -> dict:
    """Probe a single tier with a small request. Returns {ok, latency_seconds, error}."""
    _load_env()
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        return {"ok": False, "error": f"no {api_key_env} in env", "latency_seconds": 0}

    payload = {
        "model": model,
        "messages": PROBE_MESSAGES,
        "max_tokens": 5,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if not base_url:
        # No base_url = provider default - skip probing
        return {"ok": False, "error": "no base_url", "latency_seconds": 0}

    url = f"{base_url.rstrip('/')}/chat/completions"
    start = time.time()
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "-X", "POST", url,
             "-H", f"Content-Type: {headers['Content-Type']}",
             "-H", f"Authorization: {headers['Authorization']}",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        elapsed = time.time() - start
        body = r.stdout
        if '"choices"' in body:
            return {"ok": True, "latency_seconds": round(elapsed, 2), "error": None}
        # Detect specific errors
        if "credit_balance_exhausted" in body or "insufficient_quota" in body:
            return {"ok": False, "latency_seconds": round(elapsed, 2),
                    "error": "no_credits"}
        if "429" in body:
            return {"ok": False, "latency_seconds": round(elapsed, 2),
                    "error": "rate_limited"}
        if "401" in body:
            return {"ok": False, "latency_seconds": round(elapsed, 2),
                    "error": "unauthorized"}
        if "404" in body or "not found" in body.lower():
            return {"ok": False, "latency_seconds": round(elapsed, 2),
                    "error": "model_not_found"}
        return {"ok": False, "latency_seconds": round(elapsed, 2),
                "error": body[:200]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "latency_seconds": timeout, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "latency_seconds": 0, "error": str(e)}


def probe_all_tiers() -> list[dict]:
    """Probe all tiers. Returns list of {provider, model, ...probe_result}."""
    results = []
    for provider, model, base_url, api_key_env in TIERS:
        r = probe_tier(provider, model, base_url, api_key_env)
        r["provider"] = provider
        r["model"] = model
        results.append(r)
    return results


def recommend(results: list[dict] | None = None) -> dict:
    """Pick the first working tier. Returns {provider, model, base_url}."""
    if results is None:
        results = probe_all_tiers()
    for r in results:
        if r["ok"]:
            return {
                "provider": r["provider"],
                "model": r["model"],
                "base_url": next((t[2] for t in TIERS if t[0] == r["provider"] and t[1] == r["model"]), ""),
            }
    # Nothing works — fall back to first
    provider, model, base_url, _ = TIERS[0]
    return {"provider": provider, "model": model, "base_url": base_url,
            "warning": "no tier responded; returning first tier as fallback"}


def audit_crons() -> list[dict]:
    """Audit all LLM-driven crons and show their model config."""
    jobs_path = Path("/root/.hermes/cron/jobs.json")
    if not jobs_path.exists():
        return []
    data = json.loads(jobs_path.read_text())
    results = []
    for job in data.get("jobs", []):
        # Skip script-driven crons (no_agent=True)
        if job.get("no_agent"):
            continue
        # Skip crons with empty prompt (script-driven via different mechanism)
        if not job.get("prompt"):
            continue
        results.append({
            "id": job.get("id"),
            "name": job.get("name"),
            "provider": job.get("provider"),
            "model": job.get("model"),
            "last_status": job.get("last_status"),
            "last_error": (job.get("last_error") or "")[:80] if job.get("last_error") else None,
        })
    return results


def apply_to_cron(job_id: str, rec: dict) -> dict:
    """Apply recommendation to a cron job in jobs.json."""
    jobs_path = Path("/root/.hermes/cron/jobs.json")
    data = json.loads(jobs_path.read_text())
    for job in data.get("jobs", []):
        if job.get("id") == job_id:
            old = {
                "provider": job.get("provider"),
                "model": job.get("model"),
                "base_url": job.get("base_url"),
            }
            job["provider"] = rec["provider"]
            job["model"] = rec["model"]
            if rec["base_url"]:
                job["base_url"] = rec["base_url"]
            elif "base_url" in job:
                del job["base_url"]
            # Clear api_key (let env var resolve)
            job["api_key"] = ""
            jobs_path.write_text(json.dumps(data, indent=2))
            return {"ok": True, "job_id": job_id, "old": old, "new": {
                "provider": job["provider"], "model": job["model"],
                "base_url": job.get("base_url")}}
    return {"ok": False, "error": f"job {job_id} not found"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe", help="Probe all tiers")
    sub.add_parser("recommend", help="Recommend the best tier")
    sub.add_parser("audit", help="Audit LLM-driven crons")

    set_parser = sub.add_parser("set-cron", help="Apply recommendation to a cron")
    set_parser.add_argument("job_id", help="Cron job ID")

    args = parser.parse_args()

    if args.cmd == "probe":
        results = probe_all_tiers()
        for r in results:
            mark = "✓" if r["ok"] else "✗"
            err = r.get("error") or ""
            print(f"  {mark} {r['provider']}/{r['model']:25} {r['latency_seconds']:>5.2f}s  {err}")
        return 0

    if args.cmd == "recommend":
        results = probe_all_tiers()
        rec = recommend(results)
        print(json.dumps(rec, indent=2))
        return 0

    if args.cmd == "audit":
        results = audit_crons()
        print(f"LLM-driven crons: {len(results)}")
        for r in results:
            status = r["last_status"] or "?"
            mark = "✓" if status == "ok" else "✗"
            err = f" — {r['last_error']}" if r["last_error"] else ""
            print(f"  {mark} {r['name'][:35]:35} {r['provider']:15} {r['model']:20}{err}")
        return 0

    if args.cmd == "set-cron":
        rec = recommend()
        result = apply_to_cron(args.job_id, rec)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())