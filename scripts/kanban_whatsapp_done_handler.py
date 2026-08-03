#!/usr/bin/env python3
"""
kanban_whatsapp_done_handler — poll WhatsApp bridge for DONE replies and mark tasks complete.

Polls http://127.0.0.1:3000/messages, parses patterns like:
  DONE <task_id>     → mark task as done
  DONE              → mark most recent ready task as done
  BLOCK <task_id>    → mark task as blocked
  STATUS             → reply with current board summary

Quiet hours: 22:00-08:00 (defers to log file, doesn't process).
Per-run limit: 50 messages processed.

Usage:
  kanban_whatsapp_done_handler.py --board ivan-tasks
  kanban_whatsapp_done_handler.py --board kiki-tasks --dry-run
"""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
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


# Phones live in HUMAN_PEOPLE inside kanban_common.py (single source of truth).
# This script imports them automatically.


def sender_to_person(sender: str) -> str | None:
    """Look up the person slug from a sender's phone number (E.164).
    
    Handles various formats:
      - "whatsapp:+5959XX"     (bridge /messages format)
      - "+5959XX"               (raw E.164 with +)
      - "5959XX"                (E.164 without +)
      - "5959XX@c.us"           (JID with @c.us suffix)
      - "+5959XX@c.us"          (full WhatsApp JID)
    """
    s = sender.strip()
    # Strip known prefixes
    for prefix in ("whatsapp:", "telegram:", "discord:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    # Strip JID suffix
    s = s.split("@")[0].split(":")[0]
    # Strip leading +
    if s.startswith("+"):
        s = s[1:]
    # Match against known phones (which may or may not have +)
    # HUMAN_PEOPLE entries are dicts: {"role":..., "profile":..., "phone":[...], ...}
    # Pull the 'phone' list out of each.
    for person, info in HUMAN_PEOPLE.items():
        if not isinstance(info, dict):
            continue
        phones = info.get("phone", [])
        if not phones:
            continue
        for phone in phones:
            phone_normalized = phone.lstrip("+")
            if s == phone_normalized:
                return person
    return None


def is_authorized_for_task(sender: str, task_id: str, db_path) -> tuple[bool, str]:
    """Validate sender can act on task_id.

    Returns (authorized, reason).
    Authorization rules:
      1. Sender's phone must map to a known person in OWNER_PHONES.
      2. That person must be in the task's assignees (sidecar table).
      3. OR the task has no sidecar assignees (legacy fallback — anyone in OWNER_PHONES can claim it).

    Anyone else is rejected.
    """
    person = sender_to_person(sender)
    if not person:
        return False, "sender phone not in OWNER_PHONES"
    if not Path(db_path).exists():
        return False, "task DB not found"
    con = sqlite3.connect(db_path)
    try:
        # Check task_assignees (if sidecar exists)
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_assignees'")
        if cur.fetchone():
            cur = con.execute(
                "SELECT person FROM task_assignees WHERE task_id=? AND person=?", (task_id, person)
            )
            if cur.fetchone():
                con.close()
                return True, f"authorized (sidecar: {person})"
            # No sidecar match
            con.close()
            return False, f"person '{person}' is not in task's assignees"
        else:
            # No sidecar table — accept any known person as authorized
            con.close()
            return True, f"authorized (no sidecar; person={person})"
    except Exception as e:
        con.close()
        return False, f"auth check error: {e}"



BRIDGE_URL = "http://127.0.0.1:3000"
QUIET_HOURS_LOG = Path.home() / ".hermes" / "inbox" / "kanban-whatsapp-quiet-hours.log"


# board_db_path imported from kanban_common
def log_to_quiet_hours(payload):
    QUIET_HOURS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with QUIET_HOURS_LOG.open("a") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "msg": payload}) + "\n")


