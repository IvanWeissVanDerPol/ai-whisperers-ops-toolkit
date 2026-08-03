#!/usr/bin/env python3
"""
kanban_tenants — manage the `tenant` field on kanban tasks.

`tenant` is a free-text namespace (client, org, project). Use this to:
  - Mark a task as belonging to a specific client (e.g. HidroBaby-Spa)
  - Filter or group tasks by client
  - Track which work belongs to the company itself (default: Ai-Whisperers)

The tenant registry at ~/.hermes/inbox/kanban-tenants.json holds metadata
(display name, notes). All in-use tenants should be registered.

Uses the typed persistence layer (kanban_store.py) for all DB operations.

Usage:
  kanban_tenants.py list                    # list all registered tenants
  kanban_tenants.py --board ivan-tasks set <task_id> <tenant>
  kanban_tenants.py --board ivan-tasks clear <task_id>
  kanban_tenants.py --board ivan-tasks bulk-set --tenant X --match "Y"
  kanban_tenants.py stats
  kanban_tenants.py register <name> [--display "Name"] [--notes "..."]
  kanban_tenants.py rename <old> <new>
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

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
from kanban_models import TenantModel  # noqa


TENANT_REGISTRY_PATH = INBOX_DIR / "kanban-tenants.json"


# ---- Registry helpers ----

def load_tenant_registry() -> dict:
    """Load registered tenants from JSON. Returns dict keyed by tenant name."""
    if not TENANT_REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(TENANT_REGISTRY_PATH.read_text())
    except Exception as e:
        print(f"WARN: registry unreadable: {e}", file=sys.stderr)
        return {}


def save_tenant_registry(reg: dict) -> None:
    """Save registered tenants to JSON."""
    TENANT_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    TENANT_REGISTRY_PATH.write_text(json.dumps(reg, indent=1, sort_keys=True))


# ---- Commands ----

def cmd_list(args):
    """List all registered tenants (and which are in use)."""
    reg = load_tenant_registry()
    if not reg:
        print("No tenants registered yet.")
        return 0
    # Find which are in use across all boards
    in_use = defaultdict(int)
    for board in list_boards():
        with KanbanStore(board) as store:
            try:
                cur = store._connect().execute("SELECT tenant, COUNT(*) FROM tasks WHERE tenant IS NOT NULL GROUP BY tenant")
                for tenant, count in cur.fetchall():
                    in_use[tenant] += count
            except Exception:
                continue
    print(f"{'TENANT':<22} {'DISPLAY':<22} {'IN USE':<8} NOTES")
    print("-" * 80)
    for name, info in sorted(reg.items()):
        if isinstance(info, dict):
            display = info.get("display_name", name)
            notes = info.get("notes", "")
        else:
            display = info
            notes = ""
        count = in_use.get(name, 0)
        print(f"{name:<22} {display:<22} {count:<8} {notes}")
    # Also print any in-use but unregistered
    for name, count in in_use.items():
        if name not in reg:
            print(f"{name:<22} ⚠ unregistered! {count}")
    return 0


def cmd_set(args):
    """Set a task's tenant."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        task = store.get_task(args.task_id)
        if not task:
            print(f"ERROR: task {args.task_id} not found on '{args.board}'", file=sys.stderr)
            return 1
        store.set_tenant(args.task_id, args.tenant)
        print(f"✓ {args.task_id} tenant={args.tenant}")
    return 0


