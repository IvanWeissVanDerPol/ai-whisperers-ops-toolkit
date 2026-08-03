#!/usr/bin/env python3
"""
kanban_orchestrator.py — Resolve Kanban tasks via orchestrators.

Tags Kanban tasks with `orchestrator:` (in their description) and this
script:
  1. Lists all `ready` tasks across boards
  2. Filters for tasks tagged `orchestrator:<name>`
  3. Maps orchestrator names to scripts:
     - orchestrator:quality-gate    → quality-gate
     - orchestrator:coverage-runner → coverage-runner
     - orchestrator:delivery-prep   → delivery-prep
     - orchestrator:repo-tick       → repo-tick
     - orchestrator:auto-remediate  → auto-remediate
  4. Invokes the appropriate orchestrator with the task's target repo
  5. Marks task as `done` on success, `blocked` on failure
  6. Comments the result back to the task

Usage:
    python3 ~/.hermes/scripts/kanban_orchestrator.py --board dentist-tasks
    python3 ~/.hermes/scripts/kanban_orchestrator.py --board dentist-tasks --dry-run
    python3 ~/.hermes/scripts/kanban_orchestrator.py --all
    python3 ~/.hermes/scripts/kanban_orchestrator.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


HERMES_HOME = Path.home() / ".hermes"
SKILLS = HERMES_HOME / "skills"
SCRIPTS = HERMES_HOME / "scripts"
STATE = HERMES_HOME / "state"
PROJECTS_YAML = STATE / "projects.yaml"


# Map orchestrator tag → script path
ORCHESTRATOR_MAP = {
    "quality-gate": SKILLS / "quality-gate" / "scripts" / "quality_gate.py",
    "coverage-runner": SKILLS / "coverage-runner" / "scripts" / "coverage_runner.py",
    "delivery-prep": SKILLS / "delivery-prep" / "scripts" / "delivery_prep.py",
    "repo-tick": SCRIPTS / "repo_tick.py",
    "auto-remediate": SCRIPTS / "auto_remediate.py",
    "pipeline-run": SCRIPTS / "pipeline_run.py",
}


def load_projects() -> list[dict]:
    if not PROJECTS_YAML.exists():
        return []
    import yaml
    data = yaml.safe_load(PROJECTS_YAML.read_text())
    return data.get("projects", [])


def list_kanban_tasks(board: str | None) -> list[dict]:
    """List ready tasks. If board is None, list all boards."""
    cmd = ["hermes", "kanban", "list", "--json"]
    if board:
        cmd = ["hermes", "kanban", "--board", board, "list", "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if isinstance(data, dict) and "tasks" in data:
                    return data["tasks"]
                if isinstance(data, list):
                    return data
                return []
            except json.JSONDecodeError:
                return []
        return []
    except Exception as e:
        print(f"warning: kanban list failed: {e}", file=sys.stderr)
        return []


def parse_orchestrator_tag(description: str) -> str | None:
    """Extract orchestrator tag from task description."""
    if not description:
        return None
    m = re.search(r"orchestrator:([\w-]+)", description)
    return m.group(1) if m else None


def find_target_repo(description: str, projects: list[dict]) -> str | None:
    """Find repo path from task description."""
    if not description:
        return None
    # Look for project name in description
    for project in projects:
        if project["name"] in description:
            return project["path"]
    return None


def run_orchestrator(name: str, script: Path, repo_path: str) -> dict:
    """Run an orchestrator on a repo."""
    if not script.exists():
        return {"status": "skipped", "reason": f"orchestrator script missing: {script}"}
    try:
        result = subprocess.run(
            ["python3", str(script), "--path", repo_path],
            capture_output=True, text=True, timeout=300,
        )
        return {
            "status": "ok" if result.returncode in (0, 2) else "failed",
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-1500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def update_task(task_id: str, state: str, comment: str) -> bool:
    """Update Kanban task state. State: done, blocked."""
    cmd_args = ["--comment", comment]
    if state == "done":
        cmd = ["hermes", "kanban", "complete"] + cmd_args + [task_id]
    elif state == "blocked":
        cmd = ["hermes", "kanban", "block"] + cmd_args + [task_id]
    else:
        return False
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Kanban tasks via orchestrators")
    parser.add_argument("--board", help="Single board (default: all)")
    parser.add_argument("--all", action="store_true", help="All boards")
    parser.add_argument("--dry-run", action="store_true", help="Don't update tasks")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not args.board and not args.all:
        parser.error("provide --board or --all")

    projects = load_projects()
    tasks = list_kanban_tasks(args.board if args.board else None)

    results = []
    for task in tasks:
        task_id = task.get("id", task.get("task_id", "?"))
        description = task.get("description", "") + " " + task.get("title", "")
        orch = parse_orchestrator_tag(description)
        if not orch:
            continue
        if orch not in ORCHESTRATOR_MAP:
            results.append({"task": task_id, "status": "skipped", "reason": f"unknown orchestrator: {orch}"})
            continue
        repo_path = find_target_repo(description, projects) or "/root/psycology"
        script = ORCHESTRATOR_MAP[orch]
        # Run
        run_result = run_orchestrator(orch, script, repo_path)
        # Update Kanban
        if not args.dry_run:
            new_state = "done" if run_result["status"] == "ok" else "blocked"
            comment = f"orchestrator:{orch} → {run_result['status']} (exit={run_result.get('exit_code', '?')})"
            updated = update_task(task_id, new_state, comment)
            run_result["kanban_updated"] = updated
            run_result["new_state"] = new_state
        results.append({"task": task_id, "orchestrator": orch, "repo": repo_path, "result": run_result})

    if args.json:
        print(json.dumps({"skill": "kanban-orchestrator", "version": "1.0.0", "results": results}, indent=2))
    else:
        print(f"\n=== Kanban Orchestrator ===")
        print(f"  Tasks scanned: {len(tasks)}")
        print(f"  Orchestrator-tagged: {len(results)}")
        for r in results:
            task_id = r.get("task", "?")
            orch = r.get("orchestrator", "?")
            status = r.get("result", {}).get("status", "?")
            print(f"  {task_id:<15} orch={orch:<18} {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())