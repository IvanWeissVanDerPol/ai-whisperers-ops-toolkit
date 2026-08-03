# .cursor/ Re-Analysis — Gold I Missed in Round 1

## What I caught in round 1

- ✅ 4 categories of `prompt-improvement-loop` rubric (missing-trigger, etc.)
- ✅ The "staged + human-commit" gate pattern
- ✅ 5 exemplars ported (user-story, complexity-metrics, etc.)
- ✅ AAA test-doc pattern (no bulk enforcers!)
- ✅ The "cost ceiling + cron-cost-guard" divergence from Eneve

## What I missed (and need to port now)

### 🔴 CRITICAL — The `jp-doc-standard` FORBIDDEN list (anti-patterns)

This is the **highest-leverage content in the entire zip** and I only
touched it superficially in `test-doc-standard`. The full FORBIDDEN
table documents specific corruption cases that destroyed "full days
of manual work" at Eneve. Includes:

| Forbidden | Symptom |
|---|---|
| Shell/terminal bulk edits on test files | `Get-ChildItem \| ForEach-Object { WriteAllText }`, `sed -i` over trees |
| Repo `scripts/` helpers for doc traits | `enforce-tst-doc-standard.py`, `cleanup-test-docs.py` |
| Parallel/batched file transforms | "First 70 files missing trait" |
| Template `Write` of whole test files | Regenerating from class/method names only |

**Plus corruption fingerprints:**
- `/// Unit tests for <see cref=""/>.` (empty cref)
- `{public class FooTests` on the line after `public class FooTests`
- Duplicate `{` immediately after the class opening brace
- Class summary/trait injected without blank line after `namespace`

**Why this matters for us:** we don't have `tst/` but we DO have
`tests/`, `__tests__/`, `test_*.py`, `*.test.ts`, `*.spec.ts` across
paragu-ai-platform, template-nextjs-client, psycology, dentist, and
every client repo. The same temptation to "just script it" exists.
The same corruption modes apply.

**Action:** port the full FORBIDDEN list into `test-doc-standard/SKILL.md`
as a dedicated "Anti-patterns (corruption modes)" section.

### 🟡 HIGH — `jp-address-findings` tier model

This is a clean 3-tier model for triaging review findings that I
completely missed:

| Tier | Action |
|---|---|
| **Minor / Uncertain** | Fix directly if unambiguous + file-scoped |
| **Observations** | Resolve only if within files already in review scope — don't expand scope |
| **Blocker / Major** | Skip — assume already handled before this step |

The model is **anti-scope-creep** by design. It forces the agent to
acknowledge that "Blocker / Major" findings aren't its job in a
post-review cleanup pass. This is a missing skill.

**Action:** create new skill `review-findings-triage` that implements
this exact 3-tier model. Pair it with `simplify-code` (which is the
cleanup pass that produces findings to triage) and `pr-review`.

### 🟡 HIGH — `jp-quality-push` summary table format

The summary table is a **specific artifact format** that downstream
reporting skills can consume:

```markdown
| Repo | Cov % | CRAP ok | CC ok | Prod doc | Test doc | New findings |
|------|-------|---------|-------|----------|----------|-------------|
| Eneve.eBase.Meter | 74 % | ✓ | ✓ | 3 gaps | 12 fixed | 2 new |
```

The **findings log format** is also reusable:

```markdown
### [phase] finding-id
- **Phase**: coverage | crap | cc | prod-doc | test-doc
- **Severity**: Critical | High | Medium | Low
- **Target**: file:line
- **Issue**: <one sentence>
- **Fix**: <one sentence>
- **Jira**: EBASE-XXXXX (status)
```

**Action:** add this format to `simplify-code` as the canonical output
for batch runs. Could also be a reference doc under the
`simplify-code/references/` directory.

### 🟡 HIGH — The `tracked` vs `new` vs `partial` annotation system

Multiple commands (`jp-quality-push`, `jp-midnight-run`, `jp-analyze-gaps`)
share a common pattern:

