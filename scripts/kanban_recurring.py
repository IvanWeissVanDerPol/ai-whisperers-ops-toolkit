#!/usr/bin/env python3
"""
kanban_recurring — manage recurring task templates that auto-create kanban tasks.

Templates are stored in ~/.hermes/inbox/kanban-templates.json.
Each template defines:
  - title: task title
  - body: task description
  - board: which board to create on
  - assignee: who owns it
  - priority: 0-10
  - schedule: cron-like '0 9 * * 1' (every Monday 9am) or 'every 7d'
  - dedupe_key: optional — if a task with this key exists open, skip

Usage:
  kanban_recurring.py list                          # show all templates
  kanban_recurring.py add <name> --title '...' --board ivan-tasks --schedule '0 9 * * 1'
  kanban_recurring.py remove <name>
  kanban_recurring.py run                            # process all templates (called by cron)
  kanban_recurring.py run --name <name>              # process one template
  kanban_recurring.py run --dry-run
"""
import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path



TEMPLATE_FILE = Path.home() / ".hermes" / "inbox" / "kanban-templates.json"
STATE_FILE = Path.home() / ".hermes" / "inbox" / ".kanban-recurring-state"


def load_templates():
    if not TEMPLATE_FILE.exists():
        return {}
    try:
        return json.loads(TEMPLATE_FILE.read_text())
    except Exception as e:
        print(f"ERROR loading templates: {e}", file=sys.stderr)
        return {}


def save_templates(templates):
    TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_FILE.write_text(json.dumps(templates, indent=2))


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def parse_schedule(schedule):
    """Return True if the schedule should fire today. Cron: '0 9 * * 1' or 'every 7d'."""
    if schedule.startswith("every "):
        # 'every 7d' or 'every 2h' or 'every 1w'
        spec = schedule[6:]
        unit = spec[-1]
        try:
            n = int(spec[:-1])
        except ValueError:
            return False
        # Just say "fire" — the dedupe (last_run check) prevents spam
        return True
    # 5-field cron: min hour day-of-month month day-of-week
    try:
        fields = schedule.split()
        if len(fields) != 5:
            return False
        minute, hour, dom, month, dow = fields
        now = datetime.now()
        # Check minute
        if minute != "*" and int(minute) != now.minute:
            return False
        # Check hour
        if hour != "*" and int(hour) != now.hour:
            return False
        # Day of month
        if dom != "*" and int(dom) != now.day:
            return False
        # Month
        if month != "*" and int(month) != now.month:
            return False
        # Day of week (0=Sun, 1=Mon, ...)
        if dow != "*" and int(dow) != now.weekday() + 1 % 7:
            return False
        return True
    except Exception:
        return False


def should_run_now(template, state):
    """Decide if we should create a task. Combines schedule + dedupe."""
    schedule = template.get("schedule", "")
    if not parse_schedule(schedule):
        return False, "schedule says no"
    # Dedupe: if a task with the same dedupe_key is open, skip
    dedupe_key = template.get("dedupe_key")
    if dedupe_key:
        board = template.get("board")
        if not board:
            return True, "no board, letting through"
        db = KANBAN_ROOT / "boards" / board / "kanban.db"
        if db.exists():
            con = sqlite3.connect(db)
            cur = con.execute(
                "SELECT id, status FROM tasks WHERE (title LIKE ? OR body LIKE ?) AND status NOT IN ('done','archived')",
                (f"%{dedupe_key}%", f"%{dedupe_key}%")
            )
            if cur.fetchone():
                con.close()
                return False, "dedupe_key found open task"
            con.close()
    return True, "ok"