def fetch_messages(timeout=30):
    """Long-poll the WhatsApp bridge for incoming messages."""
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", str(timeout), f"{BRIDGE_URL}/messages"],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if r.returncode != 0:
            return []
        data = json.loads(r.stdout or "[]")
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  fetch error: {e}", file=sys.stderr)
        return []


def mark_done(con, task_id, board, dry_run=False):
    """Mark task as done in the kanban DB."""
    cur = con.execute("SELECT status, title, assignee FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row:
        return False, f"task {task_id} not found on {board}"
    status, title, assignee = row
    if status == "done":
        return True, f"already done (no-op)"
    if dry_run:
        return True, f"[DRY] would mark done"
    now = int(datetime.now().timestamp())
    con.execute("""
        UPDATE tasks SET
            status='done',
            completed_at=?,
            result='Marked done via WhatsApp reply by owner',
            claim_lock=NULL,
            worker_pid=NULL
        WHERE id=?
    """, (now, task_id))
    # Emit event for audit log
    con.execute("""
        INSERT INTO task_events (task_id, kind, payload, created_at)
        VALUES (?, 'whatsapp_done', ?, ?)
    """, (task_id, json.dumps({"board": board, "title": title}), now))
    con.commit()
    return True, f"marked done"


def mark_blocked(con, task_id, reason, board, dry_run=False):
    cur = con.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,))
    if not cur.fetchone():
        return False, f"task {task_id} not found"
    if dry_run:
        return True, f"[DRY] would mark blocked"
    now = int(datetime.now().timestamp())
    con.execute("""
        UPDATE tasks SET status='blocked', block_kind='needs_input',
            last_failure_error=?
        WHERE id=?
    """, (f"Blocked via WhatsApp: {reason}", task_id))
    con.execute("""
        INSERT INTO task_events (task_id, kind, payload, created_at)
        VALUES (?, 'whatsapp_blocked', ?, ?)
    """, (task_id, json.dumps({"board": board, "reason": reason}), now))
    con.commit()
    return True, "marked blocked"


def get_latest_ready_task(con):
    cur = con.execute("""
        SELECT id, title FROM tasks
        WHERE status IN ('ready', 'blocked') AND assignee != 'archive'
        ORDER BY created_at DESC LIMIT 1
    """)
    return cur.fetchone()


def send_reply(chat_id, message, dry_run=False):
    if dry_run:
        print(f"  [DRY] would reply to {chat_id}: {message[:100]}")
        return
    cmd = ["hermes", "send", "-t", f"whatsapp:{chat_id}", "-q", message]
    subprocess.run(cmd, capture_output=True, text=True)


