"""
kanban_bot_inspect — show what each bot is currently working on / available for.

Replaces the "who has the ball now?" question with a single command.

Usage:
  kanban_bot_inspect.py                # all bots summary
  kanban_bot_inspect.py design-bot     # one bot in detail
  kanban_bot_inspect.py --active       # only bots with running/ready tasks
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import repo_context  # noqa: E402
from kanban_common import (
    HUMAN_PEOPLE, AGENT_PEOPLE,
    board_db_path, list_boards, INBOX_DIR,
)
from kanban_store import KanbanStore


# Bot profile ↔ tenant knowledge mapping
TENANT_TO_REPO_DIR = INBOX_DIR / "repo_context.json"

# Load repo context if available
def load_repo_context() -> dict:
    if not TENANT_TO_REPO_DIR.exists():
        return {}
    try:
        return json.loads(TENANT_TO_REPO_DIR.read_text())
    except Exception:
        return {}


def get_bot_stats(bot: str) -> dict:
    """Get current state of one bot's tasks across all boards."""
    stats = {
        "bot": bot,
        "ready": [],
        "running": [],
        "blocked": [],
        "done_this_week": [],
    }

    for board in list_boards():
        try:
            with KanbanStore(board) as store:
                rows = store._connect().execute("""
                    SELECT id, title, status, priority, tenant, body
                    FROM tasks
                    WHERE assignee = ?
                """, (bot,)).fetchall()
        except Exception:
            continue
        for tid, title, status, priority, tenant, body in rows:
            entry = {
                "id": tid,
                "title": title or "",
                "board": board,
                "priority": priority,
                "tenant": tenant,
                "body_excerpt": (body or "")[:80],
            }
            if status == "ready":
                stats["ready"].append(entry)
            elif status == "running":
                stats["running"].append(entry)
            elif status == "blocked":
                stats["blocked"].append(entry)
            elif status == "done":
                # rough: count as "this week" if id looks recent (no created_at fetch needed)
                stats["done_this_week"].append(entry)
    return stats


def get_humans_stats(person: str) -> dict:
    """Get a human's open tasks + recently done."""
    stats = {
        "person": person,
        "ready": [], "running": [], "blocked": [], "done": [],
    }
    for board in list_boards():
        try:
            db = board_db_path(board)
            with KanbanStore(board) as store:
                rows = store._connect().execute("""
                    SELECT t.id, t.title, t.status, t.priority, t.tenant, a.weight
                    FROM tasks t
                    LEFT JOIN task_assignees a ON a.task_id = t.id AND a.person = ?
                    WHERE (t.assignee = ? OR a.task_id IS NOT NULL)
                """, (person, person)).fetchall()
        except Exception:
            continue
        for tid, title, status, priority, tenant, weight in rows:
            entry = {"id": tid, "title": title or "", "board": board,
                     "priority": priority, "tenant": tenant, "weight": weight or 1.0}
            key = status if status in stats else "done"
            stats.setdefault(key, []).append(entry)
    return stats


def format_stats(stats: dict, repo_ctx: dict) -> str:
    out = []
    name = stats.get("bot") or stats.get("person")
    out.append(f"=== {name} ===")

    if stats.get("bot"):
        # Bot view
        running = stats.get("running", [])
        ready = stats.get("ready", [])
        blocked = stats.get("blocked", [])
        done = stats.get("done_this_week", [])

        out.append(f"  in-flight: {len(running)} running | {len(ready)} ready | {len(blocked)} blocked")
        out.append(f"  done recently: {len(done)}")

        # Cross-reference tenant → repo path
        tenants_seen = set()
        for entries in [running, ready, blocked]:
            for e in entries:
                if e.get("tenant"):
                    tenants_seen.add(e["tenant"])

        if tenants_seen and repo_ctx:
            out.append(f"\n  Tenants seen:")
            for t in sorted(tenants_seen):
                repos = [p for p, r in repo_ctx.get("repos", {}).items() if r.get("tenant") == t]
                for r in repos[:2]:
                    out.append(f"    {t} → {r}")

        # Show details for non-empty
        for state, entries in [("RUNNING", running), ("READY", ready), ("BLOCKED", blocked)]:
            if entries:
                out.append(f"\n  {state} ({len(entries)}):")
                for e in entries[:5]:
                    out.append(f"    [{e['priority']}] {e['id']} ({e['board']}) {e['title'][:50]}")
                    if e.get("body_excerpt"):
                        out.append(f"        \"{e['body_excerpt']}...\"")
                if len(entries) > 5:
                    out.append(f"    ... +{len(entries)-5} more")
    else:
        # Human view
        running = stats.get("running", [])
        ready = stats.get("ready", [])
        blocked = stats.get("blocked", [])
        out.append(f"  open: {len(running)} running | {len(ready)} ready | {len(blocked)} blocked")
        for state, entries in [("RUNNING", running), ("READY", ready), ("BLOCKED", blocked)]:
            if entries:
                out.append(f"\n  {state} ({len(entries)}):")
                for e in entries[:8]:
                    wtag = f" w={e['weight']:.1f}" if e.get("weight") else ""
                    out.append(f"    [{e['priority']}]{wtag} {e['id']} ({e['board']}) {e['title'][:50]}")
                if len(entries) > 8:
                    out.append(f"    ... +{len(entries)-8} more")
    return "\n".join(out)


