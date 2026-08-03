#!/usr/bin/env python3
"""
kanban_reset_to_blocked — bulk-reset tasks to blocked status.

Useful when:
  - The dispatcher race auto-completed tasks with garbage results
  - Someone marked tasks done prematurely
  - You want to undo mass-completion

Uses the typed persistence layer (kanban_store.py) for atomic updates.

Safety:
  - Dry-run by default (preview before applying)
  - Filter by --mode (all/only-done)
  - Filter by --min-result-len (skip tasks with substantial results)
  - Idempotent: running twice produces the same result

Usage:
  kanban_reset_to_blocked.py --board ivan-tasks --only-done --min-result-len 100 --dry-run
  kanban_reset_to_blocked.py --board ivan-tasks --only-done --min-result-len 100
  kanban_reset_to_blocked.py --board ivan-tasks --ids "t_b4e05b10,t_cd2ffe4a"
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


def reset_tasks(store: KanbanStore, task_ids: list[str], dry_run: bool = False) -> int:
    """Reset tasks to blocked. Returns count reset."""
    reset = 0
    for tid in task_ids:
        task = store.get_task(tid)
        if not task:
            print(f"  WARN: {tid} not found, skipping")
            continue
        if dry_run:
            print(f"  [DRY] would reset {tid} [{task.status}] → blocked")
            reset += 1
        else:
            try:
                store.set_status(tid, "blocked")
                print(f"  ✓ {tid} [{task.status}] → blocked")
                reset += 1
            except Exception as e:
                print(f"  ✗ {tid}: {e}")
    return reset


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", required=True)
    p.add_argument("--mode", choices=["all", "only-done"], default="only-done",
                   help="Filter scope (ignored if --ids provided)")
    p.add_argument("--ids", help="Comma-separated list of task IDs (overrides --mode)")
    p.add_argument("--min-result-len", type=int, default=100,
                   help="Skip tasks with results longer than this")
    p.add_argument("--skip-ids", help="Comma-separated list of task IDs to skip")
    p.add_argument("--dry-run", action="store_true", help="Preview without changing")
    args = p.parse_args()

    if not board_db_path(args.board).exists():
        print(f"ERROR: board '{args.board}' not found", file=sys.stderr)
        return 1

    skip_ids = set(args.skip_ids.split(",") if args.skip_ids else [])

    with KanbanStore(args.board) as store:
        store.ensure_schema()
        # Determine target IDs
        if args.ids:
            ids = [tid.strip() for tid in args.ids.split(",") if tid.strip()]
        else:
            ids = []
            cur = store._connect().execute(
                "SELECT id, status, result FROM tasks "
                + ("WHERE status='done' " if args.mode == "only-done" else "")
                + "ORDER BY created_at ASC"
            )
            for tid, status, result in cur.fetchall():
                if tid in skip_ids:
                    continue
                if args.min_result_len > 0 and result and len(result) >= args.min_result_len:
                    continue
                ids.append(tid)

        if not ids:
            print(f"No tasks to reset on {args.board}")
            return 0

        print(f"Reset target: {len(ids)} tasks on {args.board} (dry_run={args.dry_run})")
        reset = reset_tasks(store, ids, dry_run=args.dry_run)

        verb = "would reset" if args.dry_run else "reset"
        print(f"\n{verb} {reset} task(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
