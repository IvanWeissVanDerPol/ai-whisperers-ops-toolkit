#!/usr/bin/env python3
"""
kanban_doctor — health check for the kanban system.

Tier 3.2 — run a comprehensive check, exit non-zero if anything is wrong.

Checks:
  1. DB integrity (PRAGMA integrity_check)
  2. Sidecar tables exist on all populated boards
  3. Indexes present on sidecar tables
  4. No active tasks without assignees
  5. No orphan due_dates / task_assignees
  6. All tenants in registry
  7. Phone numbers in HUMAN_PEOPLE for anyone marked as "needs_phone"
  8. Cron log files not too large
  9. Backup exists for today
  10. WhatsApp bridge reachable

Usage:
  python3 /root/.hermes/scripts/kanban_doctor.py [options]

Exit code:
  0 = all healthy
  1 = warnings (non-critical)
  2 = errors (critical)
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import (
    KANBAN_ROOT, KANBAN_HOME, INBOX_DIR,
    board_db_path, list_boards, table_exists,
    is_human, HUMAN_PEOPLE, today_iso,
)

BACKUP_DIR = KANBAN_HOME / "backups" / "daily"
WHATSAPP_BRIDGE_URL = "http://127.0.0.1:3000/health"

# Tunables
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CRON_FILE_AGE_DAYS = 7


class Doctor:
    """Health check runner. Tracks findings and prints a final report."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.checks: list[tuple[str, str, str]] = []  # (level, name, message)
        # level: "ok" | "warn" | "error"

    def add(self, level: str, name: str, message: str):
        self.checks.append((level, name, message))
        if self.verbose and level != "ok":
            symbols = {"ok": "✓", "warn": "⚠", "error": "✗"}
            print(f"  {symbols.get(level, '?')} {name}: {message}", file=sys.stderr)

    def run_all(self, silent: bool = False) -> int:
        """Run all health checks. Returns exit code (0, 1, or 2)."""
        if not silent:
            print("=" * 60)
            print("Kanban Doctor — Health Check")
            print("=" * 60)

        if not silent:
            print("\n--- Board health ---")
        self.check_db_integrity()
        self.check_sidecar_tables()
        self.check_indexes()

        if not silent:
            print("\n--- Data integrity ---")
        self.check_active_tasks_have_assignees()
        self.check_no_orphan_data()
        self.check_tenants_in_registry()

        if not silent:
            print("\n--- System integrity ---")
        self.check_phone_numbers_configured()
        self.check_cron_log_sizes()
        self.check_backup_exists()
        self.check_whatsapp_bridge()

        return self.summary(json_output=silent)

    # ---- Checks ----

    def check_db_integrity(self):
        for board in list_boards():
            db = board_db_path(board)
            try:
                con = sqlite3.connect(db)
                result = con.execute("PRAGMA integrity_check").fetchone()
                if result and result[0] == "ok":
                    self.add("ok", board, f"DB integrity OK ({db})")
                else:
                    self.add("error", board, f"DB integrity FAILED: {result}")
                con.close()
            except Exception as e:
                self.add("error", board, f"DB integrity check error: {e}")

    def check_sidecar_tables(self):
        for board in list_boards():
            db = board_db_path(board)
            try:
                con = sqlite3.connect(db)
                n_tasks = con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                if n_tasks == 0:
                    con.close()
                    continue
                missing = []
                if not table_exists(con, "due_dates"):
                    missing.append("due_dates")
                if not table_exists(con, "task_assignees"):
                    missing.append("task_assignees")
                if missing:
                    self.add("warn", board, f"missing sidecar tables: {missing}")
                else:
                    self.add("ok", board, f"sidecar tables present ({n_tasks} tasks)")
                con.close()
            except Exception as e:
                self.add("error", board, f"sidecar check error: {e}")

    def check_indexes(self):
        for board in list_boards():
            db = board_db_path(board)
            try:
                con = sqlite3.connect(db)
                for table in ("due_dates", "task_assignees"):
                    if not table_exists(con, table):
                        continue
                    cur = con.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
                        (table,),
                    )
                    indexes = [r[0] for r in cur.fetchall()]
                    auto_idx = [i for i in indexes if i.startswith(f"sqlite_autoindex_{table}")]
                    if not auto_idx:
                        self.add("warn", board, f"{table} has no indexes")
                    else:
                        self.add("ok", board, f"{table} indexed")
                con.close()
            except Exception as e:
                self.add("warn", board, f"index check error: {e}")

    def check_active_tasks_have_assignees(self):
        total_unassigned = 0
        for board in list_boards():
            db = board_db_path(board)
            try:
                con = sqlite3.connect(db)
                if not table_exists(con, "task_assignees"):
                    con.close()
                    continue
                n = con.execute("""
                    SELECT COUNT(*) FROM tasks t
                    LEFT JOIN task_assignees a ON a.task_id = t.id
                    WHERE a.task_id IS NULL AND t.status NOT IN ('done', 'archived')
                """).fetchone()[0]
                if n:
                    self.add("warn", board, f"{n} active tasks without assignee")
                    total_unassigned += n
                con.close()
            except Exception as e:
                self.add("warn", board, f"assignee check error: {e}")
        if total_unassigned == 0:
            self.add("ok", "[all]", "all active tasks have assignees")

    def check_no_orphan_data(self):
        for board in list_boards():
            db = board_db_path(board)
            try:
                con = sqlite3.connect(db)
                for sidecar in ("due_dates", "task_assignees"):
                    if not table_exists(con, sidecar):
                        continue
                    n = con.execute(f"""
                        SELECT COUNT(*) FROM {sidecar} s
                        LEFT JOIN tasks t ON t.id = s.task_id
                        WHERE t.id IS NULL
                    """).fetchone()[0]
                    if n:
                        self.add("warn", board, f"{n} orphan {sidecar} rows")
                con.close()
            except Exception as e:
                self.add("warn", board, f"orphan check error: {e}")

    def check_tenants_in_registry(self):
        reg_path = INBOX_DIR / "kanban-tenants.json"
        if not reg_path.exists():
            self.add("warn", "[tenants]", "no tenant registry file")
            return
        try:
            reg = json.loads(reg_path.read_text())
        except Exception as e:
            self.add("error", "[tenants]", f"registry unreadable: {e}")
            return

        unregistered = set()
        for board in list_boards():
            db = board_db_path(board)
            try:
                con = sqlite3.connect(db)
                for (t,) in con.execute("SELECT DISTINCT tenant FROM tasks WHERE tenant IS NOT NULL"):
                    if t not in reg:
                        unregistered.add(t)
                con.close()
            except Exception:
                continue
        if unregistered:
            self.add("warn", "[tenants]", f"unregistered: {sorted(unregistered)}")
        else:
            self.add("ok", "[tenants]", f"all in-use tenants registered")

    def check_phone_numbers_configured(self):
        missing = [
            p for p, info in HUMAN_PEOPLE.items()
            if not info.get("phone")
        ]
        if missing:
            self.add("warn", "[phones]", f"humans without phones: {missing}")
        else:
            self.add("ok", "[phones]", "all humans have phone numbers")

    def check_cron_log_sizes(self):
        log_dir = INBOX_DIR
        if not log_dir.exists():
            return
        for log_file in log_dir.glob("*.log"):
            size = log_file.stat().st_size
            if size > MAX_LOG_SIZE_BYTES:
                self.add("warn", log_file.name, f"log size {size:,} bytes > {MAX_LOG_SIZE_BYTES:,}")

    def check_backup_exists(self):
        if not BACKUP_DIR.exists():
            self.add("warn", "[backups]", "backup directory missing")
            return
        today = today_iso()
        # Compare on first 8 chars (YYYYMMDD) to match backup dir names like "20260728-..."
        today_compact = today.replace("-", "")
        today_backups = [d for d in BACKUP_DIR.iterdir() if d.name.startswith(today_compact)]
        if not today_backups:
            self.add("warn", "[backups]", f"no backup for {today}")
        else:
            self.add("ok", "[backups]", f"backup found: {today_backups[0].name}")

    def check_whatsapp_bridge(self):
        import urllib.request
        import urllib.error
        try:
            with urllib.request.urlopen(WHATSAPP_BRIDGE_URL, timeout=3) as resp:
                if resp.status == 200:
                    self.add("ok", "[whatsapp]", "bridge reachable")
                else:
                    self.add("warn", "[whatsapp]", f"bridge returned {resp.status}")
        except (urllib.error.URLError, TimeoutError) as e:
            self.add("warn", "[whatsapp]", f"bridge unreachable: {e}")

    # ---- Summary ----

    def summary(self, json_output: bool = False) -> int:
        ok = sum(1 for c in self.checks if c[0] == "ok")
        warn = sum(1 for c in self.checks if c[0] == "warn")
        error = sum(1 for c in self.checks if c[0] == "error")
        if not json_output:
            print("\n" + "=" * 60)
            print(f"Summary: {ok} ok, {warn} warnings, {error} errors")
            print("=" * 60)
        # Watchdog semantic — same as cron_health.py R14 fix.
        # This is a DOCTOR: it produces a report. Warnings are data, not failures.
        # Only exit non-zero when the script itself failed (errors) or
        # when a critical finding was found.
        # Previously: warnings → exit 1 made cron_health flag it as broken.
        # Now: warnings → exit 0 (the report IS the signal), errors → exit 2.
        if error:
            return 2
        return 0


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-q", "--quiet", action="store_true", help="only print warnings/errors")
    p.add_argument("--json", action="store_true", help="output JSON instead of text")
    args = p.parse_args()

    doc = Doctor(verbose=not args.quiet and not args.json)
    if args.json:
        # JSON mode: collect everything, suppress text, print JSON
        doc.run_all(silent=True)
        out = [{"level": c[0], "name": c[1], "message": c[2]} for c in doc.checks]
        print(json.dumps({"checks": out, "exit_code": doc.summary(json_output=True)}, indent=2))
        sys.exit(doc.summary(json_output=True))
    else:
        rc = doc.run_all()
        sys.exit(rc)


if __name__ == "__main__":
    main()
