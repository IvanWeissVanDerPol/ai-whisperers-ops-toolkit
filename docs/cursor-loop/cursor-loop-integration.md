# Cursor Loop Integration — Canonical Reference

**This is the single source of truth for the Cursor → Hermes integration.**
Every Hermes session (default, lua, copy-bot, closer-bot, all 14
profiles) loads the skills referenced here. The cron, Kanban board,
and scripts all live under `~/.hermes/`.

**If you change anything in this integration, update this file too.**

---

## Why this exists

The `cursor_20260628.zip` artifact was Eneve's `.cursor/` directory
snapshot — 51 prompt-improvement iterations complete, 0 unenhanced,
435K of staged rewrites. We extracted the patterns that generalized
beyond Eneve (no VB.NET / Jira / Eneve-ticket-prefix bindings) and
made them a permanent part of the Hermes shared skill library.

**Last re-analysis:** 2026-07-29 (round 3) — see
[`cursor-loop-gold-i-missed.md`](./cursor-loop-gold-i-missed.md) for
the deep re-read that surfaced the FORBIDDEN list, the 3-tier
finding triage model, the New/Tracked/Partial dedup pattern, and the
per-repo findings registry.

---

## What lives where

| Artifact | Path | Visibility |
|----------|------|-----------|
| **Skills** (shared) | `~/.hermes/skills/` | Loaded by every session |
| **Scripts** (cron + board) | `~/.hermes/scripts/` | Cron + ad-hoc invocation |
| **Cron jobs** | registered via `hermes cron` | Persistent schedule |
| **Kanban board** | `~/.hermes/kanban/boards/prompt-quality/` | Visible in web UI |
| **State / findings log** | `~/.hermes/state/skill-quality-audit/` | Cron-emitted delta |
| **Loop state** | `~/.hermes/skills/prompt-improvement-loop/.loop-state/` | Per-run scratch |
| **This doc + analysis** | `~/.hermes/inbox/` | Reference, not loaded |

**Not in psycology.** Not in any single repo. These are shared infra.

---

## Skills (5 + 4 in pipeline)

### Production-ready

| Skill | Path | Score | Purpose |
|---|---|---|---|
| `prompt-quality-rubric` | `~/.hermes/skills/prompt-quality-rubric/` | 78/100 | 4-category structural scorer (trigger / steps / verification / pitfalls). Zero LLM cost. ~5s for 717 skills. |
| `prompt-improvement-loop` | `~/.hermes/skills/prompt-improvement-loop/` | 90/100 | 6-phase orchestrator: score → queue → rewrite → stage → human-review → housekeeping. 20-item cap, $2 budget. |
| `test-doc-standard` | `~/.hermes/skills/test-doc-standard/` | 90/100 | AAA + `Verifies that` pattern. Python pytest + TS Jest linter. **Has corruption-mode FORBIDDEN list.** |
| `documentation-sync-checker` | `~/.hermes/skills/documentation-sync-checker/` | 90/100 | 4 drift categories. Has Tailwind/CSS variable noise filter. |

### Updated (was already in stack)

| Skill | Path | Version | Change |
|---|---|---|---|
| `simplify-code` | `~/.REPLACE_ME/` | **v1.2.0** | Phase 1.5: CRAP + CC gate before 4-reviewer fan-out. Standalone script: `check_complexity_gate.py`. |

### In pipeline (to build next)

| Skill | Why | Pattern source |
|---|---|---|
| `review-findings-triage` | 3-tier model (Minor / Observations / Blocker) | `jp-address-findings.md` |
| `finding-deduplication` | New / Tracked / Partial cross-check | `jp-analyze-gaps.md`, `jp-midnight-run.md` |
| `quality-findings-log` | Per-repo persistent findings registry | `tickets/quality-findings.md` pattern |
| `disaster-recovery` | Stop-and-revert rule for bulk-edit disasters | `jp-doc-standard.md` "If corruption already happened" |

### Already-skipped (Eneve-specific)

