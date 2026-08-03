#!/usr/bin/env python3
"""
seed_prompt_quality_board.py — populate the prompt-quality Kanban board
with one ticket per bad-skill finding (from the latest scorecard).

Idempotent: skips tasks that already exist (matched by title).

Usage:
    python3 seed_prompt_quality_board.py --findings /tmp/loop-2-bottom25.json
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path('/root/.hermes/kanban/boards/prompt-quality/kanban.db')

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--findings', required=True)
    args = ap.parse_args()

    findings = json.loads(Path(args.findings).read_text())
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT,
        assignee TEXT, status TEXT NOT NULL, priority INTEGER DEFAULT 0,
        created_by TEXT, created_at INTEGER NOT NULL,
        started_at INTEGER, completed_at INTEGER,
        workspace_kind TEXT DEFAULT 'scratch', workspace_path TEXT,
        branch_name TEXT, project_id TEXT, claim_lock TEXT,
        claim_expires INTEGER, tenant TEXT, result TEXT,
        idempotency_key TEXT, consecutive_failures INTEGER DEFAULT 0,
        worker_pid INTEGER, last_failure_error TEXT,
        max_runtime_seconds INTEGER, last_heartbeat_at INTEGER,
        current_run_id INTEGER, workflow_template_id TEXT,
        current_step_key TEXT, skills TEXT,
        model_override TEXT, provider_override TEXT,
        max_retries INTEGER, goal_mode INTEGER DEFAULT 0,
        goal_max_turns INTEGER, session_id TEXT,
        block_kind TEXT, block_recurrences INTEGER DEFAULT 0
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')

    now = int(time.time())
    created = 0
    skipped = 0
    for f in findings:
        skill_name = f['skill']
        cats = f['categories']
        weakest_cat, weakest_info = min(cats.items(), key=lambda kv: kv[1]['score'])
        title = f"Improve skill: {skill_name} ({f['total']}/100 → target 80+)"
        # idempotency: skip if same title already exists
        cur = con.execute('SELECT id FROM tasks WHERE title=?', (title,))
        if cur.fetchone():
            skipped += 1
            continue
        # build body with the 4-category scorecard + suggested actions
        body_lines = [
            f"## Skill audit finding",
            "",
            f"- **Skill**: `{skill_name}`",
            f"- **Path**: `{f['path']}`",
            f"- **Current score**: {f['total']}/100 ({f['tier']})",
            f"- **Target**: 80/100 (acceptable tier)",
            "",
            "### Category scores",
            "",
            "| Category | Score | Notes |",
            "|----------|-------|-------|",
        ]
        for cat, info in cats.items():
            body_lines.append(f"| {cat} | {info['score']}/25 | {'; '.join(info['notes'])} |")
        body_lines += [
            "",
            f"**Weakest category:** {weakest_cat} ({weakest_info['score']}/25)",
            "",
            "### Suggested actions",
            "",
            "1. Read `~/.hermes/skills/prompt-quality-rubric/SKILL.md` to understand the 4-category rubric.",
            "2. Read `~/.REPLACE_ME.md` for few-shot patterns.",
            "3. Re-score the original first, then craft a targeted rewrite for the weakest category.",
            "4. Re-score the rewrite. Accept only if delta >= +10 AND no category regressed.",
            "5. Apply via `patch` or `skill_manage(action='edit')`. Commit by hand.",
            "6. Move this card to done; the next `skill-quality-audit` cron will verify.",
            "",
            "### Pipeline",
            "",
            "- Staged diff: `/root/.hermes/skills/prompt-improvement-loop/.loop-state/staged-review.diff`",
            "- Loop manifest: `/root/.hermes/skills/prompt-improvement-loop/.loop-state/prompt-improvement-loop.json`",
            "- Score history: `/root/.hermes/skills/prompt-improvement-loop/.loop-state/score-history.json`",
            "",
            "_Auto-seeded by `seed_prompt_quality_board.py` on the 2026-07-29 cursor-loop integration pass._",
        ]
        task_id = f"pq-{skill_name.replace('/', '-')}"
        priority = max(0, 50 - f['total'])  # worse score = higher priority
        con.execute(
            'INSERT INTO tasks (id, title, body, status, priority, created_by, created_at, workspace_kind) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (task_id, title, '\n'.join(body_lines), 'todo', priority, 'skill-quality-audit', now, 'scratch'),
        )
        created += 1
    con.commit()
    con.close()
    print(f'Created: {created}, Skipped (already exists): {skipped}, DB: {DB_PATH}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
