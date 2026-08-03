# Hermes + Cursor Loop — Round 5: Autonomous-Running Plan

**Date:** 2026-07-29
**Status:** Round 4 complete. Round 5 = "make it run constantly and autonomously on all projects."

---

## What we have so far

### From the original `cursor_20260628-2.zip` (620 files, full Eneve playbook)

| Round | What was internalized | Files |
|---|---|---|
| **R1** | First ~40 files; basics: rubric, loop, lint, doc-standard | 8 skills |
| **R3** | Deep re-read: FORBIDDEN list, 3-tier triage, New/Tracked/Partial dedup, per-repo findings registry | (semantic improvements to R1) |
| **R4** | Orchestrators + meta + ports: 5 orchestrators, 6 Eneve prompts, 2 meta skills, 19 collections, 11 scripts | 13 new skills + 11 scripts |

### Hermes current state (post-R4)

- **205 skills** (12.6% with full schema, 7.3% with `triggers`, 0.5% with `alwaysApply`)
- **76 scripts** in `~/.hermes/scripts/`
- **19 collections** in `~/.hermes/skills/collections/` (0 orphans, 0 ghosts, 0 duplicates)
- **50 cron jobs** running
- **Various Kanban boards** (prompt-quality, client-deploy, dentist-tasks, etc.)
- **Memory** at 98% — well-utilized

### What Eneve had that we **don't** yet

| Eneve pattern | Hermes status |
|---|---|
| 5 orchestrator skills | ✅ Round 4 built |
| 6 ported Eneve prompts | ✅ Round 4 built |
| Structured frontmatter schema | ✅ Round 4 built |
| 3 invocation strategies | ✅ Round 4 built |
| 19 collections | ✅ Round 4 built |
| Extraction/condense pipeline | ✅ Round 4 built (3 scripts) |
| 5-phase skill authoring | ✅ Round 4 built |
| **Orchestrators wire to each other** | ❌ **Not yet** |
| **Per-repo autonomous tick** | ❌ **Not yet** |
| **Project discovery + auto-run** | ❌ **Not yet** |
| **Health scoring + auto-remediation** | ❌ **Not yet** |
| **Loop-back feedback (skill improves from use)** | ❌ **Not yet** |
| **Cross-repo aggregation dashboard** | ❌ **Not yet** |

---

## The 12 gaps preventing fully autonomous operation

### Gap 1: Orchestrators don't call each other

`delivery-prep` mentions `quality-gate` and `coverage-runner` but doesn't
**actually invoke them**. Each orchestrator is a standalone script.
**Fix:** build `pipeline_run.py` that chains orchestrators into a single
workflow.

### Gap 2: No per-repo "tick" loop

Eneve runs `validate-pre-merge.ps1` per-repo. We have a one-off
`pre_merge_check.py` but no loop that runs on every repo in a registered
list. **Fix:** `repo_tick.py` — discover all repos, run quality-gate on
each, log findings.

### Gap 3: No project discovery

Our 20+ repos (`psycology`, `nexa-paraguay`, `paragu-ai-platform`,
`dentist-repo`, etc.) are not registered anywhere. **Fix:** a
`~/.hermes/state/projects.yaml` registry with auto-discovery.

### Gap 4: No health scoring

Eneve has a multi-dimensional CRAP score; we have `coverage-runner`
and `complexity_gate.py` but no unified health score. **Fix:** a
`repo_health.py` that combines: coverage % + complexity + findings
count + branch staleness + age.

### Gap 5: No auto-remediation

Quality-gate flags problems but doesn't fix them. **Fix:** wire
`simplify-code` (existing 4-agent cleanup) + `coverage-runner` to
generate missing tests, then re-run.

### Gap 6: No loop-back feedback

When a skill gets used 100+ times, it should auto-validate. When it
gets used 0 times for 30 days, it should be flagged as dead. **Fix:**
`skill_usage_tracker.py` that counts skill loads via the `skill_view`
log.

### Gap 7: No cross-repo dashboard

Hard to see "is everything green across all projects." **Fix:** a
`repo_dashboard.py` that aggregates per-repo health into a single table.

### Gap 8: No proactive project creation

When you say "build a new client site," we don't auto-scaffold the
project with quality-gate hooks pre-installed. **Fix:** a
`new_project.py` that copies the Paragu-AI template + registers the
project in the manifest.

### Gap 9: No skill-of-the-week / loop improvement

The Eneve loop runs continuously. Our cron runs `skill-quality-audit`
weekly but doesn't **act on findings**. **Fix:** a `loop_continuity.py`
that runs `manage-playbook` cycle after the audit.

### Gap 10: No integration with Kanban bot runner

Our `kanban-bot-runner` cron picks up tasks but doesn't trigger the
new orchestrators. **Fix:** link bot tasks to orchestrator invocations.