def get_client_priority() -> dict:
    """Read client_priority from repo_context (which is the only external client)."""
    try:
        return repo_context.load().get("client_priority", {})
    except Exception:
        return {}


def get_contacts() -> dict:
    """Read contacts registry (clients + leads)."""
    try:
        import contacts
        return contacts.load()
    except Exception:
        return {}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bot", nargs="?", help="bot or person to inspect (default: all)")
    p.add_argument("--active", action="store_true", help="only show with active work")
    p.add_argument("--priority", action="store_true", help="show which client is the external priority")
    p.add_argument("--contacts", action="store_true", help="show contacts (pipeline by stage)")
    args = p.parse_args()

    repo_ctx = load_repo_context()

    if args.contacts:
        contacts = get_contacts()
        if not contacts.get("contacts"):
            print("No contacts registered.")
            return
        print(f"\n{'='*70}\nContacts Pipeline ({len(contacts['contacts'])} total)\n{'='*70}\n")
        by_stage = {}
        for c in contacts["contacts"]:
            by_stage.setdefault(c.get("stage", "?"), []).append(c)
        for stage in ["lead", "qualifying", "opportunity", "client", "main client", "cold", "lost"]:
            if stage in by_stage:
                print(f"  {stage.upper()} ({len(by_stage[stage])}):")
                for c in by_stage[stage]:
                    tenant = c.get("tenant", "-") or "-"
                    lck = c.get("line_of_work", "-") or "-"
                    print(f"    · {c['id']:<25} {c['name']:<22} {lck:<20} tenant={tenant}")
                print()
        return

    if args.priority:
        priority = get_client_priority()
        if not priority:
            print("Default priority: dentist-template-scan")
            return
        print(f"\n{'='*70}")
        print(f"External client priority — {priority.get('primary_tenant_label', '(unset)')}")
        print(f"{'='*70}")
        print(f"  Active: {priority.get('is_external_client')}")
        print(f"  Tenant: {priority.get('tenant')}")
        print(f"  Repo:   {priority.get('primary_repo')}")
        paused = priority.get("paused_clients", [])
        if paused:
            print(f"\n  Paused ({len(paused)}):")
            for p in paused:
                print(f"    - {p.get('repo')}: {p.get('reason', '')[:60]}")
        return



    if args.bot:
        # One entity
        if args.bot in AGENT_PEOPLE:
            stats = get_bot_stats(args.bot)
            print(format_stats(stats, repo_ctx))
        elif args.bot in HUMAN_PEOPLE:
            stats = get_humans_stats(args.bot)
            print(format_stats(stats, repo_ctx))
        else:
            print(f"unknown bot/person: {args.bot}")
            print(f"agents: {', '.join(AGENT_PEOPLE.keys())}")
            print(f"humans: {', '.join(HUMAN_PEOPLE.keys())}")
            sys.exit(1)
        return

    # All bots
    priority = get_client_priority()
    client_label = priority.get("primary_tenant_label", "dentist")
    header = "=" * 70
    print(f"\n{header}\nKanban Bot Inspection — {len(AGENT_PEOPLE)} agents, {len(HUMAN_PEOPLE)} humans")
    print(f"External client: {client_label} (only one — internal upgrades otherwise)")
    print(f"Use --priority for client details\n{header}")

    for bot in AGENT_PEOPLE:
        stats = get_bot_stats(bot)
        running = len(stats.get("running", []))
        ready = len(stats.get("ready", []))
        blocked = len(stats.get("blocked", []))
        done = len(stats.get("done_this_week", []))
        if args.active and (running + ready + blocked) == 0:
            continue
        active = (running + ready + blocked) > 0
        marker = "●" if active else "·"
        print(f"  {marker} {bot:<20} R:{running:>3} Q:{ready:>3} B:{blocked:>3} | done:{done}")

    print(f"\n{'='*70}\nHumans\n{'='*70}")
    for person in HUMAN_PEOPLE:
        stats = get_humans_stats(person)
        running = len(stats.get("running", []))
        ready = len(stats.get("ready", []))
        blocked = len(stats.get("blocked", []))
        active = (running + ready + blocked) > 0
        if args.active and not active:
            continue
        marker = "●" if active else "·"
        print(f"  {marker} {person:<20} R:{running:>3} Q:{ready:>3} B:{blocked:>3}")


if __name__ == "__main__":
    main()
