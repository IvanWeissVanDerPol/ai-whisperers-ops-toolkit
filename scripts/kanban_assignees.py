#!/usr/bin/env python3
"""
kanban_assignees — multi-person co-assignee support for kanban tasks.

Uses the typed persistence layer (kanban_store.py) for all DB operations.
The PEOPLE registry (kanban_common.py) is the source of truth for human/agent metadata.

Usage:
  kanban_assignees.py --board ivan-tasks add <task_id> <person> [--role "..."] [--weight 0.5]
  kanban_assignees.py --board ivan-tasks remove <task_id> <person>
  kanban_assignees.py --board ivan-tasks list <task_id>
  kanban_assignees.py --board ivan-tasks tasks-for <person> [--include-done]
  kanban_assignees.py --board ivan-tasks migrate   # one-time: from legacy assignee column
  kanban_assignees.py --board ivan-tasks people
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
from kanban_models import AssigneeModel  # noqa


# ---- Commands ----

def cmd_add(args):
    """Add a co-assignee to a task."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        # Validate task exists
        task = store.get_task(args.task_id)
        if not task:
            print(f"ERROR: task {args.task_id} not found on board '{args.board}'", file=sys.stderr)
            return 1
        # Validate person exists
        if not is_known_person(args.person):
            print(f"WARN: '{args.person}' is not in PEOPLE registry. Adding anyway.")
        # Validate via pydantic
        try:
            model = AssigneeModel(
                task_id=args.task_id,
                person=args.person,
                role=args.role,
                weight=args.weight,
            )
        except Exception as e:
            print(f"ERROR: validation failed: {e}", file=sys.stderr)
            return 1
        added = store.add_assignee(model.task_id, model.person, role=model.role, weight=model.weight)
        if added:
            role_info = model.role or "no role"
            print(f"✓ Added {model.person} ({role_info}, weight={model.weight}) to {model.task_id}")
        else:
            print(f"  {model.person} already assigned to {model.task_id}")
    return 0


def cmd_remove(args):
    """Remove a co-assignee from a task."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        removed = store.remove_assignee(args.task_id, args.person)
        if removed:
            print(f"✓ Removed {args.person} from {args.task_id}")
        else:
            print(f"  {args.person} was not assigned to {args.task_id}")
    return 0


def cmd_list(args):
    """List all co-assignees for a task."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        assignees = store.list_assignees(args.task_id)
        if not assignees:
            print(f"No assignees for {args.task_id}")
            return 0
        task = store.get_task(args.task_id)
        title = task.title if task else "(unknown)"
        print(f"Assignees for {args.task_id} ({title[:50]}):")
        for a in assignees:
            marker = " ★" if a.weight >= 1.0 else ""
            role = a.role or "no role"
            profile = PEOPLE.get(a.person, {}).get("profile", "?")
            print(f"  {a.person:<14} {role:<22} weight={a.weight}{marker}  [profile={profile}]")
    return 0


def cmd_tasks_for(args):
    """Show all tasks assigned to a person across this board."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        rows = store.list_tasks_for_person(args.person, include_done=args.include_done)
        if not rows:
            print(f"No tasks assigned to {args.person} on {args.board}")
            return 0
        for task, assignee in rows:
            marker = " ★" if assignee.weight >= 1.0 else ""
            print(f"  {task.id} [{task.status[:9]:<9}] {task.title[:60]}{marker}" +
                  (f"  weight={assignee.weight}" if assignee.weight < 1.0 else ""))
    return 0


def cmd_migrate(args):
    """One-time: migrate legacy tasks.assignee column to sidecar table."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        cur = store._connect().execute("SELECT id, assignee FROM tasks WHERE assignee IS NOT NULL")
        candidates = cur.fetchall()
        added = 0
        for tid, assignee in candidates:
            if not assignee:
                continue
            # Default weight 1.0 for primary, 0.5 for secondaries
            existing = store.list_assignees(tid)
            if not existing:
                store.add_assignee(tid, assignee, role="primary", weight=1.0)
                added += 1
        print(f"Migration: {added} tasks on {args.board} got primary assignee from 'assignee' column")
    return 0


def cmd_set_phone(args):
    """Set a person's phone via KANBAN_PHONE_<PERSON> env var instructions.

    This doesn't write to disk (env vars are process-local). It shows
    you the command to run to set the phone for future sessions.
    """
    person = args.person.lower()
    if person not in HUMAN_PEOPLE:
        print(f"ERROR: '{person}' is not a known human", file=sys.stderr)
        return 1
    env_key = f"KANBAN_PHONE_{person.upper()}"
    if args.clear:
        print(f"To clear {person}'s phone, unset the env var:")
        print(f"  unset {env_key}")
        return 0
    if not args.phone.startswith("+"):
        print(f"WARN: phone should be E.164 with leading '+', got {args.phone!r}")
    print(f"To set {person}'s phone for this session and future ones, add to your shell rc:")
    print(f"  export {env_key}={args.phone}")
    print(f"Or for one-off:  {env_key}={args.phone} hermes kanban ...")
    print(f"\nUpdated phones will be picked up when a script reloads.")
    return 0


def cmd_people(args):
    """Show the people registry (humans + agents)."""
    print("Humans (with WhatsApp when configured):")
    for p, info in HUMAN_PEOPLE.items():
        phone = ", ".join(info.get("phone", [])) or "—"
        print(f"  {p:<14} {info['role']:<22} profile={info['profile']:<10} phone={phone}")
    print("\nAgents (no WhatsApp, receive work via dispatcher):")
    for p, info in AGENT_PEOPLE.items():
        print(f"  {p:<14} {info['role']:<22} profile={info['profile']}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("task_id")
    p_add.add_argument("person")
    p_add.add_argument("--role", default="co-owner")
    p_add.add_argument("--weight", type=float, default=1.0)
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("task_id")
    p_rm.add_argument("person")
    p_rm.set_defaults(func=cmd_remove)

    p_ls = sub.add_parser("list")
    p_ls.add_argument("task_id")
    p_ls.set_defaults(func=cmd_list)

    p_tf = sub.add_parser("tasks-for")
    p_tf.add_argument("person")
    p_tf.add_argument("--include-done", action="store_true")
    p_tf.set_defaults(func=cmd_tasks_for)

    p_mig = sub.add_parser("migrate")
    p_mig.set_defaults(func=cmd_migrate)

    p_people = sub.add_parser("people")
    p_people.set_defaults(func=cmd_people)

    p_phone = sub.add_parser("set-phone")
    p_phone.add_argument("person")
    p_phone.add_argument("phone", help="E.164 format with + (e.g., +595985724135)")
    p_phone.add_argument("--clear", action="store_true", help="Clear the phone")
    p_phone.set_defaults(func=cmd_set_phone)

    args = p.parse_args()
    rc = args.func(args)
    sys.exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