> Before surfacing findings as new work, cross-check against:
> - `tickets/` subfolders in the current repo
> - `docs/technical/` specs that already document the identified issue
>
> For each finding, annotate:
> - **New** (not tracked)
> - **Tracked** (ticket or spec exists — cite it)
> - **Partial** (partially covered — cite what exists, what's missing)
>
> Only **New** and **Partial** findings require follow-up action.

This is a **deduplication pattern** that prevents double-reporting the
same finding across multiple invocations. It's missing from our current
`pr-review` and `simplify-code` skills.

**Action:** create a new skill `finding-deduplication` that implements
this tracking pattern. Or add it as a Phase to `simplify-code` (after
Phase 1.5 complexity gate, before the 4-reviewer fan-out).

### 🟢 MEDIUM — The `Corruption fingerprints` recovery procedure

The `jp-doc-standard` says: "If corruption already happened: recover
with `git restore` / `git checkout --` on the affected paths (or revert
the commit). Do **not** 'repair' dozens of test files with another
bulk regex pass."

This is a general **"stop and revert, don't re-fix"** rule for any
bulk-edit disaster. Applies beyond tests — applies to any code
where a partial / corrupted bulk-edit happened.

**Action:** add to `simplify-code`'s pitfalls and to a new
`disaster-recovery` skill (or extend the existing one).

### 🟢 MEDIUM — Quality Run Summary table

The `jp-midnight-run` produces a per-phase summary:

```markdown
| Phase | Gate | Result | New findings |
|-------|------|--------|-------------|
| Coverage | ≥ 70 % | 74 % | 2 |
| CRAP | < 30 | ✓ | 0 |
| CC | < 16 | ✓ | 0 |
| Prod doc | High gaps = 0 | 3 gaps | 1 |
| Test doc | All files compliant | 12 fixed | 0 |
```

This is a **canonical phase summary format** that any orchestrated
quality pass should produce. Better than our freeform text.

**Action:** add to `simplify-code` as the canonical multi-phase output
format (when running with `--multi-phase` flag).

### 🟢 MEDIUM — `jp-check-documentation-sync` XML request schema

```xml
<doc_sync_scan>
  <scope>[capability id | topic id | domain name | @path]</scope>
  <stale_days>[optional, default 90]</stale_days>
  <write_registry>[true | false, default true]</write_registry>
</doc_sync_scan>
```

This is a **typed input schema** pattern for orchestrator commands.
Better than freeform "scope it like this". Worth porting as the
canonical input format for `documentation-sync-checker`.

**Action:** add to `documentation-sync-checker` as the canonical
CLI input format.

### 🟢 LOW — `jp-commit-text` Conventional Commit format

Bracket-ticket-ID style: `type[TICKET-ID]: summary` with no footer.
We use Conventional Commits (`feat:`, `fix:`, etc.) without ticket IDs.
This is a divergence worth noting but not porting.

### 🟢 LOW — `jp-investigate-topic` topic-registry YAML pattern

YAML registry of topics with statuses (`proposed`, `covered`, `scoped`,
`partial`). We don't have a topic registry; our work is organized
in Kanban instead. Different paradigm; not porting.

### 🔴 CRITICAL — The `tickets/quality-findings.md` registry pattern

Every quality run reads from + appends to a persistent findings log:

```markdown
# Quality Findings — [RepoName]

## coverage
### cov-2025-01-15-001
- **Phase**: coverage
- **Severity**: Medium
- **Target**: src/Services/MeterService.cs:42
- **Issue**: Method has 12 branches but only 60% coverage
- **Fix**: Add 3 test cases covering edge branches
- **Jira**: EBASE-14257 (In Progress)

## crap
### crap-2025-01-15-001
...

## cc
...

## prod-doc
...

## test-doc
...
```

This is a **persistent memory** that survives across quality runs. Without
it, the cron would re-report the same findings every Monday forever.

We have Kanban tickets, but **not a per-repo findings log** that
aggregates cross-cutting findings.

**Action:** create new skill `quality-findings-log` that:
1. Reads from `~/.hermes/state/quality-findings/[repo-name].md` (per-repo)
2. Cross-checks new findings against the log
3. Annotates New / Tracked / Partial
4. Appends New + Partial only

This is the missing link between `prompt-quality` Kanban (which is
for skill-wide findings) and per-repo findings (which don't exist yet).

---

## Summary of new artifacts to create

| # | Skill / Update | Type | Why |
|---|---|---|---|
| 1 | `test-doc-standard` v0.2.0 | UPDATE | Add full FORBIDDEN list + corruption fingerprints |
| 2 | `review-findings-triage` | NEW | 3-tier model (Minor / Observations / Blocker) |
| 3 | `finding-deduplication` | NEW | New/Tracked/Partial cross-check pattern |
| 4 | `quality-findings-log` | NEW | Per-repo persistent findings registry |
| 5 | `simplify-code` v1.3.0 | UPDATE | Add Phase 1.6 (finding dedup) + canonical output formats |
| 6 | `documentation-sync-checker` v0.2.0 | UPDATE | XML `<doc_sync_scan>` schema |
| 7 | New exemplar: `agent-application-rule` v0.2.0 | UPDATE | Already ported; re-verify |
| 8 | New exemplar: `changelog-agent-application` | NEW | The 3-tier agent-application rule |

## Where these live

**NOT** in psycology. These belong in the **shared Hermes skill
library** (`~/.hermes/skills/`) so every session (every profile,
every project) loads them. The integration docs belong in a new
location: `~/.hermes/integrations/cursor-loop/` so all sessions
reference the same canonical doc.