### Gap 11: No "everything fine" baseline

We can't tell if today's run is "worse than yesterday" or "noisy
normal." **Fix:** differential snapshots in
`~/.hermes/state/health-snapshots/`.

### Gap 12: No single command to "run everything"

There's no `hermes run all` that fires every autonomous tick. **Fix:**
a `cron_orchestrator.py` that runs the full pipeline.

---

## The Round 5 ship list (12 items)

### Tier 1 — Wire the orchestrators (P0)

**Effort:** 4 hours
**Value:** Closes gap 1. Makes the orchestrators actually orchestrate.

Build `~/.hermes/scripts/pipeline_run.py` that chains:

```bash
python3 ~/.hermes/scripts/pipeline_run.py --tier pre-commit
# → quality-gate → coverage-runner → pre_merge_check

python3 ~/.hermes/scripts/pipeline_run.py --tier release
# → quality-gate → coverage-runner → delivery-prep → changelog-releaser

python3 ~/.hermes/scripts/pipeline_run.py --tier ticket-close
# → quality-gate → coverage-runner → ticket-lifecycle close
```

### Tier 2 — Project registry + auto-discovery (P1)

**Effort:** 3 hours
**Value:** Closes gap 3. Single source of truth for "what projects do we have."

Build `~/.hermes/state/projects.yaml`:

```yaml
projects:
  - name: psycology
    path: /root/psycology
    type: python-research
    git: https://github.com/iivana/psycology
    default_branch: master
    orchestrators: [quality-gate, coverage-runner]
    cron: weekly
  - name: paragu-ai-platform
    path: /root/paragu-ai-platform
    type: nextjs-monorepo
    git: https://github.com/iivana/paragu-ai-platform
    default_branch: main
    orchestrators: [quality-gate, coverage-runner, delivery-prep]
    cron: daily
  - name: dentist-repo
    path: /root/dentist-repo
    type: nextjs-client
    git: https://github.com/iivana/dentist-repo
    default_branch: main
    orchestrators: [quality-gate, coverage-runner, delivery-prep, doc-architecture]
    cron: daily
  # ... ~20 more
```

Plus `repo_discover.py` that scans `~/` for git repos and proposes
additions to the manifest.

### Tier 3 — Per-repo tick loop (P2)

**Effort:** 4 hours
**Value:** Closes gap 2. The autonomous "heartbeat."

Build `~/.hermes/scripts/repo_tick.py`:

```bash
python3 ~/.hermes/scripts/repo_tick.py --repo psycology
# → quality-gate → coverage-runner → log findings → alert if regression

python3 ~/.hermes/scripts/repo_tick.py --all
# → runs on every project in registry
```

Each tick:
1. Detect toolchain
2. Run quality-gate
3. Run coverage-runner
4. Run find-dead-code
5. Update `~/.hermes/state/health-snapshots/<repo>.json`
6. If regression vs last snapshot → log to findings + alert

### Tier 4 — Unified health scoring (P3)

**Effort:** 3 hours
**Value:** Closes gap 4. One number per repo.

Build `~/.hermes/scripts/repo_health.py`:

```python
score = (
    coverage_pct * 0.30 +           # 30% weight
    complexity_score * 0.20 +       # 20% weight
    findings_count_inverse * 0.20 + # 20% weight
    branch_age_score * 0.15 +       # 15% weight
    test_pass_rate * 0.15           # 15% weight
)
```

Output: 0-100 score per repo. Visible at a glance.

### Tier 5 — Cross-repo dashboard (P4)

**Effort:** 2 hours
**Value:** Closes gap 7. Operator-visible health.

Build `~/.hermes/scripts/repo_dashboard.py`:

```bash
python3 ~/.hermes/scripts/repo_dashboard.py
# Renders ASCII table of all repos + scores
```

```
| Repo                  | Score | Coverage | Findings | Last tick |
|-----------------------|-------|----------|----------|-----------|
| psycology             | 87    | 49.8%    | 0        | 2h ago    |
| paragu-ai-platform    | 92    | 78.0%    | 3        | 30m ago   |
| dentist-repo          | 94    | 84.0%    | 0        | 30m ago   |
| ... 20 more rows                                          |
```

Optional: HTML dashboard rendered to `~/.hermes/state/dashboard.html`
and served by Traefik.

### Tier 6 — Auto-remediation for low-risk findings (P5)

**Effort:** 4 hours
**Value:** Closes gap 5. The "fix it yourself" tier.

Build `~/.hermes/scripts/auto_remediate.py`:

```python
safe_categories = [
    ("lint-format", "ruff check --fix + black ."),  # Python
    ("lint-format", "npx eslint --fix + npx prettier --write"),  # Node
    ("doc-trailing", "find . -name '*.md' -exec sed -i 's/\\s*$//' {} \\;"),
    ("import-sort", "isort ."),
]

unsafe_categories = [
    "logic-fix", "security-fix", "breaking-change", "refactor"
]
```