- 4 jp commands for Jira / Atlassian MCP → we use Kanban
- 4 jp commands for VB.NET/C++ migration → we're greenfield TS/Python
- 2 jp commands for Eneve ticket prefixes (`EBASE-NNNNN`) → we use `HERMES-<client>-<seq>`

---

## Scripts (2 cron/board + 5 in-skill)

| Script | Path | Invoked by |
|---|---|---|
| `score_skill.py` | `~/.hermes/skills/prompt-quality-rubric/scripts/` | ad-hoc + cron + loop |
| `run_loop.py` | `~/.REPLACE_ME/` | ad-hoc + Phase 4a cron |
| `lint_tests.py` | `~/.hermes/skills/test-doc-standard/scripts/` | ad-hoc + pre-commit hook |
| `check_drift.py` | `~/.REPLACE_ME/` | ad-hoc + Phase 4b cron |
| `check_complexity_gate.py` | `~/.REPLACE_ME/` | ad-hoc + pre-commit hook |
| `skill_quality_audit.py` | `~/.hermes/scripts/` | weekly cron (no LLM) |
| `seed_prompt_quality_board.py` | `~/.hermes/scripts/` | one-shot, idempotent |

---

## Cron jobs

| Job ID | Name | Schedule | Mode | Repeat |
|---|---|---|---|---|
| `08eb21836275` | `skill-quality-audit` | `0 7 * * 1` (Mondays 7am) | no-agent (zero LLM) | 52 weeks |

**What it does each Monday:**

1. Score all skills under `~/.hermes/skills/`.
2. Compare to last week's `last-findings.json` snapshot.
3. Emit markdown delta report (new vs. fixed skills).
4. Exit code 0 if no new findings; exit code 2 if new findings detected
   (cron delivers the report to operator).

**Operator weekly workflow (~5 min):**

1. Read the cron-delivered report.
2. Open Kanban board `prompt-quality` — new findings are tickets in `todo`.
3. Pick worst-priority ticket. Open the linked skill.
4. Read `~/.REPLACE_ME.md`
   for the right pattern.
5. Edit the skill (`skill_manage(action='edit')` or `patch`).
6. Re-score: `python3 ~/.REPLACE_ME.py --path <skill-path>`
7. Commit by hand. Mark Kanban ticket done.
8. Next Monday, the cron verifies your fix (or flags it as still-bad).

---

## Kanban board

**Slug:** `prompt-quality`
**Path:** `~/.hermes/kanban/boards/prompt-quality/`
**Web UI:** `https://chat.paragu-ai.com/kanban?board=prompt-quality`

**Status flow:** `todo` → `in_progress` → `done`
**Priority formula:** `max(0, 50 - score)` — worst score = highest priority.

**Body template** (auto-seeded by `seed_prompt_quality_board.py`):

```markdown
## Skill audit finding
- Skill: <name>
- Path: <path>
- Current score: <X>/100 (<tier>)
- Target: 80/100 (acceptable tier)

### Category scores
| Category | Score | Notes |
| trigger | X/25 | ... |
| steps | X/25 | ... |
| verification | X/25 | ... |
| pitfalls | X/25 | ... |

### Suggested actions
1. Read prompt-quality-rubric to understand the rubric
2. Read REPLACE_ME.md for patterns
3. Re-score first, then craft a targeted rewrite for the weakest category
4. Re-score the rewrite. Accept only if delta >= +10 AND no regression
5. Apply via patch or skill_manage. Commit by hand.
6. Move this card to done; next cron verifies.
```

---

## Exemplars (8 + INDEX.md)

All under `~/.REPLACE_ME/`:

```
INDEX.md                                          # operator guide
agile/
  user-story-exemplar.md                          # Given/When/Then (Tier 1)
  user-story-bad-exemplar.md                      # contrastive negative (Tier 1)
  epic-exemplar-hermes.md                         # Eneve → Hermes mapping (Tier 2)
changelog/
  generate-changelog-from-git-exemplar.md         # Conventional Commits (Tier 2)
  agent-application-rule-exemplar.md              # auto-apply vs surface (Tier 1)
code-quality/
  complexity-metrics-analysis-exemplar.md         # CRAP/CC table (Tier 1)
  diagnostic-fix-script-pattern-exemplar.md       # 4-phase workflow (Tier 1)
```

