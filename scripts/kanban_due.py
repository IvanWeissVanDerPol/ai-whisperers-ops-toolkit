#!/usr/bin/env python3
"""
kanban_due — manage structured due dates for Hermes Kanban tasks.

Uses the typed persistence layer (kanban_store.py) for all DB operations.

Usage:
  kanban_due.py --board ivan-tasks set <task_id> 2026-07-28 [--source audio-2026-07-27]
  kanban_due.py --board ivan-tasks list [--days 7]
  kanban_due.py --board ivan-tasks get <task_id>
  kanban_due.py --board ivan-tasks overdue
  kanban_due.py --board ivan-tasks migrate   # one-time: extract from existing comment-style schedules
"""
import argparse
import sys
from datetime import datetime, timedelta
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
from kanban_models import DueDateModel  # noqa


# ---- Commands ----

def cmd_set(args):
    """Set or update a task's due date."""
    db = board_db_path(args.board)
    if not db.exists():
        print(f"ERROR: board '{args.board}' not found at {db}", file=sys.stderr)
        return 1
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        # Validate task exists
        task = store.get_task(args.task_id)
        if not task:
            print(f"ERROR: task {args.task_id} not found on board '{args.board}'", file=sys.stderr)
            return 1
        # Validate due date format
        try:
            datetime.fromisoformat(args.due)
        except ValueError:
            print(f"ERROR: due date must be YYYY-MM-DD, got {args.due!r}", file=sys.stderr)
            return 1
        # Use pydantic models for validation
        try:
            model = DueDateModel(task_id=args.task_id, due_at=args.due, source=args.source)
            store.set_due_date(model.task_id, model.due_at, source=model.source)
            print(f"✓ {args.task_id} due {args.due} (source={args.source})")
            return 0
        except Exception as e:
            print(f"ERROR: validation failed: {e}", file=sys.stderr)
            return 1


def cmd_list(args):
    """List due dates, optionally within a window."""
    db = board_db_path(args.board)
    if not db.exists():
        print(f"ERROR: board '{args.board}' not found", file=sys.stderr)
        return 1
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        days = args.days or 7
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        future = (datetime.now() + timedelta(days=days)).date().isoformat()
        # Use the store's typed query
        con = store._connect()
        cur = con.execute("""
            SELECT d.task_id, t.title, d.due_at, t.assignee, t.status, d.source
            FROM due_dates d
            JOIN tasks t ON t.id = d.task_id
            WHERE d.due_at >= ? AND d.due_at <= ?
            ORDER BY d.due_at ASC
        """, (cutoff, future))
        rows = cur.fetchall()
        if not rows:
            print(f"No due dates in window [{cutoff}, {future}]")
            return 0
        print(f"Due dates for {args.board} (window {days} days):")
        print(f"{'TASK ID':<14} {'DUE':<12} {'STATUS':<10} {'ASSIGNEE':<10} {'SOURCE':<25} {'TITLE'}")
        print("-" * 110)
        for r in rows:
            tid, title, due_at, assignee, status, source = r
            title_short = (title or "(no title)")[:45]
            print(f"{tid:<14} {due_at:<12} {status:<10} {assignee or '-':<10} {source or '-':<25} {title_short}")
    return 0


def cmd_get(args):
    """Get a single task's due date."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        due = store.get_due_date(args.task_id)
        if not due:
            print(f"No due date for {args.task_id}")
            return 1
        print(f"Task {args.task_id} due {due.due_at} (source={due.source})")
        return 0


def cmd_overdue(args):
    """List all overdue tasks."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        today = today_iso()
        overdue = store.list_overdue(today)
        if not overdue:
            print(f"No overdue tasks on {args.board} (as of {today})")
            return 0
        print(f"Overdue tasks on {args.board} (as of {today}):")
        for task, due in overdue:
            days_late = (datetime.now().date() - datetime.fromisoformat(due.due_at).date()).days
            print(f"  {task.id} {due.due_at} (-{days_late}d) [{task.assignee or '-'}] {task.title[:50]}")
    return 0


def cmd_migrate(args):
    """One-time: extract dates from task body/comments into due_dates."""
    import re
    from datetime import date
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
        cur = store._connect().execute("SELECT id, title, body FROM tasks")
        candidates = cur.fetchall()
        added = 0
        for tid, title, body in candidates:
            for text in (title or "", body or ""):
                m = DATE_RE.search(text)
                if m:
                    due_date = m.group(1)
                    # Don't migrate past dates
                    try:
                        if datetime.fromisoformat(due_date).date() < date.today():
                            continue
                    except ValueError:
                        continue
                    # Only add if not already there
                    if not store.get_due_date(tid):
                        store.set_due_date(tid, due_date, source="migrate")
                        added += 1
                        break
        print(f"Migration: {added} new due dates added on {args.board}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set")
    p_set.add_argument("task_id")
    p_set.add_argument("due")
    p_set.add_argument("--source", default="manual")
    p_set.set_defaults(func=cmd_set)

    p_list = sub.add_parser("list")
    p_list.add_argument("--days", type=int, help="window in days (default 7)")
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get")
    p_get.add_argument("task_id")
    p_get.set_defaults(func=cmd_get)

    p_overdue = sub.add_parser("overdue")
    p_overdue.set_defaults(func=cmd_overdue)

    p_migrate = sub.add_parser("migrate")
    p_migrate.set_defaults(func=cmd_migrate)

    args = p.parse_args()
    rc = args.func(args)
    sys.exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
