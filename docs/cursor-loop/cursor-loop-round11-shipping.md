# Cursor Loop Integration — Round 11 (2026-07-31)

**Source:** `cursor_20260628.zip` (1.9 MB, 620 files) extracted to `/tmp/cursor_extract3/`
**Previous rounds:** round 3, round 4 (2026-07-29) — captured 90% of high-value patterns.
**This round:** finish the last 10% — merge ticket-plan, port full FORBIDDEN list, document skip decisions.

---

## What shipped in R11 (3 items)

### #1 — MERGE `ticket-plan` into `ticket-lifecycle`

Eneve's `ticket-plan` was a thin router (3 operations: validate-plan, fix-plan, roadmap). Hermes's `ticket-lifecycle` already covered start→plan→execute→progress→validate→close but lacked these 3 pre-execution / multi-subticket phases.

**Merge approach:** Added 3 new phases to `ticket-lifecycle` instead of creating a separate skill.

| New phase | What it does | Reference doc |
|---|---|---|
| **Phase 7 — validate-plan** | 8-category pre-execution quality gate (Structure, Objective, Requirements, AC, Strategy, Complexity, OPSEC, Executability) with BLOCKER/MUST-FIX/NICE-TO-HAVE severity levels | `references/validate-plan-criteria.md` (7.1KB) |
| **Phase 8 — fix-plan** | Auto-remediation decision tree (OPSEC first → missing sections → non-testable ACs → comprehensive) | `references/fix-plan-patterns.md` (5.0KB) |
| **Phase 9 — roadmap** | Multi-subticket planning with milestone ladder, owner/dep/risk mapping, near-term actions | `references/roadmap-template.md` (5.1KB) |

**Files updated:**
- `~/.hermes/skills/ticket-lifecycle/SKILL.md` — 184 → 308 lines, version 1.0.0 → 1.1.0
- `~/.REPLACE_ME.md` (NEW)
- `~/.REPLACE_ME.md` (NEW)
- `~/.REPLACE_ME.md` (NEW)
- Ticket folder structure now includes `validation.md` and `roadmap.md`

**New intents added to the deterministic router:**
- `"validate plan X"` → Phase 7
- `"fix plan X"` → Phase 8
- `"create roadmap X"` → Phase 9

**Decision rationale:** Merging (not duplicating) keeps the routing simple. The `ticket-lifecycle` skill already had the file_pattern → rule mapping pattern; adding 3 phases extends the existing router rather than fragmenting user mental models.

---

### #2 — PORT full FORBIDDEN list to `test-doc-standard`

The v2 audit flagged that `test-doc-standard` only had a partial FORBIDDEN list (the table format, not the full corruption fingerprint catalog). The full reference lived only in `cursor-loop-gold-i-missed.md` (inbox, not loaded by skills).

**Fix:** Created `REPLACE_ME.md` (9.0KB) with:

| Section | Content |
|---|---|
| **Forbidden actions table** | 10 rows covering shell bulk edits, repo `scripts/` helpers, parallel transforms, template `write_file`, `/loop N` misinterpretation, `--fix` flag additions, multi-line summaries, empty crefs, AAA-as-functions, empty Arrange |
| **`/loop N` correct interpretation** | N = count of FILES you complete by hand, not iterations of a script |
| **Allowed shell use** | Read-only: pytest, jest, git status, rg, find. Forbidden: anything that writes. |
| **Corruption fingerprints** | 8 Python + 6 TypeScript + 5 cross-language patterns to spot existing damage |
| **Recovery procedure** | `git restore`/`git checkout --`/`git revert` — never repair with more automation |
| **Real-world incident modes** | 4 documented Eneve incidents with recovery time (2 days, 4 hours, 6 hours, 1 day) |
| **What this skill DOES allow** | Read-only lint, manual edits, new files from scratch |
| **What this skill NEVER allows** | `--fix` flag, `scripts/enforce-*`, `find | xargs` writes, `/loop N` as shell iterations |

**Also extended the in-SKILL.md anti-patterns table** from 5 items to 11 (added: past-tense Verifies, empty Verifies, AAA-out-of-order, missing class summary after fix, trailing comment, generated assertions, duplicate braces).

**Files updated:**
- `~/.hermes/skills/test-doc-standard/SKILL.md` — version 0.2.0 → 0.3.0, description now also triggers on "tempted to bulk-edit test files"
- `~/.REPLACE_ME.md` (NEW, 9.0KB)

**Why a reference doc (not inlined):** The original SKILL.md already had the FORBIDDEN section; the new content would have doubled its size. The reference doc is loaded only when the trigger matches ("bulk edit", "test enforcer", etc.), keeping SKILL.md lean for the common case.

---

### #3 — Document skip decisions (2 items)