**Usage rule:** patterns, not templates. Never copy-paste content.
Shapes are what to extract.

---

## How every session uses this

**No session needs to "load" this manually.** The skills are auto-loaded
by `skill_view` when keywords match. When you (or any session) say any
of:

- "score this skill" / "audit prompts" / "prompt quality"
  → loads `prompt-quality-rubric`
- "improve prompts" / "run the loop" / "batch rewrite"
  → loads `prompt-improvement-loop`
- "test docs" / "AAA pattern" / "Verifies that"
  → loads `test-doc-standard`
- "doc drift" / "stale docs" / "doc-vs-code"
  → loads `documentation-sync-checker`
- "simplify" / "cleanup my changes" / "/simplify"
  → loads `simplify-code` (now Phase 1.5 gated)

**Cross-session state:**

- The Kanban board is shared. Any session can create / update / complete
  tickets on `prompt-quality`.
- The cron is shared. Any session's Monday audit updates the same
  `last-findings.json` snapshot.
- The state file `~/.REPLACE_ME.json`
  is read by every Monday run.

**Per-session state:**

- The loop-state directory (`.loop-state/`) is per-run scratch.
  Each invocation of `run_loop.py` increments `iteration` and writes
  its own `staged-review.diff`.

---

## What's deliberately NOT in psycology / any client repo

- The 5 skills
- The 7 scripts
- The cron job
- The Kanban board
- The 8 exemplars
- This doc

These all live in `~/.hermes/` because they are **shared infra** that
every Hermes session / profile / project loads. Putting them in a
client repo would mean re-deploying them for every client.

**Exception:** per-repo findings registry (`quality-findings-log`,
planned). Each repo gets its own log file, but the skill that
manages those logs is shared.

---

## How to add a new skill to this integration

1. Create the skill at `~/.hermes/skills/<name>/SKILL.md`.
2. Score it: `python3 ~/.REPLACE_ME.py --path <skill-path>`.
3. If score < 70, apply rewrite pattern (see `prompt-improvement-loop`).
4. If score ≥ 70, the skill is "production-ready" and will appear
   in the next Monday's audit as a healthy skill.
5. Update this canonical doc with the new skill row.
6. Update `REPLACE_ME.md` if
   the new skill changes the available patterns.

**Don't:**

- Don't add new skills to a client repo. Use the shared library.
- Don't create per-cron-job scripts in client repos. Use the
  shared scripts under `~/.hermes/scripts/`.
- Don't fork the cron schedule. One cron, one schedule, all skills.
- Don't create a new Kanban board for skill quality. Use `prompt-quality`.

---

## Round history

- **Round 1** (2026-07-29, AM): extracted 4 skills + 1 update + cron + Kanban + 5 exemplars. Verified end-to-end. `REPLACE_ME.md`.
- **Round 2** (2026-07-29, PM): closed the loop with 1 real rewrite (paraguay-open-data-fetch 13→90), fixed doc-sync false-positives, added Phase 1.5 standalone gate, ported 2 more exemplars. `REPLACE_ME.md`.
- **Round 3** (2026-07-29, late): **re-analyzed .cursor/ in depth**, surfaced the missed gold (FORBIDDEN list, 3-tier triage, New/Tracked/Partial dedup, findings registry). Moved docs out of psycology to canonical home at `~/.hermes/inbox/`. **THIS IS WHERE WE ARE.**

**Next round (planned):** build the 4 in-pipeline skills
(review-findings-triage, finding-deduplication, quality-findings-log,
disaster-recovery), update test-doc-standard v0.2.0 with the full
FORBIDDEN list, update simplify-code to v1.3.0 with finding dedup
Phase 1.6.
