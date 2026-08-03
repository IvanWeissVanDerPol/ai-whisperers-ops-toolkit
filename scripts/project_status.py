"""
project_status.py — show ALL projects: active, standby, cold.

Aggregates 4 sources:
  1. repo_context.json (repos + active_projects)
  2. contacts.py (clients + leads)
  3. kanban boards (active tasks per tenant)
  4. /root + /root/.hermes (research directories)

Usage:
  python3 project_status.py               # show all
  python3 project_status.py --active      # only active
  python3 project_status.py --standby     # only standby/paused
  python3 project_status.py --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import INBOX_DIR, board_db_path, list_boards
import contacts


KANBAN_DB = Path("/root/.hermes/kanban.db")
CONTEXT_PATH = Path("/root/.hermes/inbox/repo_context.json")


def count_active_tasks_by_tenant() -> dict[str, int]:
    """Count active (non-done, non-archived) tasks per tenant across all boards."""
    counts: dict[str, int] = {}
    boards = ["/root/.hermes/kanban.db"]
    for p in Path("/root/.hermes/kanban/boards").glob("*/kanban.db"):
        boards.append(str(p))

    for db in boards:
        try:
            con = sqlite3.connect(db)
            cur = con.execute("""
                SELECT tenant, COUNT(*) FROM tasks
                WHERE status NOT IN ('done', 'archived')
                GROUP BY tenant
            """)
            for tenant, n in cur.fetchall():
                counts[tenant or "(no tenant)"] = counts.get(tenant or "(no tenant)", 0) + n
            con.close()
        except Exception:
            pass
    return counts


def get_kanban_boards_for_tenant(tenant: str) -> list[str]:
    """Find which kanban boards have tasks for a given tenant."""
    boards_found = set()
    for db in ["/root/.hermes/kanban.db"] + [str(p) for p in Path("/root/.hermes/kanban/boards").glob("*/kanban.db")]:
        try:
            con = sqlite3.connect(db)
            cur = con.execute("SELECT 1 FROM tasks WHERE tenant = ? AND status NOT IN ('done','archived') LIMIT 1", (tenant,))
            if cur.fetchone():
                board = Path(db).parent.name if "boards" in db else "default"
                boards_found.add(board)
            con.close()
        except Exception:
            pass
    return sorted(boards_found)


def get_projects() -> list[dict]:
    """Aggregate all projects from contacts + repo_context + kanban."""
    projects = []
    task_counts = count_active_tasks_by_tenant()
    ctx = json.loads(CONTEXT_PATH.read_text()) if CONTEXT_PATH.exists() else {}

    # 1. Active projects from repo_context
    for p in ctx.get("active_projects", []):
        projects.append({
            "id": p["id"],
            "name": p["name"],
            "type": "project",
            "stage": p.get("stage", "active"),
            "active_tasks": p.get("active_tasks", 0),
            "kanban_boards": [p["kanban_board"]] if p.get("kanban_board") else [],
            "owner": p.get("owner", "?"),
            "notes": p.get("note", ""),
        })

    # 2. Dentist (the only repo client)
    priority = ctx.get("client_priority", {})
    if priority.get("primary_repo"):
        projects.append({
            "id": "dentist",
            "name": "Dentist (the only repo client)",
            "type": "client",
            "stage": "active",
            "active_tasks": task_counts.get("Ai-Whisperers", 0),  # dentist tasks use Ai-Whisperers tenant
            "repo": priority["primary_repo"],
            "kanban_boards": list(priority.get("kanban_boards", {}).values()) if isinstance(priority.get("kanban_boards"), dict) else [],
            "owner": "Ivan",
            "notes": "Live client. The only repo client per SINGLE-CLIENT-RULE.",
        })

    # 3. Internal work
    for tenant, count in task_counts.items():
        if tenant in ("Ai-Whisperers", "(no tenant)"):
            if count > 0:
                projects.append({
                    "id": "internal-ops",
                    "name": "Internal Ai-Whisperers ops",
                    "type": "internal",
                    "stage": "active",
                    "active_tasks": count,
                    "kanban_boards": get_kanban_boards_for_tenant(tenant),
                    "owner": "Ivan + Kiki + Lua",
                    "notes": "Internal company projects, not for clients.",
                })
                break

    # 4. Contacts (cold)
    contacts_data = contacts.load()
    for c in contacts_data.get("contacts", []):
        if c.get("tasks"):
            continue  # has tasks, accounted for elsewhere
        projects.append({
            "id": c["id"],
            "name": c["name"],
            "type": "contact",
            "stage": c.get("stage", "?"),
            "phone": c.get("phone_e164", ""),
            "line_of_work": c.get("line_of_work", ""),
            "tenant": c.get("tenant", ""),
            "active_tasks": 0,
            "kanban_boards": [],
            "owner": "(unassigned)",
            "notes": c.get("notes", ""),
        })

    # 5. Paused repos
    for p in priority.get("paused_clients", []):
        projects.append({
            "id": p["repo"],
            "name": Path(p["repo"]).name,
            "type": "repo",
            "stage": "paused",
            "active_tasks": 0,
            "owner": "(paused)",
            "notes": p.get("reason", ""),
        })

    return projects


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--active", action="store_true", help="only active projects")
    p.add_argument("--standby", action="store_true", help="only standby/paused")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    projects = get_projects()

    # Filter
    if args.active:
        projects = [p for p in projects if p.get("stage") in ("active", "qualifying", "pre-sales", "internal")]
    elif args.standby:
        projects = [p for p in projects if p.get("stage") in ("paused", "cold", "lost")]

    if args.json:
        print(json.dumps({"projects": projects}, indent=2))
        return

    # Group by stage
    by_stage = {}
    for p in projects:
        by_stage.setdefault(p.get("stage", "?"), []).append(p)

    print(f"\n{'='*70}")
    print(f"Project Status — {len(projects)} projects")
    print(f"{'='*70}\n")

    stage_order = ["active", "pre-sales", "qualifying", "internal", "client", "lead", "cold", "paused", "lost", "?"]
    for stage in stage_order:
        if stage not in by_stage:
            continue
        items = by_stage[stage]
        print(f"  {stage.upper()} ({len(items)}):")
        for p in items:
            pid = p["id"][:35]
            name = p["name"][:35]
            tasks = p.get("active_tasks", 0)
            owner = p.get("owner", "?").replace("+", "")[:18]
            boards = ", ".join(p.get("kanban_boards", [])[:2])[:18]
            print(f"    [{tasks:>3}] {pid:<35} {name:<35} ({owner}) [{boards}]")
        print()


if __name__ == "__main__":
    main()
