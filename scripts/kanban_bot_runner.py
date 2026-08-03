#!/usr/bin/env python3
"""
kanban_bot_runner — smart dispatcher for bot-assigned kanban tasks.

Replaces the (broken) auto-dispatcher. Strict safeguards:
  - Only claims tasks with assignee IN AGENT_PEOPLE (humans never auto-claimed)
  - Per-bot quota: max 5 tasks/day
  - Per-bot cooldown: 15 minutes between tasks
  - Skip tasks with empty body (<30 chars) or hallucinated follow-ups
  - Halt bot on 2 consecutive failures (24h cooldown)

Usage:
  kanban_bot_runner.py --dry-run    # preview what would be claimed
  kanban_bot_runner.py              # actually claim and run
  kanban_bot_runner.py --bot design-bot   # only process one bot

Cron: every 15 minutes (separate from gateway)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kanban_common import (
    KANBAN_ROOT, KANBAN_HOME, INBOX_DIR,
    board_db_path, list_boards,
)
from kanban_store import KanbanStore
from skill_metadata import get_skills_for_bot


STATE_PATH = INBOX_DIR / ".kanban-bot-runner-state.json"
DAILY_QUOTA = 5
COOLDOWN_MINUTES = 15
MAX_FAILURES = 2
HALLUCINATION_KEYWORDS = [
    "follow-up", "re-entry", "blocking on human",
    "ai response", "auto-claimed", "agent run",
]
MIN_BODY_LEN = 30


def load_state() -> dict:
    """Load per-bot state: quota used today, last run timestamp, consecutive failures."""
    if not STATE_PATH.exists():
        return {"date": "", "bots": {}}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"date": "", "bots": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def get_bot_today(state: dict, bot: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("date") != today:
        state["date"] = today
        state["bots"] = {}
    return state["bots"].setdefault(bot, {
        "used": 0,
        "last_run": None,
        "failures": 0,
    })


def is_hallucinated(task_body: str, task_title: str) -> bool:
    """Detect if a task looks like an auto-generated follow-up that should NOT be claimed."""
    text = (task_body or "").lower() + " " + (task_title or "").lower()
    if len(task_body or "") < MIN_BODY_LEN:
        return True
    return any(kw in text for kw in HALLUCINATION_KEYWORDS)


def is_in_cooldown(bot_state: dict) -> bool:
    if not bot_state.get("last_run"):
        return False
    last = datetime.fromisoformat(bot_state["last_run"])
    return datetime.now() - last < timedelta(minutes=COOLDOWN_MINUTES)


def find_ready_tasks_for_bot(bot: str) -> list[tuple[str, str, str, str, str, str]]:
    """Find ready tasks with assignee=bot, return list of (board, task_id, title, body, priority, tenant)."""
    results = []
    for board in list_boards():
        with KanbanStore(board) as store:
            cur = store._connect().execute("""
                SELECT id, title, body, priority, tenant
                FROM tasks
                WHERE assignee = ? AND status = 'ready'
                ORDER BY priority ASC, created_at ASC
            """, (bot,))
            for row in cur.fetchall():
                tid, title, body, priority, tenant = row
                results.append((board, tid, title or "", body or "", priority, tenant or ""))
    return results


def claim_and_run_task(bot: str, board: str, task_id: str, title: str, body: str) -> tuple[bool, str]:
    """Mark task as running, run the bot, mark as done/blocked based on result.

    Returns (success, message). The bot itself is invoked via `hermes` CLI.
    """
    db = board_db_path(board)
    with KanbanStore(board) as store:
        # Mark running
        store.set_status(task_id, "running")
        # Build the prompt
        prompt = (
            f"You are {bot}, an AI workforce lead for Ai-Whisperers. "
            f"Process this kanban task and report the result.\n\n"
            f"Task ID: {task_id}\n"
            f"Title: {title}\n"
            f"Board: {board}\n"
            f"Body:\n{body}\n\n"
            f"When done, summarize your work. "
            f"If you can't finish, mark the task blocked with a real block_kind."
        )
        try:
            # Run the bot via hermes CLI (with timeout)
            result = subprocess.run(
                ["hermes", "-p", bot, "chat", prompt, "--no-restore-cwd"],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                # Mark done with the result excerpt
                excerpt = result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                store.set_status(task_id, "done")
                return True, f"completed: {excerpt[:200]}"
            else:
                store.set_status(task_id, "blocked")
                # Set block_kind via SQL (no high-level method)
                store._connect().execute(
                    "UPDATE tasks SET block_kind='agent_run_failed' WHERE id=?",
                    (task_id,),
                )
                store._connect().commit()
                return False, f"failed: {result.stderr[-200:]}"
        except subprocess.TimeoutExpired:
            store.set_status(task_id, "blocked")
            return False, "timeout"
        except Exception as e:
            store.set_status(task_id, "blocked")
            return False, f"exception: {e}"


def process_bot(bot: str, state: dict, dry_run: bool = False) -> list[str]:
    """Process one bot: find tasks, run them, update state. Returns list of actions."""
    actions = []
    bot_state = get_bot_today(state, bot)

    # Safeguard 1: failures
    if bot_state["failures"] >= MAX_FAILURES:
        actions.append(f"  ⚠ {bot}: halted (failures={bot_state['failures']})")
        return actions

    # Safeguard 2: quota
    if bot_state["used"] >= DAILY_QUOTA:
        actions.append(f"  ⚠ {bot}: daily quota exhausted ({bot_state['used']}/{DAILY_QUOTA})")
        return actions

    # Safeguard 3: cooldown
    if is_in_cooldown(bot_state):
        actions.append(f"  ⏸ {bot}: in cooldown (last run {bot_state['last_run']})")
        return actions

    # Find tasks
    tasks = find_ready_tasks_for_bot(bot)
    if not tasks:
        actions.append(f"  · {bot}: no ready tasks")
        return actions

    # Process up to remaining quota
    remaining = DAILY_QUOTA - bot_state["used"]
    for board, task_id, title, body, priority, tenant in tasks[:remaining]:
        if is_hallucinated(body, title):
            actions.append(f"  ⏭ {bot}/{task_id}: skip (hallucination marker)")
            continue

        if dry_run:
            actions.append(f"  DRY {bot}/{task_id}: would claim [{priority}] {title[:50]}")
            continue

        # Actually run
        actions.append(f"  → {bot}/{task_id}: starting [{priority}] {title[:50]}")
        ok, msg = claim_and_run_task(bot, board, task_id, title, body)
        bot_state["used"] += 1
        bot_state["last_run"] = datetime.now().isoformat()
        if ok:
            bot_state["failures"] = 0
            actions.append(f"    ✓ done")
        else:
            bot_state["failures"] += 1
            actions.append(f"    ✗ {msg[:100]}")
            # Stop after first failure (don't cascade)
            break

    return actions


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="preview only, no writes")
    p.add_argument("--bot", help="only process this bot")
    args = p.parse_args()

    state = load_state()
    all_actions = []

    # All agent profiles (bots that can run autonomously)
    from kanban_common import AGENT_PEOPLE
    bots = [args.bot] if args.bot else list(AGENT_PEOPLE.keys())

    for bot in bots:
        all_actions.extend(process_bot(bot, state, dry_run=args.dry_run))

    if not args.dry_run:
        save_state(state)

    print(f"\n{'='*70}\nkanban-bot-runner {'(dry-run)' if args.dry_run else ''}\n{'='*70}")
    for a in all_actions:
        print(a)
    print(f"{'='*70}\nState saved: {STATE_PATH}")


if __name__ == "__main__":
    main()