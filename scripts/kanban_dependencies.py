#!/usr/bin/env python3
"""
kanban_dependencies — manage task dependencies (links) and show critical path.

Tasks form a DAG via the `task_links(parent_id, child_id)` table.
A parent must be done before the child can be claimed.

Uses the typed persistence layer (kanban_store.py) for all DB operations.

Usage:
  kanban_dependencies.py --board ivan-tasks link <parent_id> <child_id>
  kanban_dependencies.py --board ivan-tasks path           # show critical path
  kanban_dependencies.py --board ivan-tasks tree           # show full dependency tree
  kanban_dependencies.py --board ivan-tasks deps           # show all dependencies
"""
import argparse
import sqlite3
import sys
from collections import defaultdict, deque
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


# ---- Helpers ----

def _reaches(start: str, target: str, edges: set) -> bool:
    """BFS: does `start` reach `target` along edges? Used for cycle detection."""
    if start == target:
        return True
    visited = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for (p, c) in edges:
            if p == node:
                if c == target:
                    return True
                queue.append(c)
    return False


def _print_tree(node, children, tasks, prefix=""):
    """Print a tree starting at node."""
    title = tasks.get(node, "(unknown)")
    print(f"{prefix}{node} {title[:50]}")
    for child in children.get(node, []):
        _print_tree(child, children, tasks, prefix + "  ")


# ---- Commands ----

def cmd_link(args):
    """Create a dependency: parent must be done before child."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        # Validate both tasks exist
        if not store.get_task(args.parent_id):
            print(f"ERROR: parent task {args.parent_id} not found", file=sys.stderr)
            return 1
        if not store.get_task(args.child_id):
            print(f"ERROR: child task {args.child_id} not found", file=sys.stderr)
            return 1
        # Load all edges for cycle detection
        cur = store._connect().execute("SELECT parent_id, child_id FROM task_links")
        edges = set(cur.fetchall())
        # Check: would adding this create a cycle?
        if args.child_id in (p for (p, c) in edges):
            # Note: existing edge says child has its own parents. Check indirectly.
            pass
        if _reaches(args.child_id, args.parent_id, edges):
            print(f"ERROR: would create cycle (child {args.child_id} already reaches parent {args.parent_id})", file=sys.stderr)
            return 1
        # Check if edge already exists
        if (args.parent_id, args.child_id) in edges:
            print(f"  Edge already exists: {args.parent_id} → {args.child_id}")
            return 0
        # Insert
        try:
            store._connect().execute(
                "INSERT INTO task_links (parent_id, child_id) VALUES (?, ?)",
                (args.parent_id, args.child_id),
            )
            store._connect().commit()
            print(f"✓ Linked {args.parent_id} → {args.child_id}")
        except sqlite3.IntegrityError:
            print(f"  Edge already exists", file=sys.stderr)
    return 0


def cmd_path(args):
    """Show critical path (longest dependency chain)."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        edges = store._connect().execute("SELECT parent_id, child_id FROM task_links").fetchall()
        cur = store._connect().execute("SELECT id, title FROM tasks")
        tasks = {tid: title for tid, title in cur.fetchall()}
        # Build adjacency
        children = defaultdict(list)
        parents = defaultdict(list)
        for p, c in edges:
            children[p].append(c)
            parents[c].append(p)
        # Find longest path from any leaf
        all_ids = set(tasks.keys())
        leaves = {tid for tid in all_ids if not children.get(tid)}
        if not leaves:
            print("No tasks or no dependencies.")
            return 0
        # For each leaf, find max path to it
        # Use memoized DFS
        memo = {}
        def longest_to(tid):
            if tid in memo:
                return memo[tid]
            ps = parents.get(tid, [])
            if not ps:
                memo[tid] = (1, [tid])
            else:
                best_len, best_path = 0, []
                for p in ps:
                    l, path = longest_to(p)
                    if l > best_len:
                        best_len = l
                        best_path = path
                memo[tid] = (best_len + 1, best_path + [tid])
            return memo[tid]
        best = (0, [])
        for leaf in leaves:
            l, path = longest_to(leaf)
            if l > best[0]:
                best = (l, path)
        length, path = best
        print(f"Critical path ({length} tasks):")
        for tid in path:
            print(f"  {tid} {tasks.get(tid, '(unknown)')[:60]}")
    return 0


def cmd_tree(args):
    """Show full dependency tree from root tasks."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        edges = store._connect().execute("SELECT parent_id, child_id FROM task_links").fetchall()
        cur = store._connect().execute("SELECT id, title FROM tasks")
        tasks = {tid: title for tid, title in cur.fetchall()}
        children = defaultdict(list)
        for p, c in edges:
            children[p].append(c)
        # Roots = tasks with no parents
        all_in_links = {c for (p, c) in edges}
        roots = [tid for tid in tasks if tid not in all_in_links]
        if not roots:
            print("No tasks or no dependencies.")
            return 0
        for root in sorted(roots):
            _print_tree(root, children, tasks)
    return 0


def cmd_deps(args):
    """List all dependencies."""
    with KanbanStore(args.board) as store:
        store.ensure_schema()
        cur = store._connect().execute(
            "SELECT tl.parent_id, p.title, tl.child_id, c.title, c.status "
            "FROM task_links tl "
            "JOIN tasks p ON p.id = tl.parent_id "
            "JOIN tasks c ON c.id = tl.child_id "
            "ORDER BY tl.parent_id, tl.child_id"
        )
        rows = cur.fetchall()
        if not rows:
            print(f"No dependencies on {args.board}")
            return 0
        print(f"Dependencies on {args.board}:")
        for parent_id, parent_title, child_id, child_title, child_status in rows:
            print(f"  {parent_id} {parent_title[:35]}")
            print(f"    → {child_id} [{child_status}] {child_title[:35]}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_link = sub.add_parser("link")
    p_link.add_argument("parent_id")
    p_link.add_argument("child_id")
    p_link.set_defaults(func=cmd_link)

    sub.add_parser("path").set_defaults(func=cmd_path)
    sub.add_parser("tree").set_defaults(func=cmd_tree)
    sub.add_parser("deps").set_defaults(func=cmd_deps)

    args = p.parse_args()
    rc = args.func(args)
    sys.exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