def cmd_clear(args):
    """Clear a task's tenant (set to NULL)."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        store.set_tenant(args.task_id, None)
        print(f"✓ {args.task_id} tenant cleared")
    return 0


def cmd_bulk_set(args):
    """Set tenant on all tasks where title/body matches a regex."""
    import re
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        pattern = re.compile(args.match, re.IGNORECASE)
        cur = store._connect().execute("SELECT id, title, body FROM tasks WHERE tenant IS NULL OR tenant != ?", (args.tenant,))
        candidates = cur.fetchall()
        updated = 0
        for tid, title, body in candidates:
            if pattern.search(title or "") or pattern.search(body or ""):
                store.set_tenant(tid, args.tenant)
                updated += 1
        print(f"✓ {updated} tasks on '{args.board}' set to tenant={args.tenant}")
    return 0


def cmd_stats(args):
    """Show tenant usage stats across all boards."""
    in_use = defaultdict(lambda: {"count": 0, "boards": set(), "active": 0})
    for board in list_boards():
        with KanbanStore(board) as store:
            try:
                cur = store._connect().execute(
                    "SELECT tenant, status, COUNT(*) FROM tasks WHERE tenant IS NOT NULL GROUP BY tenant, status"
                )
                for tenant, status, count in cur.fetchall():
                    in_use[tenant]["count"] += count
                    in_use[tenant]["boards"].add(board)
                    if status not in ("done", "archived"):
                        in_use[tenant]["active"] += count
            except Exception:
                continue
    if not in_use:
        print("No tenants in use.")
        return 0
    reg = load_tenant_registry()
    print(f"{'TENANT':<22} {'TASKS':<8} {'ACTIVE':<8} {'BOARDS'}")
    print("-" * 60)
    for name, info in sorted(in_use.items(), key=lambda x: -x[1]["count"]):
        boards = ", ".join(sorted(info["boards"]))
        marker = " ✓" if name in reg else " ⚠ unregistered"
        print(f"{name:<22} {info['count']:<8} {info['active']:<8} {boards}{marker}")
    return 0


def cmd_register(args):
    """Register a tenant in the metadata registry."""
    reg = load_tenant_registry()
    try:
        model = TenantModel(
            name=args.name,
            display_name=args.display or args.name,
            notes=args.notes,
        )
        reg[model.name] = {
            "display_name": model.display_name,
            "notes": model.notes,
        }
        save_tenant_registry(reg)
        print(f"✓ Registered '{model.name}' (display='{model.display_name}')")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_rename(args):
    """Rename a tenant across the registry AND all DB columns."""
    reg = load_tenant_registry()
    if args.old not in reg:
        print(f"ERROR: '{args.old}' not in registry", file=sys.stderr)
        return 1
    if args.new in reg:
        print(f"ERROR: '{args.new}' already exists in registry", file=sys.stderr)
        return 1
    # Update registry
    reg[args.new] = reg.pop(args.old)
    save_tenant_registry(reg)
    # Update DBs
    updated = 0
    for board in list_boards():
        with KanbanStore(board) as store:
            cur = store._connect().execute("UPDATE tasks SET tenant=? WHERE tenant=?", (args.new, args.old))
            updated += cur.rowcount
    print(f"✓ Renamed '{args.old}' → '{args.new}' (updated {updated} tasks)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", help="Which board (required for set/clear/bulk-set)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)

    p_set = sub.add_parser("set")
    p_set.add_argument("task_id")
    p_set.add_argument("tenant")
    p_set.set_defaults(func=cmd_set)

    p_clear = sub.add_parser("clear")
    p_clear.add_argument("task_id")
    p_clear.set_defaults(func=cmd_clear)

    p_bulk = sub.add_parser("bulk-set")
    p_bulk.add_argument("--tenant", required=True)
    p_bulk.add_argument("--match", required=True, help="regex pattern to match title/body")
    p_bulk.set_defaults(func=cmd_bulk_set)

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    p_reg = sub.add_parser("register")
    p_reg.add_argument("name")
    p_reg.add_argument("--display", help="display name")
    p_reg.add_argument("--notes", help="notes")
    p_reg.set_defaults(func=cmd_register)

    p_ren = sub.add_parser("rename")
    p_ren.add_argument("old")
    p_ren.add_argument("new")
    p_ren.set_defaults(func=cmd_rename)

    args = p.parse_args()
    rc = args.func(args)
    sys.exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
