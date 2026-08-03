"""
kanban_store — typed persistence layer for the kanban.

Replaces the ~25 raw `con.execute(...)` calls scattered across our 11
extension scripts with a single, testable API.

Usage:
    from kanban_store import KanbanStore, Task, Assignee, DueDate, Tenant

    with KanbanStore("ivan-tasks") as store:
        task = store.get_task("t_b4e05b10")
        tasks = store.get_tasks_for_person("ivan")
        store.add_assignee("t_b4e05b10", "lua", role="Design & Styling", weight=0.5)
        store.set_due_date("t_b4e05b10", "2026-08-15", source="manual")

Why this exists:
- One place to fix SQL bugs
- Transaction wrappers (Tier 1.2) live here
- Migrations (Tier 9.3) live here
- Mockable in tests (Tier 2.x)
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

from kanban_common import (
    KANBAN_ROOT, KANBAN_HOME, board_db_path, list_boards,
    ensure_due_dates_table, ensure_task_assignees_table,
    table_exists, now_ts,
)


# ---- Domain models (plain dataclasses, not pydantic — pydantic is Tier 1.3) --

@dataclass
class Task:
    """A kanban task. Field set mirrors the `tasks` table.

    Columns not in our typed fields go into `extra` so we don't drop data
    when the schema evolves.
    """
    id: str
    title: str
    body: str | None = None
    assignee: str | None = None
    status: str = "ready"
    priority: int = 5
    created_by: str | None = None
    created_at: int = 0
    started_at: int | None = None
    completed_at: int | None = None
    workspace_kind: str = "scratch"
    workspace_path: str | None = None
    branch_name: str | None = None
    project_id: str | None = None
    claim_lock: str | None = None
    claim_expires: int | None = None
    tenant: str | None = None
    result: str | None = None
    idempotency_key: str | None = None
    consecutive_failures: int = 0
    worker_pid: int | None = None
    last_failure_error: str | None = None
    max_runtime_seconds: int | None = None
    last_heartbeat_at: int | None = None
    current_run_id: int | None = None
    workflow_template_id: str | None = None
    current_step_key: str | None = None
    skills: str | None = None
    model_override: str | None = None
    provider_override: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Assignee:
    task_id: str
    person: str
    role: str | None
    weight: float
    created_at: int


@dataclass
class DueDate:
    task_id: str
    due_at: str  # YYYY-MM-DD
    source: str | None
    created_at: int
    updated_at: int


@dataclass
class Tenant:
    name: str  # the slug (e.g., "Ai-Whisperers")
    display_name: str
    notes: str | None
    updated_at: str | None


# ---- The store -----------------------------------------------------------

class KanbanStore:
    """Persistent store for one board's kanban data.

    Lazy-creates sidecar tables (due_dates, task_assignees) on construction.
    Wraps writes in transactions.
    """

    def __init__(self, board: str, db_path: Path | None = None):
        self.board = board
        self.db_path = db_path or board_db_path(board)
        self._lock = threading.RLock()  # re-entrant lock for nested calls
        self._conn: sqlite3.Connection | None = None

    # ---- Connection management ----

    def _connect(self) -> sqlite3.Connection:
        """Lazy-connect. Caller should hold self._lock."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            self._conn.row_factory = sqlite3.Row
            # Apply PRAGMA tuning (Tier 8.1) on every connection
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-64000")  # 64MB
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()

    # ---- Schema ----

    def ensure_schema(self):
        """Lazy-create sidecar tables."""
        with self._lock:
            con = self._connect()
            ensure_due_dates_table(con)
            ensure_task_assignees_table(con)
            con.commit()

    # ---- Transactions ----

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Wrap a block in a transaction. BEGIN IMMEDIATE so writers don't race.

        Usage:
            with store.transaction() as con:
                con.execute(...)
                con.execute(...)
        """
        with self._lock:
            con = self._connect()
            # BEGIN IMMEDIATE acquires a write lock immediately, preventing
            # dispatcher races where multiple writers interleave.
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise

    # ---- Task queries ----

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            con = self._connect()
            cur = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def list_tasks(
        self,
        board: str | None = None,
        status: list[str] | None = None,
        tenant: str | None = None,
        assignee: str | None = None,
        priority_max: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with optional filters. Returns Task objects."""
        where = []
        params = []
        if status:
            placeholders = ",".join("?" * len(status))
            where.append(f"status IN ({placeholders})")
            params.extend(status)
        if tenant is not None:
            where.append("tenant = ?")
            params.append(tenant)
        if assignee is not None:
            where.append("assignee = ?")
            params.append(assignee)
        if priority_max is not None:
            where.append("priority <= ?")
            params.append(priority_max)
        where_clause = " AND ".join(where) if where else "1=1"
        params.extend([limit, offset])

        with self._lock:
            con = self._connect()
            cur = con.execute(
                f"SELECT * FROM tasks WHERE {where_clause} "
                f"ORDER BY priority ASC, created_at ASC LIMIT ? OFFSET ?",
                params,
            )
            return [self._row_to_task(row) for row in cur.fetchall()]

    # ---- Assignees ----

    def add_assignee(
        self,
        task_id: str,
        person: str,
        role: str | None = None,
        weight: float = 1.0,
    ) -> bool:
        """Add a sidecar assignee. Returns True if added, False if already present."""
        with self.transaction() as con:
            try:
                con.execute(
                    "INSERT INTO task_assignees (task_id, person, role, weight, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (task_id, person, role, weight, now_ts()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_assignee(self, task_id: str, person: str) -> bool:
        with self.transaction() as con:
            cur = con.execute(
                "DELETE FROM task_assignees WHERE task_id=? AND person=?",
                (task_id, person),
            )
            return cur.rowcount > 0

    def list_assignees(self, task_id: str) -> list[Assignee]:
        with self._lock:
            con = self._connect()
            if not table_exists(con, "task_assignees"):
                return []
            cur = con.execute(
                "SELECT task_id, person, role, weight, created_at FROM task_assignees "
                "WHERE task_id=? ORDER BY weight DESC, created_at ASC",
                (task_id,),
            )
            return [Assignee(*row) for row in cur.fetchall()]

    def list_tasks_for_person(
        self,
        person: str,
        include_done: bool = False,
    ) -> list[tuple[Task, Assignee]]:
        """Return (task, assignee) pairs for a person across this board."""
        with self._lock:
            con = self._connect()
            if not table_exists(con, "task_assignees"):
                return []
            status_filter = "" if include_done else "AND t.status NOT IN ('done','archived')"
            cur = con.execute(
                f"SELECT t.*, a.person, a.role, a.weight, a.created_at "
                f"FROM task_assignees a JOIN tasks t ON t.id = a.task_id "
                f"WHERE a.person = ? {status_filter} "
                f"ORDER BY t.priority ASC, t.created_at ASC",
                (person,),
            )
            results = []
            for row in cur.fetchall():
                # Last 4 columns are a.person, a.role, a.weight, a.created_at
                task = self._row_to_task(row[:-4])
                assignee = Assignee(
                    task_id=row[-4], person=row[-3],
                    role=row[-2], weight=row[-1],
                    created_at=row[0],
                )
                # Wait — created_at in Assignee should be a.created_at
                # But the row is ordered: t.* columns first, then a.person, a.role, a.weight, a.created_at
                # Actually we want a.created_at for Assignee.created_at, which is the LAST column
                results.append((task, Assignee(
                    task_id=task.id,
                    person=row[-4],
                    role=row[-3],
                    weight=row[-2],
                    created_at=row[-1],
                )))
            return results

    # ---- Due dates ----

    def set_due_date(
        self,
        task_id: str,
        due_at: str,
        source: str | None = None,
    ) -> bool:
        """Set or update a task's due date."""
        ts = now_ts()
        with self.transaction() as con:
            # Upsert: INSERT ... ON CONFLICT DO UPDATE
            con.execute(
                "INSERT INTO due_dates (task_id, due_at, source, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET due_at=excluded.due_at, "
                "source=excluded.source, updated_at=excluded.updated_at",
                (task_id, due_at, source, ts, ts),
            )
            return True

    def get_due_date(self, task_id: str) -> DueDate | None:
        with self._lock:
            con = self._connect()
            if not table_exists(con, "due_dates"):
                return None
            cur = con.execute(
                "SELECT task_id, due_at, source, created_at, updated_at "
                "FROM due_dates WHERE task_id=?",
                (task_id,),
            )
            row = cur.fetchone()
            return DueDate(*row) if row else None

    def list_overdue(self, today_iso: str) -> list[tuple[Task, DueDate]]:
        """Return (task, due_date) pairs where due_at < today and task is active."""
        with self._lock:
            con = self._connect()
            if not table_exists(con, "due_dates"):
                return []
            cur = con.execute(
                "SELECT t.*, d.due_at, d.source, d.created_at, d.updated_at "
                "FROM due_dates d JOIN tasks t ON t.id = d.task_id "
                "WHERE d.due_at < ? AND t.status NOT IN ('done','archived') "
                "ORDER BY d.due_at ASC",
                (today_iso,),
            )
            results = []
            for row in cur.fetchall():
                task = self._row_to_task(row[:-4])
                due = DueDate(
                    task_id=task.id,
                    due_at=row[-4],
                    source=row[-3],
                    created_at=row[-2],
                    updated_at=row[-1],
                )
                results.append((task, due))
            return results

    # ---- Tenant ----

    def set_tenant(self, task_id: str, tenant: str | None) -> bool:
        """Set (or clear) a task's tenant."""
        with self.transaction() as con:
            con.execute("UPDATE tasks SET tenant=? WHERE id=?", (tenant, task_id))
            return True

    # ---- Status updates ----

    def set_status(self, task_id: str, status: str) -> bool:
        """Mark a task's status. Validates against allowed values."""
        ALLOWED = {"ready", "running", "blocked", "done", "archived"}
        if status not in ALLOWED:
            raise ValueError(f"status must be one of {ALLOWED}, got {status!r}")
        with self.transaction() as con:
            con.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
            return True

    # ---- Internals ----

    def _row_to_dict(self, row) -> dict:
        """Convert a sqlite3.Row OR tuple to a dict. Works for both."""
        if isinstance(row, sqlite3.Row):
            return {key: row[key] for key in row.keys()}
        # tuple — assume it's a positional row matching SELECT *; use schema introspection
        con = self._connect()
        cur = con.execute("PRAGMA table_info(tasks)")
        cols = [r[1] for r in cur.fetchall()]
        return dict(zip(cols, row))

    def _row_to_task(self, row) -> Task:
        """Convert a SQLite row to a Task dataclass. Handles Row or tuple."""
        d = self._row_to_dict(row)
        # Split known vs unknown fields; put unknowns in Task.extra
        try:
            return Task(**d)
        except TypeError:
            # Some columns aren't in our dataclass — put them in extra
            known_fields = {"id", "title", "body", "assignee", "status", "priority",
                             "created_by", "created_at", "started_at", "completed_at",
                             "workspace_kind", "workspace_path", "branch_name",
                             "project_id", "claim_lock", "claim_expires", "tenant",
                             "result", "idempotency_key", "consecutive_failures",
                             "worker_pid", "last_failure_error", "max_runtime_seconds",
                             "last_heartbeat_at", "current_run_id",
                             "workflow_template_id", "current_step_key",
                             "skills", "model_override", "provider_override"}
            extras = {k: v for k, v in d.items() if k not in known_fields}
            known = {k: v for k, v in d.items() if k in known_fields}
            return Task(extra=extras, **known)


# ---- Module-level convenience --------------------------------------------

def for_board(board: str) -> KanbanStore:
    """Shorthand: KanbanStore("ivan-tasks")."""
    return KanbanStore(board)
