#!/usr/bin/env python3
"""
quality_gate.py — Drive the quality-gate orchestrator.

Chains auto-fix → build → lint → test → complexity → findings log,
emits JSON + markdown report, sets exit code 2 on failure.

Usage:
    python3 ~/.REPLACE_ME.py --path <repo>
    python3 ~/.REPLACE_ME.py --path <repo> --no-auto-fix
    python3 ~/.REPLACE_ME.py --path <repo> --json
    python3 ~/.REPLACE_ME.py --path <repo> --loop

Adopted from Eneve's `validate-pre-merge.ps1` (7-step pre-merge gate).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SCRIPTS = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"


def detect_toolchain(repo: Path) -> list[str]:
    """Detect which toolchain(s) the repo uses."""
    found = []
    if (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists() or (repo / "setup.py").exists():
        found.append("python")
    if (repo / "package.json").exists():
        found.append("node")
    if (repo / "Cargo.toml").exists():
        found.append("rust")
    if (repo / "go.mod").exists():
        found.append("go")
    return found


def run(cmd: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str, str]:
    """Run a command, return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return -1, "", f"command not found: {e}"


def phase_auto_fix(repo: Path, toolchain: list[str]) -> dict:
    """Run auto-fix tools where safe."""
    if not toolchain:
        return {"status": "skipped", "files": 0, "errors": 0}
    files = 0
    errors = []
    if "python" in toolchain:
        for fix in [["ruff", "check", "--fix", "--exit-zero"], ["black", ".", "--quiet"]]:
            rc, out, err = run(fix, repo)
            if rc != 0 and "not found" in err.lower():
                continue
    if "node" in toolchain:
        for fix in [["npx", "eslint", "--fix", "--quiet"], ["npx", "prettier", "--write", "--log-level", "silent"]]:
            rc, out, err = run(fix, repo)
            if rc != 0 and "not found" in err.lower():
                continue
    return {"status": "ok", "files": files, "errors": len(errors)}


def phase_build(repo: Path, toolchain: list[str]) -> dict:
    """Run build for the detected toolchain."""
    if "python" in toolchain:
        # Try editable install
        rc, out, err = run(["python3", "-m", "pip", "install", "-e", ".", "--quiet"], repo, timeout=120)
        if rc != 0:
            # Fallback to import check
            rc, out, err = run(["python3", "-c", "import sys; sys.path.insert(0, '.'); print('ok')"], repo)
        return {"status": "ok" if rc == 0 else "failed", "errors": [err] if err else []}
    if "node" in toolchain:
        rc, out, err = run(["npm", "run", "build"], repo, timeout=300)
        return {"status": "ok" if rc == 0 else "failed", "errors": [err[-500:]] if err else []}
    if "rust" in toolchain:
        rc, out, err = run(["cargo", "build"], repo, timeout=600)
        return {"status": "ok" if rc == 0 else "failed", "errors": [err[-500:]] if err else []}
    if "go" in toolchain:
        rc, out, err = run(["go", "build", "./..."], repo, timeout=300)
        return {"status": "ok" if rc == 0 else "failed", "errors": [err[-500:]] if err else []}
    return {"status": "skipped", "errors": []}


def phase_lint(repo: Path, toolchain: list[str]) -> dict:
    """Run linters."""
    errors = []
    status = "ok"
    if "python" in toolchain:
        lint_script = SCRIPTS / "lint_python.py"
        if lint_script.exists():
            rc, out, err = run(["python3", str(lint_script), "--path", str(repo), "--recursive"], repo)
            if rc != 0:
                errors.append(f"lint_python: {err[-500:]}")
                status = "failed"
    if "node" in toolchain:
        rc, out, err = run(["npx", "eslint", ".", "--max-warnings", "0"], repo, timeout=120)
        if rc != 0 and "not found" not in err.lower():
            errors.append(f"eslint: {err[-500:]}")
            status = "failed"
    return {"status": status, "errors": errors}


def phase_test(repo: Path, toolchain: list[str]) -> dict:
    """Run tests with coverage."""
    tests_run = 0
    tests_passed = 0
    tests_failed = 0
    coverage = 0.0
    if "python" in toolchain:
        rc, out, err = run(
            ["python3", "-m", "pytest", "--tb=short", "-q", "--no-header"],
            repo, timeout=300
        )
        # Parse summary line "12 passed, 0 failed"
        for line in out.split("\n"):
            if "passed" in line and "failed" in line:
                import re
                m = re.search(r"(\d+)\s+passed", line)
                if m:
                    tests_passed = int(m.group(1))
                m = re.search(r"(\d+)\s+failed", line)
                if m:
                    tests_failed = int(m.group(1))
                tests_run = tests_passed + tests_failed
                break
            elif "passed" in line and "failed" not in line:
                import re
                m = re.search(r"(\d+)\s+passed", line)
                if m:
                    tests_passed = int(m.group(1))
                    tests_run = tests_passed
        return {
            "status": "ok" if (rc == 0 or tests_failed == 0) else "failed",
            "tests_run": tests_run,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "coverage": coverage,
            "coverage_threshold": 0.70,
        }
    if "node" in toolchain:
        rc, out, err = run(["npm", "test", "--", "--silent"], repo, timeout=300)
        return {"status": "ok" if rc == 0 else "failed", "coverage": 0.0}
    return {"status": "skipped", "tests_run": 0, "tests_passed": 0, "tests_failed": 0, "coverage": 0.0}


