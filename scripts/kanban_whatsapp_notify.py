#!/usr/bin/env python3
"""
kanban_whatsapp_notify — send WhatsApp notifications for kanban task events.

Reads task events from a board's SQLite task_events table, formats as
WhatsApp messages, and sends via `hermes send -t whatsapp:<phone>`.

Modes:
  --mode due-today     : notify owner of tasks due today
  --mode overdue       : notify owner of overdue tasks (limit 5 per run)
  --mode new-task      : notify owner of tasks assigned/created in last hour
  --mode completed     : notify subscribers that a task moved to done

Quiet hours: 22:00-08:00 local (America/Asuncion) — defers non-urgent notifications.
Per-owner rate limit: max 3 messages per run.

Usage:
  kanban_whatsapp_notify.py --board ivan-tasks --mode due-today
  kanban_whatsapp_notify.py --board kiki-tasks --mode overdue --dry-run
"""
import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

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




# Per-person → multi-platform routing. Each person can have multiple platforms.
# When a task fires, the first available platform is used. If `hermes send` fails,
# the script falls back to the next number in the list.
# Format: phone in E.164 (no +) for `hermes send -t whatsapp:<phone>`
# This is the ONLY place to set phone numbers.
# Phones now live in HUMAN_PEOPLE inside kanban_common.py (single source of truth).
# This script imports them automatically.


def person_phones_from_assignees(task_id, db_path):
    """Look up the task_assignees sidecar for the task, return list of (person, phones_list).

    Only humans (anyone in HUMAN_PEOPLE) get phones. Agents are filtered out.
    Phones are stored as list of E.164 strings (with '+' prefix) in HUMAN_PEOPLE.
    """
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("SELECT person FROM task_assignees WHERE task_id=?", (task_id,))
        people = [r[0] for r in cur.fetchall()]
    except sqlite3.OperationalError:
        people = []
    con.close()
    # Filter: only humans (anyone in HUMAN_PEOPLE) get phones
    return [(p, HUMAN_PEOPLE.get(p, {}).get("phone", [])) for p in people if p in HUMAN_PEOPLE]