Only `safe_categories` get auto-remediated. `unsafe` get logged as
findings.

### Tier 7 — Skill usage tracking (P6)

**Effort:** 3 hours
**Value:** Closes gap 6. Loop-back feedback.

Build `~/.hermes/scripts/skill_usage_tracker.py`:

- Tails `~/.hermes/logs/skill_view.log`
- Counts skill loads per day
- Identifies dead skills (0 loads in 30 days)
- Identifies high-use skills (>= 10 loads/week)
- Reports to `~/.hermes/state/skill-usage.json`

Cron: hourly.

### Tier 8 — Loop-back continuity (P7)

**Effort:** 2 hours
**Value:** Closes gap 9. The "watchdog" pattern.

Wire `skill-quality-audit` cron to also fire `manage-playbook/scripts/run_cycle.py`:

```bash
# After weekly skill-quality-audit fires:
python3 ~/.REPLACE_ME.py --all --bottom 10
```

This auto-improves the bottom-10 skills every week. The cron is the
"senior engineer" that ensures quality stays high.

### Tier 9 — Kanban bot runner integration (P8)

**Effort:** 4 hours
**Value:** Closes gap 10. Tickets drive orchestrators.

Tag Kanban tasks with `orchestrator:` and have the bot runner resolve
them:

```yaml
# In a Kanban task:
title: "[psycology] improve coverage to 70%"
skills: [coverage-runner]
goal: "Run coverage-runner until psycology hits 70% coverage"
```

Bot runner picks up → invokes orchestrator → reports back.

### Tier 10 — New project scaffolding (P9)

**Effort:** 3 hours
**Value:** Closes gap 8. Onboarding automation.

Build `~/.hermes/scripts/new_project.py`:

```bash
python3 ~/.hermes/scripts/new_project.py --name "client-x" --type "nextjs-pyme"
# → Clones the Paragu-AI template
# → Renames everywhere
# → Sets up quality-gate + coverage-runner + delivery-prep
# → Registers in projects.yaml
# → Sets up cron for daily tick
```

### Tier 11 — Differential snapshots (P10)

**Effort:** 2 hours
**Value:** Closes gap 11. "Is this worse than yesterday?"

Build `~/.hermes/scripts/snapshot_diff.py`:

```bash
python3 ~/.hermes/scripts/snapshot_diff.py --repo psycology
# Compares today's health to last week's
# Outputs: "coverage: -2.3% (regression)"
# Outputs: "new findings: 3 (regression)"
# Outputs: "tests passed: 47 → 47 (no change)"
```

### Tier 12 — Single "run all" command (P11)

**Effort:** 2 hours
**Value:** Closes gap 12. The "cron orchestrator."

Build `~/.hermes/scripts/cron_orchestrator.py`:

```bash
python3 ~/.hermes/scripts/cron_orchestrator.py
# Steps:
# 1. Tick all repos (repo_tick.py --all)
# 2. Update health snapshots
# 3. Find regressions (snapshot_diff.py)
# 4. Auto-remediate safe findings
# 5. Run skill-quality-audit
# 6. Run manage-playbook cycle if score regressed
# 7. Render dashboard
# 8. Send digest to Telegram/WhatsApp
```

This is the **single command** that runs everything.

---

## Total Round 5 effort

| Tier | Effort | Value |
|---|---|---|
| T1 — Wire orchestrators | 4h | ⭐⭐⭐⭐⭐ |
| T2 — Project registry | 3h | ⭐⭐⭐⭐⭐ |
| T3 — Per-repo tick | 4h | ⭐⭐⭐⭐⭐ |
| T4 — Health scoring | 3h | ⭐⭐⭐⭐ |
| T5 — Cross-repo dashboard | 2h | ⭐⭐⭐⭐ |
| T6 — Auto-remediation | 4h | ⭐⭐⭐⭐ |
| T7 — Skill usage tracking | 3h | ⭐⭐⭐ |
| T8 — Loop-back continuity | 2h | ⭐⭐⭐⭐ |
| T9 — Kanban integration | 4h | ⭐⭐⭐⭐ |
| T10 — New project scaffold | 3h | ⭐⭐⭐ |
| T11 — Differential snapshots | 2h | ⭐⭐⭐ |
| T12 — Single run-all | 2h | ⭐⭐⭐⭐⭐ |
| **Total** | **36h** | |

---

## The 3 things to ship first (max-impact, low-risk)

If we have to pick the top 3 to ship in Round 5:

1. **T2 — Project registry** (3h). One YAML file describing all our
   repos. Without this, every other tier is harder.
2. **T3 — Per-repo tick** (4h). The autonomous heartbeat. Runs on
   cron, emits health snapshots.