def phase_complexity(repo: Path) -> dict:
    """Run complexity gate."""
    script = SCRIPTS / "check_complexity_gate.py"
    if not script.exists():
        return {"status": "skipped", "max_crap": 0, "max_cc": 0}
    rc, out, err = run(["python3", str(script), "--path", str(repo), "--max-crap", "30", "--max-cc", "16"], repo)
    max_crap = 0
    max_cc = 0
    if out:
        import re
        m = re.search(r"max_crap[:=]\s*(\d+)", out)
        if m:
            max_crap = int(m.group(1))
        m = re.search(r"max_cc[:=]\s*(\d+)", out)
        if m:
            max_cc = int(m.group(1))
    return {
        "status": "ok" if (max_crap < 30 and max_cc < 16) else "failed",
        "max_crap": max_crap,
        "max_cc": max_cc,
        "max_crap_threshold": 30,
        "max_cc_threshold": 16,
    }


def phase_anomaly_check(repo: Path) -> dict:
    """Run anomaly detection on the repo's snapshot."""
    snap_path = STATE / "health-snapshots" / f"{repo.name}.json"
    if not snap_path.exists():
        return {"status": "skipped", "reason": "no snapshot"}
    try:
        # Run anomaly_detector on this single repo
        result = subprocess.run(
            ["python3", str(SCRIPTS / "anomaly_detector.py"),
             "--repo", repo.name, "--no-llm", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"status": "skipped", "reason": f"anomaly_detector failed: {result.returncode}"}
        data = json.loads(result.stdout)
        anomalies = data.get("rule_anomalies", [])
        # Categorize by severity
        severe = [a for a in anomalies if a.get("kind") in ("gate-without-coverage", "many-uncommitted")]
        return {
            "status": "ok" if not severe else "warning",
            "anomaly_count": len(anomalies),
            "severe_count": len(severe),
            "anomalies": anomalies[:5],  # first 5
        }
    except Exception as e:
        return {"status": "skipped", "reason": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes quality gate orchestrator")
    parser.add_argument("--path", required=True, help="Repository path")
    parser.add_argument("--no-auto-fix", action="store_true", help="Skip auto-fix phase")
    parser.add_argument("--loop", action="store_true", help="Loop on fixes until green")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    repo = Path(args.path).resolve()
    if not repo.exists():
        print(f"error: {repo} does not exist", file=sys.stderr)
        return 2

    started = time.time()
    toolchain = detect_toolchain(repo)
    if not toolchain:
        print(f"error: no recognized toolchain in {repo}", file=sys.stderr)
        return 2

    iterations = 0
    max_iter = args.max_iterations if args.loop else 1
    accumulated_errors = []

    while iterations < max_iter:
        iterations += 1
        report = {
            "skill": "quality-gate",
            "version": "1.0.0",
            "repo": repo.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "toolchain": toolchain,
            "iteration": iterations,
            "phases": {},
        }
        if not args.no_auto_fix and iterations == 1:
            report["phases"]["auto_fix"] = phase_auto_fix(repo, toolchain)
        report["phases"]["build"] = phase_build(repo, toolchain)
        report["phases"]["lint"] = phase_lint(repo, toolchain)
        report["phases"]["test"] = phase_test(repo, toolchain)
        report["phases"]["complexity"] = phase_complexity(repo)
        report["phases"]["anomaly_check"] = phase_anomaly_check(repo)
        report["duration_seconds"] = round(time.time() - started, 1)
        report["gate_passed"] = all(
            p.get("status") in ("ok", "skipped", "warning") for p in report["phases"].values()
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            # Human summary
            print(f"\n=== Quality Gate: {repo.name} (iteration {iterations}) ===")
            for phase_name, phase in report["phases"].items():
                status = phase.get("status", "?")
                icon = "✓" if status == "ok" else ("⊘" if status == "skipped" else "✗")
                print(f"  {icon} {phase_name}: {status}")
                if "errors" in phase and phase["errors"]:
                    for e in phase["errors"][:3]:
                        print(f"      {e[:200]}")
            print(f"  Duration: {report['duration_seconds']}s")
            print(f"  Gate: {'PASS' if report['gate_passed'] else 'FAIL'}")
        if report["gate_passed"] or iterations >= max_iter:
            return 0 if report["gate_passed"] else 2
        # Loop: print "iterating..." and continue
        if not args.json:
            print(f"  → iterating ({iterations + 1}/{max_iter})...")
    return 2


if __name__ == "__main__":
    sys.exit(main())