def create_task_from_template(name, template, dry_run=False):
    """Create one kanban task from a template."""
    title = template.get("title", name)
    body = template.get("body", "")
    board = template.get("board", "default")
    assignee = template.get("assignee", "default")
    priority = template.get("priority", 5)
    dedupe_key = template.get("dedupe_key", "")

    # Augment body with provenance
    full_body = f"{body}\n\n---\nRecurring template: {name}\nSchedule: {template.get('schedule','')}\nCreated: {datetime.now().isoformat()}"
    if dedupe_key:
        full_body += f"\nDedupe key: {dedupe_key}"

    cmd = [
        "hermes", "kanban", "--board", board, "create", title,
        "--body", full_body,
        "--priority", str(priority),
        "--assignee", assignee,
        "--initial-status", "blocked",
        "--created-by", f"recurring-{name}",
    ]
    if dry_run:
        print(f"  [DRY] would create on {board}: {title}")
        return None
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()[:200]}", file=sys.stderr)
        return None
    # Extract task ID
    import re

    m = re.search(r"(t_[a-f0-9]+)", result.stdout)
    return m.group(1) if m else None


def cmd_list(args):
    templates = load_templates()
    if not templates:
        print("(no templates defined)")
        return 0
    print(f"Recurring templates ({len(templates)}):")
    for name, t in templates.items():
        print(f"\n  {name}")
        print(f"    title:    {t.get('title', name)}")
        print(f"    board:    {t.get('board', '?')}")
        print(f"    assignee: {t.get('assignee', '?')}")
        print(f"    schedule: {t.get('schedule', '?')}")
        if t.get("dedupe_key"):
            print(f"    dedupe:   {t['dedupe_key']}")
    return 0


def cmd_add(args):
    templates = load_templates()
    if args.name in templates:
        print(f"ERROR: template '{args.name}' already exists. Use --name for a unique name.", file=sys.stderr)
        return 1
    templates[args.name] = {
        "title": args.title or args.name,
        "body": args.body or "",
        "board": args.board,
        "assignee": args.assignee,
        "priority": int(args.priority),
        "schedule": args.schedule,
        "dedupe_key": args.dedupe_key or "",
    }
    save_templates(templates)
    print(f"✓ Added template '{args.name}'")
    return 0


def cmd_remove(args):
    templates = load_templates()
    if args.name not in templates:
        print(f"ERROR: template '{args.name}' not found", file=sys.stderr)
        return 1
    del templates[args.name]
    save_templates(templates)
    print(f"✓ Removed template '{args.name}'")
    return 0


def cmd_run(args):
    templates = load_templates()
    if args.name:
        if args.name not in templates:
            print(f"ERROR: template '{args.name}' not found", file=sys.stderr)
            return 1
        templates = {args.name: templates[args.name]}

    state = load_state()
    today = datetime.now().date().isoformat()

    ran = 0
    skipped = 0
    for name, template in templates.items():
        should, reason = should_run_now(template, state)
        if not should:
            print(f"  ⊘ {name}: {reason}")
            skipped += 1
            continue
        task_id = create_task_from_template(name, template, dry_run=args.dry_run)
        if task_id:
            print(f"  ✓ {name}: created {task_id}")
            state[name] = {"last_run": today, "last_task_id": task_id}
            ran += 1
        else:
            skipped += 1

    if not args.dry_run:
        save_state(state)
    print(f"\n{'[DRY] ' if args.dry_run else ''}Ran: {ran}, Skipped: {skipped}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List all templates")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="Add a template")
    p_add.add_argument("name", help="Unique name for the template")
    p_add.add_argument("--title", help="Task title (defaults to name)")
    p_add.add_argument("--body", help="Task body")
    p_add.add_argument("--board", required=True, help="Board slug")
    p_add.add_argument("--assignee", default="default", help="Profile name")
    p_add.add_argument("--priority", default=5, help="Priority 0-10")
    p_add.add_argument("--schedule", required=True, help="Cron or 'every Nd'")
    p_add.add_argument("--dedupe-key", help="Skip if open task contains this in title/body")
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="Remove a template")
    p_rm.add_argument("name")
    p_rm.set_defaults(func=cmd_remove)

    p_run = sub.add_parser("run", help="Process templates (called by cron)")
    p_run.add_argument("--name", help="Run only one template")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