3. **T12 — Single run-all** (2h). One command that ties it all
   together.

**Total: 9 hours.** This gives us a working autonomous pipeline.
The other 9 tiers can be layered on top.

---

## The 5 phases of "make it work constantly and autonomously"

### Phase 1: Register (week 1)

Build `projects.yaml` with our 20 repos. Each gets:
- Path, type, branch, git URL
- Orchestrator list (default: quality-gate + coverage-runner)
- Cron frequency (default: daily)

### Phase 2: Tick (week 1)

Build `repo_tick.py` and wire it to a daily cron. Every repo gets
health-checked daily.

### Phase 3: Score (week 2)

Build `repo_health.py` and `repo_dashboard.py`. Operator sees one
view of all repos.

### Phase 4: Heal (week 2)

Build `auto_remediate.py` for safe categories. Wire it into the tick.

### Phase 5: Improve (ongoing)

Build `skill_usage_tracker.py` + loop-back continuity. Cron
auto-improves the bottom-10 skills weekly.

After Phase 5, the system is fully self-sustaining:
- Daily tick: every repo gets health-checked
- Daily auto-remediation: safe findings fixed
- Weekly skill audit: skills stay high-quality
- Weekly loop-back: bottom-10 skills get improved
- Continuous dashboard: operator sees the state

This is the **autonomous loop** Eneve has. We can match it.

---

## The 6 crons to add

```bash
# 1. Daily tick (every repo)
0 9 * * * → python3 ~/.hermes/scripts/repo_tick.py --all

# 2. Hourly skill-usage tracking
0 * * * * → python3 ~/.hermes/scripts/skill_usage_tracker.py

# 3. Daily dashboard render
0 10 * * * → python3 ~/.hermes/scripts/repo_dashboard.py --render

# 4. Weekly loop-back (Monday 7am, after skill-quality-audit)
0 7 * * 1 → python3 ~/.REPLACE_ME.py --all --bottom 10

# 5. Weekly auto-remediation (Monday 8am)
0 8 * * 1 → python3 ~/.hermes/scripts/auto_remediate.py --safe-only

# 6. Weekly cross-repo digest (Sunday 9pm)
0 21 * * 0 → python3 ~/.hermes/scripts/cron_orchestrator.py --digest
```

That's 6 new crons. Combined with the existing 50, that's 56 crons
running the full autonomous pipeline.

---

## The 1 new big idea: `cron_orchestrator.py`

The single biggest unlock is **one command that runs everything**:

```bash
python3 ~/.hermes/scripts/cron_orchestrator.py
```

This runs:
1. Per-repo tick (all repos)
2. Health scoring
3. Auto-remediation (safe)
4. Skill-usage tracking
5. Loop-back continuity
6. Dashboard render
7. Digest to Telegram/WhatsApp

If you want only **one** thing from Round 5, build this.

---

## The 4 risks to manage

1. **Auto-remediation can break things.** Always start with
   `safe_categories` only. Add `unsafe_categories` only after 30 days
   of safe-category stability.

2. **Daily tick on 20 repos = significant compute.** Each repo takes
   5-30s. Total = 100-600s. Cron should run at off-peak hour (3am).

3. **Skill usage tracking can be noisy.** Use a 30-day rolling window,
   not daily. Otherwise, vacation weeks look like dead skills.

4. **Loop-back continuity can over-improve.** Cap at bottom-10 per
   week. Don't auto-improve everything at once.

---

## The 1 question to answer

**Is the operator OK with 6 new crons?**

If yes → ship T1-T12 in priority order.
If no → ship T2+T3+T12 (project registry + tick + run-all).

The 9-hour Option B is the minimum viable autonomous pipeline. The
36-hour full option is the target.

---

## Files of record

- `~/.hermes/inbox/cursor-loop-integration.md` (Round 1)
- `~/.hermes/inbox/cursor-loop-integration-round3.md` (Round 3)
- `~/.hermes/inbox/cursor-loop-v2-full-audit.md` (Full audit)
- `~/.hermes/inbox/cursor-loop-integration-round4.md` (Round 4)
- `~/.REPLACE_ME.md` (this file)

---

## TL;DR

**Round 4** gave us the orchestrators. **Round 5** makes them run
continuously on all projects.

**The 3 must-ship:**
1. Project registry (`projects.yaml`) — 3h
2. Per-repo tick (`repo_tick.py`) — 4h
3. Single run-all (`cron_orchestrator.py`) — 2h

**Total: 9 hours** for a fully autonomous pipeline.

**The 9 nice-to-have:** wire orchestrators, health scoring, dashboard,
auto-remediation, skill usage tracking, loop-back, kanban integration,
new project scaffold, differential snapshots.

**Total: 36 hours** for a complete Eneve-equivalent pipeline.

Stand by for executio
