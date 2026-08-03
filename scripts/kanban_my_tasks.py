#!/usr/bin/env python3
"""
kanban_my_tasks — show every task assigned to one person across all boards.

Uses the typed persistence layer (kanban_store.py) for all DB operations.
Combines the multi-person sidecar table (task_assignees) with each board's
SQLite to give a single view of "what does Ivan need to do today?"

Usage:
  kanban_my_tasks.py ivan
  kanban_my_tasks.py ivan --include-done
  kanban_my_tasks.py ivan --tenant Ai-Whisperers
  kanban_my_tasks.py ivan --include-agents   # also show tasks assigned to agents
  kanban_my_tasks.py kiki --board kiki-tasks
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import (
    KANBAN_ROOT, KANBAN_HOME, INBOX_DIR,
    board_db_path, list_boards,
    ensure_due_dates_table, ensure_task_assignees_table,
    quiet_hours, log_quiet_hours, send_to_platforms,
    PEOPLE, HUMAN_PEOPLE, AGENT_PEOPLE, DEFAULT_TENANT,
    is_human, is_known_person,
    now_ts, today_iso, eprint, exit_error,
)
from kanban_store import KanbanStore  # noqa


def list_tasks_for_person(
    person: str,
    board: str | None = None,
    tenant: str | None = None,
    include_done: bool = False,
    include_agents: bool = False,
) -> list[tuple[str, str, str, str, str, str, str, str, float]]:
    """Return list of (board, task_id, title, status, priority, due_at, assignee, tenant, weight)."""
    results = []
    boards = [board] if board else list_boards()
    for b in boards:
        with KanbanStore(b) as store:
            store.ensure_schema()
            # Combine sidecar + tenant + due_at
            rows = store.list_tasks_for_person(person, include_done=include_done)
            for task, assignee in rows:
                # Filter by tenant if requested
                if tenant and task.tenant != tenant:
                    continue
                # Filter by agent inclusion
                if not include_agents and not is_human(person):
                    continue
                # Get due_at (we don't have it in the task — would need to join)
                due = store.get_due_date(task.id)
                due_at = due.due_at if due else ""
                results.append((
                    b, task.id, task.title, task.status, task.priority,
                    due_at, task.assignee or "", task.tenant or "", assignee.weight,
                ))
    return results


def format_table(results: list) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "(no tasks)"
    # Sort: priority asc, then created_at if available
    results.sort(key=lambda r: (r[4], r[3], r[1]))
    lines = []
    lines.append(f"{'BOARD':<16} {'ID':<14} {'PRI':<4} {'STATUS':<10} {'DUE':<12} {'TENANT':<14} {'TITLE'}")
    lines.append("-" * 130)
    for board, tid, title, status, priority, due_at, assignee, tenant, weight in results:
        marker = "★" if weight >= 1.0 else "·"
        # Priority display
        pri_label = "0" if priority == 0 else f"{priority}"
        title_short = (title or "(no title)")[:60]
        lines.append(
            f"{board:<16} {tid:<14} {pri_label:<4} {status:<10} {due_at:<12} {tenant:<14} {title_short} {marker}"
        )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("person", help="person slug (e.g., ivan, kiki, lua)")
    p.add_argument("--board", help="filter to one board")
    p.add_argument("--tenant", help="filter by tenant")
    p.add_argument("--include-done", action="store_true", help="include done/archived tasks")
    p.add_argument("--include-agents", action="store_true", help="also show agent-assigned tasks")
    args = p.parse_args()

    if not is_known_person(args.person):
        print(f"WARN: '{args.person}' not in PEOPLE registry. Showing anyway.")
    results = list_tasks_for_person(
        args.person,
        board=args.board,
        tenant=args.tenant,
        include_done=args.include_done,
        include_agents=args.include_agents,
    )
    print(format_table(results))
    print(f"\n  {len(results)} task(s) for {args.person}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