def ensure_due_dates_table(con):
    """Create the due_dates table if it doesn't exist (lazy migration)."""
    try:
        con.execute("SELECT 1 FROM due_dates LIMIT 1")
    except sqlite3.OperationalError:
        con.execute("""
            CREATE TABLE IF NOT EXISTS due_dates (
                task_id TEXT PRIMARY KEY,
                due_at TEXT NOT NULL,
                source TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        con.commit()


# board_db_path imported from kanban_common
def get_due_today_or_overdue(con, overdue_only=False):
    """Get tasks with due_dates <= today, excluding done/archived."""
    today = date.today().isoformat()
    if overdue_only:
        cur = con.execute("""
            SELECT d.task_id, t.title, t.assignee, d.due_at, t.body, d.source
            FROM due_dates d JOIN tasks t ON t.id = d.task_id
            WHERE d.due_at < ? AND t.status NOT IN ('done', 'archived')
            ORDER BY d.due_at LIMIT 5
        """, (today,))
    else:
        cur = con.execute("""
            SELECT d.task_id, t.title, t.assignee, d.due_at, t.body, d.source
            FROM due_dates d JOIN tasks t ON t.id = d.task_id
            WHERE d.due_at <= ? AND t.status NOT IN ('done', 'archived')
            ORDER BY d.due_at LIMIT 10
        """, (today,))
    return cur.fetchall()


def get_recent_new_tasks(con, minutes=60):
    """Get tasks created in the last N minutes, not yet done."""
    cutoff_ts = int((datetime.now() - timedelta(minutes=minutes)).timestamp())
    cur = con.execute("""
        SELECT id, title, assignee, body, created_at
        FROM tasks
        WHERE created_at >= ? AND status NOT IN ('done', 'archived')
        ORDER BY created_at DESC LIMIT 10
    """, (cutoff_ts,))
    return cur.fetchall()


def get_recently_completed(con, minutes=60):
    """Get tasks completed in the last N minutes."""
    cutoff_ts = int((datetime.now() - timedelta(minutes=minutes)).timestamp())
    cur = con.execute("""
        SELECT id, title, assignee, completed_at, result
        FROM tasks
        WHERE completed_at >= ? AND status = 'done'
        ORDER BY completed_at DESC LIMIT 10
    """, (cutoff_ts,))
    return cur.fetchall()


def format_task_msg(task_id, title, assignee, due_at, body, source=None, header="📋"):
    """Format a single task as a WhatsApp message."""
    msg = f"{header} {title}\n"
    if due_at:
        msg += f"📅 Due: {due_at}\n"
    msg += f"🆔 {task_id}\n"
    if body:
        # Truncate body to fit WhatsApp comfortably
        snippet = body[:200].replace("\n", " ")
        if len(body) > 200:
            snippet += "…"
        msg += f"\n{snippet}\n"
    msg += f"\nReply DONE {task_id} when complete."
    return msg


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--board", required=True)
    parser.add_argument("--mode", required=True, choices=["due-today", "overdue", "new-task", "completed"])
    parser.add_argument("--minutes", type=int, default=60, help="Window for new-task/completed modes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet-bypass", action="store_true", help="Send even during quiet hours")
    args = parser.parse_args()

    db = board_db_path(args.board)
    if not db.exists():
        print(f"ERROR: board '{args.board}' not found", file=sys.stderr)
        return 1

    if quiet_hours() and not args.quiet_bypass and args.mode not in ("overdue",):
        print(f"⏸  Skipping {args.mode} notification — quiet hours (22:00-08:00)")
        return 0

    con = sqlite3.connect(db)
    ensure_due_dates_table(con)
    sent = 0
    skipped = 0

    if args.mode == "due-today":
        rows = get_due_today_or_overdue(con, overdue_only=False)
        for row in rows:
            tid, title, assignee, due_at, body, source = row
            # Resolve phones from task_assignees sidecar
            recipients = person_phones_from_assignees(tid, db)
            if not recipients:
                recipients = [(assignee, HUMAN_PEOPLE.get(assignee, {}).get('phone', []))]
            msg = format_task_msg(tid, title, assignee, due_at, body, source,
                                  header="⏰ Due today")
            sent_count = 0
            for person, person_phones in recipients:
                if not person_phones: continue
                ok, status = send_to_platforms(person_phones, msg, args.dry_run)
                if ok: sent_count += 1
            if sent_count: sent += 1
            else: skipped += 1
            print(f"  {tid} → {len(recipients)} recipient(s)")

    elif args.mode == "overdue":
        rows = get_due_today_or_overdue(con, overdue_only=True)
        for row in rows:
            tid, title, assignee, due_at, body, source = row
            recipients = person_phones_from_assignees(tid, db)
            if not recipients:
                recipients = [(assignee, HUMAN_PEOPLE.get(assignee, {}).get('phone', []))]
            days_late = (date.today() - date.fromisoformat(due_at)).days
            msg = f"🚨 OVERDUE ({days_late}d): {title}\n📅 Was due: {due_at}\n🆔 {tid}\n\nReply DONE {tid} when complete."
            sent_count = 0
            for person, person_phones in recipients:
                if not person_phones: continue
                ok, status = send_to_platforms(person_phones, msg, args.dry_run)
                if ok: sent_count += 1
            if sent_count: sent += 1
            else: skipped += 1
            print(f"  {tid} → {len(recipients)} recipient(s)")

    elif args.mode == "new-task":
        rows = get_recent_new_tasks(con, args.minutes)
        for row in rows:
            tid, title, assignee, body, created_at = row
            recipients = person_phones_from_assignees(tid, db)
            if not recipients:
                recipients = [(assignee, HUMAN_PEOPLE.get(assignee, {}).get('phone', []))]
            msg = format_task_msg(tid, title, assignee, None, body, header="📋 New task")
            sent_count = 0
            for person, person_phones in recipients:
                if not person_phones: continue
                ok, status = send_to_platforms(person_phones, msg, args.dry_run)
                if ok: sent_count += 1
            if sent_count: sent += 1
            else: skipped += 1
            print(f"  {tid} → {len(recipients)} recipient(s)")

    elif args.mode == "completed":
        rows = get_recently_completed(con, args.minutes)
        for row in rows:
            tid, title, assignee, completed_at, result = row
            # Notify ALL assignees (they should know their task is done)
            recipients = person_phones_from_assignees(tid, db)
            if not recipients:
                recipients = [(assignee, HUMAN_PEOPLE.get(assignee, {}).get('phone', []))]
            result_snippet = (result or "(no result)")[:150]
            msg = f"✅ Done: {title}\n👤 By: {assignee or '-'}\n🆔 {tid}\n\nResult: {result_snippet}"
            sent_count = 0
            for person, person_phones in recipients:
                if not person_phones: continue
                ok, status = send_to_platforms(person_phones, msg, args.dry_run)
                if ok: sent_count += 1
            if sent_count: sent += 1
            else: skipped += 1
            print(f"  {tid} → {len(recipients)} recipient(s)")

    con.close()
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Sent: {sent}, Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())