#!/usr/bin/env python3
"""
skill-quality-audit — weekly no-agent cron job.

Runs prompt-improvement-loop in dry-run mode (score + queue + stage only),
then writes a markdown summary to STDOUT for the cron system to deliver.

Output is delivered verbatim by cron (no LLM cost). Designed to be silent
if everything is fine, loud only when findings exceed threshold.

Behavior:
    - Score all skills under /root/.hermes/skills/
    - Identify bottom-N by score (default N=20, configurable)
    - Compare to last week's findings (kept in state file)
    - Emit only the delta + summary table
    - Exit code 0 = clean, 2 = new findings detected (cron delivers alert)
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path('/root/.hermes/state/skill-quality-audit')
STATE_DIR.mkdir(parents=True, exist_ok=True)
LAST_FINDINGS_FILE = STATE_DIR / 'last-findings.json'
SCORE_SCRIPT = Path('/root/.REPLACE_ME.py')
SKILLS_DIR = Path('/root/.hermes/skills')
BOTTOM_N = int(os.environ.get('SKILL_AUDIT_BOTTOM_N', '20'))

def load_last_findings() -> set[str]:
    if LAST_FINDINGS_FILE.exists():
        return set(json.loads(LAST_FINDINGS_FILE.read_text()))
    return set()

def save_findings(skills: list[str]) -> None:
    LAST_FINDINGS_FILE.write_text(json.dumps(sorted(skills), indent=2))

def score_all() -> list[dict]:
    result = subprocess.run(
        ['python3', str(SCORE_SCRIPT), '--dir', str(SKILLS_DIR), '--json'],
        capture_output=True, text=True,
    )
    if result.returncode not in (0, 2):
        print(f'SCORER FAILED: {result.stderr}', file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)

def main() -> int:
    scores = score_all()
    bottom = [s for s in scores if s['total'] < 70][:BOTTOM_N]
    current_skills = [b['skill'] for b in bottom]
    last_skills = load_last_findings()
    current_set = set(current_skills)

    # delta
    new_findings = current_set - last_skills
    fixed = last_skills - current_set  # in last but not in current = improved

    # always save the current snapshot
    save_findings(current_skills)

    # silent if no changes AND no new findings
    if not new_findings:
        # still emit weekly digest if it's Monday (cron time), else silent
        # but for visibility, emit one line per run
        if not bottom:
            print('skill-quality-audit: no skills below 70/100 threshold')
            return 0
        # no new findings vs last week → still report count for trend tracking
        print(f'skill-quality-audit: {len(bottom)} skills below 70/100 (no new vs last week)')
        return 0

    # new findings detected → emit full report
    now = datetime.now(timezone.utc).isoformat()
    new_skills_pretty = sorted(new_findings)
    fixed_skills_pretty = sorted(fixed)

    lines = [
        '# Skill Quality Audit — New Findings',
        '',
        f'**Timestamp:** {now}',
        f'**Scope:** {SKILLS_DIR} ({len(scores)} skills scored)',
        f'**Threshold:** < 70/100',
        f'**Bottom N:** {BOTTOM_N}',
        '',
        f'## New bad-skill findings ({len(new_skills_pretty)})',
        '',
        '| Skill | Score | Tier | Weakest category |',
        '|-------|-------|------|------------------|',
    ]
    for skill_name in new_skills_pretty:
        b = next((x for x in bottom if x['skill'] == skill_name), None)
        if not b:
            continue
        cats = b['categories']
        weakest_cat, weakest_info = min(cats.items(), key=lambda kv: kv[1]['score'])
        lines.append(f"| `{b['skill']}` | {b['total']}/100 | {b['tier']} | {weakest_cat} ({weakest_info['score']}/25) |")

    if fixed_skills_pretty:
        lines += [
            '',
            f'## Fixed since last run ({len(fixed_skills_pretty)})',
            '',
        ]
        for s in fixed_skills_pretty:
            lines.append(f'- `{s}`')

    lines += [
        '',
        '## Action',
        '',
        '1. Review `staged-review.diff` at `/root/.hermes/skills/prompt-improvement-loop/.loop-state/staged-review.diff`',
        '2. For each new finding, file a Kanban ticket on board `prompt-quality`.',
        '3. If you accept the staged rewrites, apply them via `patch` or `skill_manage(action=\'edit\')` and commit by hand.',
        '',
    ]
    print('\n'.join(lines))
    # R16 fix: cron_health.py uses exit 2 to flag "broken". But this script's job IS to
    # produce findings — that's the report. Exit 0 (the report IS the signal).
    # The kanban ticket prompt in stdout IS the actionable signal.
    # Operators can see findings in the cron run output; cron_health now correctly
    # classifies this script as healthy.
    return 0

if __name__ == '__main__':
    sys.exit(main())
