#!/usr/bin/env python3
"""Pre-shift baseline metrics for Solstein cron jobs.
Runs before each agent shift; stdout is injected into the prompt."""
import subprocess
import os
import re

REPO = "/tmp/solstein"

def run(cmd, timeout=120):
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=REPO,
            env={**os.environ, "PYTHONPATH": os.path.join(REPO, "src")}
        )
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"ERROR: {e}"

# Ensure repo exists and is up to date
if not os.path.isdir(REPO):
    subprocess.run(
        f"git clone https://github.com/Ai-Whisperers/solstein.git {REPO}",
        shell=True, capture_output=True, timeout=120
    )

run("git checkout develop 2>&1")
run("git pull origin develop 2>&1")

# Test baseline — use a targeted run for speed (just count, don't show output)
test_out = run("python3 -m pytest tests/unit/ -q --tb=no 2>&1 | tail -5", timeout=660)

# Parse test results: "316 failed, 3860 passed, 6 skipped, 169 warnings, 231 errors in 526.24s"
passed = 0
failed = 0
errors = 0

m = re.search(r'(\d+)\s+passed', test_out)
if m: passed = int(m.group(1))
m = re.search(r'(\d+)\s+failed', test_out)
if m: failed = int(m.group(1))
m = re.search(r'(\d+)\s+error', test_out)
if m: errors = int(m.group(1))

# Lint baseline
lint_out = run("python3 -m ruff check src/ 2>&1")
lint_clean = "All checks passed" in lint_out
lint_errors = 0
if not lint_clean:
    lint_errors = len([l for l in lint_out.strip().split('\n') if l.strip() and ':' in l and not l.startswith('warning')])

# Queue status
queue_out = run("grep -c 'READY' planning/QUEUE.md 2>/dev/null || echo 0")
ready_count = 0
m = re.search(r'(\d+)', queue_out)
if m: ready_count = int(m.group(1))

# First 5 ready stories
first_ready = run("grep 'READY' planning/QUEUE.md | grep 'STORY-' | head -5")

# Source file count
src_count = run("find src -name '*.py' | wc -l").strip()

print(f"""SOLSTEIN SHIFT BASELINE (auto-generated — do NOT create a work log file)
========================================================================
Tests:     {passed} passing, {failed} failing, {errors} errors
Lint:      {"CLEAN" if lint_clean else f"{lint_errors} errors"}
Sources:   {src_count} Python files
Queue:     {ready_count} READY stories

YOUR TARGETS:
- Make tests_passing > {passed} (beat the baseline)
- Make tests_failing < {failed} (reduce failures)
- Keep lint CLEAN
- Do NOT create any .md, .txt, .rst, or documentation files
- Do NOT modify files under docs/, planning/, or backlog/
- ONLY edit .py files under src/ and tests/

FIRST READY STORIES (for feature shifts):
{first_ready.strip()}

REGRESSION GATE:
After your changes, run: PYTHONPATH=src python3 -m pytest tests/unit/ -q --tb=no 2>&1 | tail -1
If tests_passing < {passed}: REVERT with git checkout . — do NOT commit
If tests_failing > {failed}: REVERT with git checkout . — do NOT commit
""")