def handle_message(msg, board, db_path, dry_run=False):
    """Process one WhatsApp message. Returns (handled, reply_text)."""
    body = msg.get("body") or msg.get("message") or ""
    sender = msg.get("from") or msg.get("chatId") or "unknown"
    if not body:
        return False, None

    body_stripped = body.strip()
    body_upper = body_stripped.upper()

    # Pattern: DONE t_xxxxx (case-insensitive)
    m = re.match(r"^DONE\s+(T_[A-F0-9]+)\b", body_upper)
    if m:
        task_id = m.group(1).lower()  # normalize back to lowercase
        # Auth check: only the task's assignee can mark it done
        auth_ok, auth_reason = is_authorized_for_task(sender, task_id, db_path)
        if not auth_ok:
            return False, f"⛔ {task_id}: auth denied — {auth_reason}"
        con = sqlite3.connect(db_path)
        ok, status = mark_done(con, task_id, board, dry_run)
        con.close()
        return ok, f"{'✓' if ok else '✗'} {task_id}: {status}"

    # Pattern: DONE (no task_id — use most recent ready task)
    if body_upper == "DONE":
        con = sqlite3.connect(db_path)
        row = get_latest_ready_task(con)
        if not row:
            con.close()
            return False, "No active task found to mark done."
        task_id, title = row
        ok, status = mark_done(con, task_id, board, dry_run)
        con.close()
        return ok, f"{'✓' if ok else '✗'} {task_id} ({title[:40]}): {status}"

    # Pattern: BLOCK t_xxxxx [reason] (case-insensitive)
    m = re.match(r"^BLOCK\s+(T_[A-F0-9]+)\b\s*(.*)?", body_upper)
    if m:
        task_id = m.group(1).lower()
        # Auth check: same as DONE
        auth_ok, auth_reason = is_authorized_for_task(sender, task_id, db_path)
        if not auth_ok:
            return False, f"⛔ {task_id}: auth denied — {auth_reason}"
        reason = (m.group(2) or "").strip() or "no reason given"
        con = sqlite3.connect(db_path)
        ok, status = mark_blocked(con, task_id, reason, board, dry_run)
        con.close()
        return ok, f"{'✓' if ok else '✗'} {task_id}: {status}"

    # Pattern: STATUS
    if body_upper == "STATUS" or body_upper == "BOARD":
        con = sqlite3.connect(db_path)
        cur = con.execute("""
            SELECT
                COUNT(CASE WHEN status='ready' THEN 1 END),
                COUNT(CASE WHEN status='blocked' THEN 1 END),
                COUNT(CASE WHEN status='done' THEN 1 END),
                COUNT(CASE WHEN status='running' THEN 1 END)
            FROM tasks
        """)
        ready, blocked, done, running = cur.fetchone()
        # Add overdue count
        try:
            today = datetime.now().date().isoformat()
            cur = con.execute("""
                SELECT COUNT(*) FROM due_dates d
                JOIN tasks t ON t.id = d.task_id
                WHERE d.due_at < ? AND t.status NOT IN ('done','archived')
            """, (today,))
            overdue = cur.fetchone()[0]
        except sqlite3.OperationalError:
            overdue = 0
        con.close()
        return True, (f"📊 {board}: {ready} ready · {blocked} blocked · "
                      f"{running} running · {done} done · {overdue} overdue")

    # Pattern: LIST
    if body_upper == "LIST":
        con = sqlite3.connect(db_path)
        cur = con.execute("""
            SELECT id, title, status, due_at FROM due_dates d
            JOIN tasks t ON t.id = d.task_id
            WHERE t.status NOT IN ('done','archived')
            ORDER BY d.due_at LIMIT 10
        """)
        rows = cur.fetchall()
        con.close()
        if not rows:
            return True, "(no active tasks)"
        lines = ["📋 Your tasks:"]
        for r in rows:
            lines.append(f"  • {r[0]} {r[1][:40]} ({r[2]}, due {r[3]})")
        return True, "\n".join(lines)

    return False, None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--board", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=50, help="Max messages per run")
    parser.add_argument("--quiet-bypass", action="store_true")
    args = parser.parse_args()

    db = board_db_path(args.board)
    if not db.exists():
        print(f"ERROR: board '{args.board}' not found", file=sys.stderr)
        return 1

    if quiet_hours() and not args.quiet_bypass:
        print(f"⏸  Quiet hours — deferring. Will check next run.")
        # Still fetch and log so we don't miss anything
        msgs = fetch_messages(timeout=5)
        for msg in msgs:
            log_to_quiet_hours(msg)
        return 0

    msgs = fetch_messages(timeout=30)
    if not msgs:
        print("(no new messages)")
        return 0

    processed = 0
    for msg in msgs[:args.limit]:
        body = (msg.get("body") or "")[:80]
        sender = msg.get("from") or msg.get("chatId") or "?"
        handled, reply = handle_message(msg, args.board, db, args.dry_run)
        if handled:
            processed += 1
            print(f"✓ [{sender}] '{body}' → {reply}")
            if reply:
                send_reply(sender, reply, args.dry_run)
        else:
            # Not a command — log but don't reply (avoid noise)
            if body.strip():
                print(f"  [{sender}] '{body}' (ignored)")

    print(f"\nProcessed {processed} command(s) from {len(msgs)} message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())