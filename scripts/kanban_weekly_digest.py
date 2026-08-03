#!/usr/bin/env python3
"""
kanban_weekly_digest — generate a weekly markdown summary of kanban activity.

Reads every board, computes:
  - Tasks completed this week (per person, per board)
  - Tasks still open (per person, including overdue)
  - New tasks created this week
  - Workload distribution per person

Outputs to stdout (cron delivers verbatim in no-agent mode).

Usage:
  kanban_weekly_digest.py                  # current week (Mon..today)
  kanban_weekly_digest.py --week 2026-07-20 # ISO Monday of the week to summarize
  kanban_weekly_digest.py --send           # send to WhatsApp home + write to inbox
"""
import argparse
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
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



INBOX = Path.home() / ".hermes" / "inbox"


# board_db_path imported from kanban_common
# list_boards imported from kanban_common
def week_bounds(any_day_in_week):
    """Return (monday 00:00, next_monday 00:00) as Unix timestamps."""
    monday = any_day_in_week - timedelta(days=any_day_in_week.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp()), int((monday + timedelta(days=7)).timestamp())


def ensure_due_dates_table(con):
    """Create the due_dates table if it doesn't exist (lazy migration)."""
    try:
        con.execute("SELECT 1 FROM due_dates LIMIT 1")
    except sqlite3.OperationalError:
        con.execute("""
            CREATE TABLE IF NOT EXISTS due_dates (
                task_id TEXT PRIMARY KEY, due_at TEXT NOT NULL, source TEXT,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        con.commit()


def ensure_assignees_table(con):
    """Create the task_assignees table if it doesn't exist (lazy migration)."""
    try:
        con.execute("SELECT 1 FROM task_assignees LIMIT 1")
    except sqlite3.OperationalError:
        con.execute("""
            CREATE TABLE IF NOT EXISTS task_assignees (
                task_id TEXT NOT NULL, person TEXT NOT NULL, role TEXT,
                weight REAL DEFAULT 1.0, created_at INTEGER NOT NULL,
                PRIMARY KEY (task_id, person)
            )
        """)
        con.commit()


def summarize_board(board: str, week_start: int, week_end: int):
    """Return (completed, new_tasks, open_tasks, overdue, per_person_open) for one board."""
    db = board_db_path(board)
    if not db.exists():
        return [], [], [], [], {}
    con = sqlite3.connect(db)
    # Skip boards without a tasks table (stale stub DBs)
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    if not cur.fetchone():
        con.close()
        return [], [], [], [], {}
    ensure_due_dates_table(con)
    ensure_assignees_table(con)

    # Completed this week
    cur = con.execute("""
        SELECT id, title, assignee, completed_at, result
        FROM tasks
        WHERE completed_at >= ? AND completed_at < ? AND status='done'
        ORDER BY completed_at
    """, (week_start, week_end))
    completed = [tuple(r) for r in cur.fetchall()]

    # New tasks created this week
    cur = con.execute("""
        SELECT id, title, assignee, priority, created_at
        FROM tasks
        WHERE created_at >= ? AND created_at < ?
        ORDER BY created_at
    """, (week_start, week_end))
    new_tasks = [tuple(r) for r in cur.fetchall()]

    # Open tasks (not done/archived)
    cur = con.execute("""
        SELECT id, title, assignee, priority, status, block_kind
        FROM tasks
        WHERE status NOT IN ('done', 'archived')
    """)
    open_rows = cur.fetchall()
    open_tasks = [tuple(r) for r in open_rows]

    # Overdue tasks (open + due date in past)
    today = datetime.now().date().isoformat()
    cur = con.execute("""
        SELECT t.id, t.title, t.assignee, d.due_at
        FROM tasks t JOIN due_dates d ON d.task_id = t.id
        WHERE d.due_at < ? AND t.status NOT IN ('done','archived')
        ORDER BY d.due_at
    """, (today,))
    overdue = [tuple(r) for r in cur.fetchall()]

    # Per-person open counts (using sidecar if available)
    per_person = {}
    if open_rows:
        cur = con.execute("""
            SELECT a.person, COUNT(*)
            FROM task_assignees a
            JOIN tasks t ON t.id = a.task_id
            WHERE t.status NOT IN ('done','archived')
            GROUP BY a.person
        """)
        for person, count in cur.fetchall():
            per_person[person] = count

    con.close()
    return completed, new_tasks, open_tasks, overdue, per_person


def format_digest(week_start: int, week_end: int) -> str:
    """Build the full markdown digest."""
    start_dt = datetime.fromtimestamp(week_start)
    end_dt = datetime.fromtimestamp(week_end) - timedelta(seconds=1)
    period = f"{start_dt.strftime('%Y-%m-%d')} → {end_dt.strftime('%Y-%m-%d')}"

    boards = list_boards()
    if not boards:
        return f"📊 Kanban weekly digest — {period}\n\n(no boards found)"

    lines = [
        f"# 📊 Kanban weekly digest — {period}",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
    ]

    all_completed = []
    all_new = []
    all_open = []
    all_overdue = []
    all_per_person = {}

    for board in boards:
        completed, new_tasks, open_tasks, overdue, per_person = summarize_board(board, week_start, week_end)
        all_completed.extend([(board, *t) for t in completed])
        all_new.extend([(board, *t) for t in new_tasks])
        all_open.extend([(board, *t) for t in open_tasks])
        all_overdue.extend([(board, *t) for t in overdue])
        for person, count in per_person.items():
            all_per_person[person] = all_per_person.get(person, 0) + count

    # === Summary ===
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Boards:** {len(boards)}")
    lines.append(f"- **Completed this week:** {len(all_completed)}")
    lines.append(f"- **New tasks this week:** {len(all_new)}")
    lines.append(f"- **Currently open:** {len(all_open)}")
    lines.append(f"- **Overdue:** {len(all_overdue)}")
    lines.append("")

    # Workload distribution
    if all_per_person:
        lines.append("## Workload (open tasks per person)")
        lines.append("")
        for person, count in sorted(all_per_person.items(), key=lambda x: -x[1]):
            lines.append(f"- **{person}**: {count}")
        lines.append("")

    # === Completed this week ===
    lines.append(f"## ✅ Completed this week ({len(all_completed)})")
    if all_completed:
        lines.append("")
        for board, tid, title, assignee, completed_at, result in all_completed:
            when = datetime.fromtimestamp(completed_at).strftime("%a %H:%M")
            snippet = (result or "")[:60].replace("\n", " ")
            if snippet:
                snippet = f" — {snippet}"
            lines.append(f"- `{board}` **{title[:60]}** ({when}){snippet}")
    else:
        lines.append("")
        lines.append("_(none)_")
    lines.append("")

    # === Overdue ===
    lines.append(f"## 🚨 Overdue ({len(all_overdue)})")
    if all_overdue:
        lines.append("")
        today = datetime.now().date()
        for board, tid, title, assignee, due_at in all_overdue:
            days = (today - datetime.fromisoformat(due_at).date()).days
            lines.append(f"- `{board}` **{title[:60]}** — {days}d late (due {due_at})")
    else:
        lines.append("")
        lines.append("🎉 nothing overdue")
    lines.append("")

    # === New this week ===
    lines.append(f"## 📥 New this week ({len(all_new)})")
    if all_new:
        lines.append("")
        for board, tid, title, assignee, priority, created_at in all_new:
            when = datetime.fromtimestamp(created_at).strftime("%a %H:%M")
            lines.append(f"- `{board}` **{title[:60]}** (P{priority}, {when})")
    else:
        lines.append("")
        lines.append("_(none)_")
    lines.append("")

    # === Per-board breakdown ===
    lines.append("## Per-board status")
    lines.append("")
    for board in boards:
        completed, new_tasks, open_tasks, overdue, _ = summarize_board(board, week_start, week_end)
        lines.append(f"### {board}")
        lines.append(f"- open: {len(open_tasks)} · completed this week: {len(completed)} · new: {len(new_tasks)} · overdue: {len(overdue)}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week", help="ISO date (any day in the week). Default: today.")
    parser.add_argument("--send", action="store_true", help="Save to ~/.hermes/inbox/ and send via WhatsApp")
    args = parser.parse_args()

    if args.week:
        any_day = datetime.fromisoformat(args.week)
    else:
        any_day = datetime.now()

    week_start, week_end = week_bounds(any_day)
    digest = format_digest(week_start, week_end)

    # Always print to stdout (cron mode)
    print(digest)

    if args.send:
        # Save to inbox
        INBOX.mkdir(parents=True, exist_ok=True)
        fname = f"kanban-digest-{datetime.fromtimestamp(week_start).strftime('%Y-%m-%d')}.md"
        (INBOX / fname).write_text(digest)
        # Send to WhatsApp home channel
        # Compact version for messaging
        compact = digest[:3000] + ("\n..." if len(digest) > 3000 else "")
        subprocess.run(
            ["hermes", "send", "-t", "whatsapp", "-q", f"📊 *Weekly kanban digest*\n\n{compact}"],
            capture_output=True, text=True
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())