After analysis, **2 zip items are intentionally NOT integrated**. This round documents the rationale so future agents don't re-litigate.

#### Skip: `jp-toolchain` orchestrator

| Aspect | Detail |
|---|---|
| **Source pattern** | Eneve `.cursor/skills/jp-toolchain/SKILL.md` — router for 7 manual `/jp-*` commands |
| **Why skip** | Marks `disable-model-invocation: true` — it's a manual command router, not agent-callable. The underlying functionality (coverage-runner, finding-deduplication, validate-plan) already exists as standalone Hermes skills. |
| **Verdict** | Hermes already has coverage-runner, finding-deduplication, quality-findings-log. A manual router adds friction without capability. |

#### Skip: 11 EMPTY `agent-application` stub dirs

| Aspect | Detail |
|---|---|
| **Source pattern** | `agile-agent-application`, `documentation-agent-application`, `dotnet-agent-application`, etc. — 11 dirs in `.cursor/skills/` |
| **Why skip** | All 11 dirs are EMPTY — no SKILL.md inside. They were placeholders for the "file_pattern → rule" router pattern that Eneve never finished implementing. |
| **Verdict** | Creating empty stubs to match empty stubs would be cargo-culting. The pattern itself (file_pattern → rule) is captured in `ticket-lifecycle`'s "Agent-Application Pattern" section. The 11 specific stubs were Eneve-domain-specific (dotnet, rule-authoring, scripts) and don't translate to a greenfield TS/Python stack. |

---

## Final integration status

| Zip item | Hermes equivalent | Status |
|---|---|---|
| `code-coverage` | `coverage-runner` | ✓ R4 |
| `delivery-prep` | `delivery-prep` | ✓ R4 |
| `jp-toolchain` | — | ✗ SKIPPED (R11) |
| `manage-playbook` | `manage-playbook` | ✓ R4 |
| `prompt-authoring` | `prompt-improvement-loop` | ✓ R4 |
| `quality-gate` | `quality-gate` | ✓ R4 |
| `ticket-lifecycle` | `ticket-lifecycle` | ✓ R4 + extended in R11 (Phases 7-9) |
| `ticket-plan` | merged into `ticket-lifecycle` | ✓ R11 MERGE |
| 188 prompts | 6 ported + 1 merged | ✓ |
| 78 scripts | 8 ported + 1 lint_tests.py | ✓ |
| 11 agent-application stubs | — | ✗ SKIPPED (R11) |
| FORBIDDEN list | `REPLACE_ME.md` | ✓ R11 |
| 123 rules | partial via existing skills | ⚠️ most are Eneve-style enforcement, don't generalize |
| 104 exemplars | partial via existing skills | ⚠️ most are Eneve-specific |

**Coverage: ~95% of high-value patterns now integrated.** The remaining 5% is genuinely Eneve-specific (Jira tickets, C#/.NET, VB.NET migration, Eneve-ticket-prefix) and doesn't generalize to a greenfield TS/Python/AI-agent stack.

---

## Smoke test

```
✓ ticket-lifecycle/SKILL.md: 184→308 lines, v1.0.0→v1.1.0
✓ REPLACE_ME.md: NEW (7.1KB)
✓ REPLACE_ME.md: NEW (5.0KB)
✓ REPLACE_ME.md: NEW (5.1KB)
✓ test-doc-standard/SKILL.md: 270→288 lines, v0.2.0→v0.3.0
✓ REPLACE_ME.md: NEW (9.0KB)
✓ All 11 anti-patterns present
✓ Frontmatter valid (description + version + tags)
✓ Skip decisions documented in this R11 doc
```

---

## Cumulative totals (R5+R6+R7+R8+R9+R10+R11)

| Round | Scripts | Skills touched | Notable |
|---|---|---|---|
| R5 | 7 | 5 | First autonomous pipeline |
| R6 | 6 | 4 | Skill migration, T9/T10 |
| R7 | 4 | 3 | Traefik, Telegram, AI status |
| R8 | 3 | 2 | CF Pages LIVE |
| R9 | 3 | 2 | Observability |
| R10 | 3 | 1 | Self-healing |
| **R11** | **0** | **2** | **Cursor zip finalization** |
| **Total** | **26** | **19** | — |

---

## Next round candidates

1. **Rotate Cloudflare API token** — unblocks status-page-deploy (5min)
2. **Cost-aware routing** (B-31) — auto-route cheap queries to free models (4h)
3. **Vector DB / RAG** (F-1) — embed all skills for semantic search (3h)
4. **More eval sets** — repo_tick / dashboard_server / telegram_bot coverage (1h)
5. **Add ticket-plan → ticket-lifecycle migration example** — practice using the new Phases 7-9 on a real ticket (1h)

**Round 11 complete. Cursor zip is now ~95% integrated. 2 intentional skips documented. No further work needed on this artifact.**