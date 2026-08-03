"""
kanban_common — shared utilities for all kanban extension scripts.

This module exists to eliminate the duplication that grew across 11 scripts
in 2026-07-28. Every script should import from here instead of redefining:

- board_db_path(board) — resolve kanban.db path for any board slug
- list_boards() — return all boards (legacy default + multi-board)
- KANBAN_ROOT, KANBAN_HOME — paths used everywhere
- ensure_due_dates_table / ensure_task_assignees_table — lazy schema migration
- quiet_hours() — check whether to send notifications
- send_to_platforms(phones, message, dry_run) — multi-platform WhatsApp send
- PEOPLE, HUMAN_PEOPLE, AGENT_PEOPLE — combined people registry
- DEFAULT_TENANT — internal tenant name for tasks created by our scripts
- safe_log(level, msg) — log that doesn't break on missing dirs
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, time
from pathlib import Path

# ---- Paths ----------------------------------------------------------------

KANBAN_ROOT = Path("/root/.hermes/kanban")          # Multi-board layout lives here
KANBAN_HOME = Path("/root/.hermes")                  # Parent for legacy default board
INBOX_DIR = Path.home() / ".hermes" / "inbox"        # State files, templates, registry


# ---- Board path resolution ------------------------------------------------

def board_db_path(board: str) -> Path:
    """Resolve the SQLite path for a board.

    The 'default' board lives at <kanban_home>/kanban.db (legacy pre-boards path).
    Other boards live at <kanban_root>/boards/<slug>/kanban.db.
    """
    if board == "default":
        return KANBAN_HOME / "kanban.db"
    return KANBAN_ROOT / "boards" / board / "kanban.db"


def list_boards() -> list[str]:
    """Return all boards (legacy default + multi-board). Order: default first."""
    boards = []
    if (KANBAN_HOME / "kanban.db").exists():
        boards.append("default")
    boards_dir = KANBAN_ROOT / "boards"
    if boards_dir.exists():
        for d in sorted(boards_dir.iterdir()):
            if d.is_dir() and (d / "kanban.db").exists():
                boards.append(d.name)
    return boards


def current_board_file() -> Path:
    """Path to the file that tracks the active board."""
    return KANBAN_ROOT / "current"


def read_current_board() -> str:
    """Read the active board slug from disk. Defaults to 'default' if missing."""
    f = current_board_file()
    if not f.exists():
        return "default"
    text = f.read_text().strip()
    return text or "default"


# ---- Schema helpers (lazy migration) --------------------------------------

def ensure_due_dates_table(con: sqlite3.Connection) -> None:
    """Create the due_dates sidecar table if it doesn't exist.

    Idempotent. Safe to call on every script invocation.
    """
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


def ensure_task_assignees_table(con: sqlite3.Connection) -> None:
    """Create the task_assignees sidecar table if it doesn't exist.

    Idempotent. Safe to call on every script invocation.
    """
    try:
        con.execute("SELECT 1 FROM task_assignees LIMIT 1")
    except sqlite3.OperationalError:
        con.execute("""
            CREATE TABLE IF NOT EXISTS task_assignees (
                task_id TEXT NOT NULL,
                person TEXT NOT NULL,
                role TEXT,
                weight REAL DEFAULT 1.0,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (task_id, person),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        con.commit()


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    """Return True if a table exists in the connection."""
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return bool(cur.fetchone())


# ---- Time helpers ---------------------------------------------------------

def now_ts() -> int:
    """Current unix timestamp (seconds). Replaces deprecated utcnow().timestamp()."""
    return int(datetime.now().timestamp())


def today_iso() -> str:
    """Today's date as YYYY-MM-DD in local timezone. Replaces utcnow().date()."""
    return datetime.now().date().isoformat()


# ---- Quiet hours ----------------------------------------------------------

def quiet_hours() -> bool:
    """Return True if it's currently in quiet hours (22:00-08:00 local time).

    Use to suppress WhatsApp notifications during off-hours.
    """
    now = datetime.now().time()
    return now >= time(22, 0) or now < time(8, 0)


def log_quiet_hours(payload: dict, log_path: Path | None = None) -> None:
    """Write a JSON record to the quiet-hours log file.

    Default path: <inbox>/kanban-quiet-hours.log
    """
    if log_path is None:
        log_path = INBOX_DIR / "kanban-quiet-hours.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps({**payload, "logged_at": datetime.now().isoformat()}) + "\n")


# ---- WhatsApp multi-platform send -----------------------------------------

def send_to_platforms(
    phones: list[str] | None,
    message: str,
    dry_run: bool = False,
    home_channel: str | None = None,
) -> tuple[bool, str]:
    """Try each phone in order. Returns (success, status_message).

    Parameters:
        phones: list of E.164 phone numbers WITH '+' prefix (e.g. '+595981324569').
                Empty list or None means "no phones configured" — caller should skip.
        message: text to send.
        dry_run: if True, print what would be sent instead of sending.
        home_channel: optional home channel ID to send to when phones are empty.

    Returns:
        (True, "sent to +XXX") if at least one send succeeded.
        (False, "no phones configured") if phones was empty/None.
        (False, "all N phones failed") if every send failed.
    """
    if not phones:
        return False, "no phones configured"

    if dry_run:
        print(f"  [DRY] would send to {phones[0]}: {message[:80]}")
        return True, "dry-run"

    for phone in phones:
        cmd = ["hermes", "send", "-t", f"whatsapp:{phone}", "-q", message]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return True, f"sent to {phone}"
        except subprocess.TimeoutExpired:
            continue
    return False, f"all {len(phones)} phones failed"


# ---- People registry ------------------------------------------------------

# Humans get WhatsApp notifications. Agents don't (they receive work via dispatcher).
HUMAN_PEOPLE = {
    # Phone numbers are stored WITH the leading '+' (E.164 format).
    # Update these when you know someone's number. Or override via env vars:
    #   KANBAN_PHONE_IVAN, KANBAN_PHONE_KIKI, KANBAN_PHONE_LUA, KANBAN_PHONE_SONIA
    # Format: env var is a single E.164 number (with +). Multiple phones
    # require editing the file directly.
    "ivan":  {"role": "Dev",             "profile": "default",    "phone": ["+595****4569"], "is_human": True},
    "kiki":  {"role": "Management",      "profile": "copy-bot",   "phone": ["+595****4135"], "is_human": True},
    "lua":   {"role": "Design & Styling","profile": "lua",         "phone": ["+595****5035"], "is_human": True},
    "sonia": {"role": "Main Client",     "profile": "default",    "phone": ["+595****5138"], "is_human": True},
}


def _load_phone_overrides() -> dict[str, list[str]]:
    """Read KANBAN_PHONE_<PERSON> env vars and return dict of {person: [phone]}.
    Used to override the static HUMAN_PEOPLE phones without editing code.
    """
    import os
    overrides = {}
    for person in HUMAN_PEOPLE:
        env_key = f"KANBAN_PHONE_{person.upper()}"
        value = os.environ.get(env_key, "").strip()
        if value:
            overrides[person] = [value]
    return overrides


def get_human_phones(person: str) -> list[str]:
    """Get phone list for a person, considering env var overrides."""
    overrides = _load_phone_overrides()
    if person in overrides:
        return overrides[person]
    return HUMAN_PEOPLE.get(person, {}).get("phone", [])


AGENT_PEOPLE = {
    "default":            {"role": "@agent",        "profile": "default",            "is_human": False},
    "copy-bot":           {"role": "@agent:copy",   "profile": "copy-bot",           "is_human": False},
    "design-bot":         {"role": "@agent:design", "profile": "design-bot",         "is_human": False},
    "architect-bot":      {"role": "@agent:arch",   "profile": "architect-bot",      "is_human": False},
    "closer-bot":         {"role": "@agent:sales",  "profile": "closer-bot",         "is_human": False},
    "explorer-bot":       {"role": "@agent:seo",    "profile": "explorer-bot",       "is_human": False},
    "delivery-bot":       {"role": "@agent:deploy", "profile": "delivery-bot",       "is_human": False},
    "client-success-bot": {"role": "@agent:cs",     "profile": "client-success-bot", "is_human": False},
    "ops-bot":            {"role": "@agent:ops",    "profile": "ops-bot",            "is_human": False},
    "dentist-content-bot":{"role": "@agent:dentist-copy",   "profile": "dentist-content-bot", "is_human": False},
    "dentist-deploy-bot": {"role": "@agent:dentist-deploy", "profile": "dentist-deploy-bot",  "is_human": False},
    "dentist-design-bot": {"role": "@agent:dentist-design", "profile": "dentist-design-bot",  "is_human": False},
}

PEOPLE = {**HUMAN_PEOPLE, **AGENT_PEOPLE}


def is_human(person: str) -> bool:
    """True if person is in HUMAN_PEOPLE."""
    return person in HUMAN_PEOPLE


def is_known_person(person: str) -> bool:
    """True if person is anywhere in PEOPLE."""
    return person in PEOPLE


# ---- Tenant defaults ------------------------------------------------------

DEFAULT_TENANT = "Ai-Whisperers"  # Internal company. Used when our scripts create tasks
                                    # that don't fit a specific client/product tenant.


# ---- Cron pipeline wrapper ------------------------------------------------

def run_pipeline_scripts() -> dict[str, str]:
    """Run the 3 sub-scripts in the kanban pipeline cron.

    Returns a dict mapping script name to its stdout (truncated to 500 chars).
    Used by kanban_pipeline_cron.sh and tests.
    """
    scripts = [
        ("voice", "kanban_voice_cron.py"),
        ("notify", "kanban_whatsapp_notify.py"),
        ("done", "kanban_whatsapp_done_handler.py"),
    ]
    results = {}
    for key, name in scripts:
        path = INBOX_DIR.parent / "scripts" / name
        if not path.exists():
            results[key] = "SCRIPT NOT FOUND"
            continue
        r = subprocess.run(["python3", str(path)], capture_output=True, text=True, timeout=60)
        out = (r.stdout or "")[:500]
        results[key] = out + (r.stderr[:200] if r.stderr else "")
    return results


# ---- CLI helpers ----------------------------------------------------------

def eprint(msg: str) -> None:
    """Print to stderr."""
    print(msg, file=sys.stderr)


def exit_error(msg: str, code: int = 1) -> None:
    """Print error to stderr and exit with code."""
    eprint(f"ERROR: {msg}")
    sys.exit(code)
