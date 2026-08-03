# Cursor Loop v2 — Full Audit & Hermes Upgrade Plan

**Date:** 2026-07-29
**Source:** `cursor_20260628-2.zip` (1.9 MB, **620 files** — the full Eneve playbook)
**Previous round:** `cursor-loop-integration-round3.md` covered only 40 files (~3% of payload)

---

## What this zip actually is

The previous zip was a working-state snapshot. **This is the entire
Eneve engineering playbook** — the AI rules + prompts + skills + scripts +
exemplars system that turns a Cursor subscription into a fully orchestrated
.NET engineering org. Files in 100+ directories:

| Layer | Count | Purpose |
|---|---|---|
| **Prompts** (`.cursor/prompts/`) | 188 | Task workflows — the "what to do" |
| **Rules** (`.cursor/rules/`) | 123 | Standards — the "how to do it" |
| **Exemplars** (`.cursor/exemplars/`) | 104 | Few-shot patterns (critic-only) |
| **Templars** (`.cursor/templars/`) | 43 | Output structure templates |
| **Scripts** (`.cursor/scripts/`) | 78 | PowerShell + Python automation |
| **Collections** (`.cursor/prompts/collections/`) | 27 | Prompt Registry manifests |
| **Orchestrator skills** (`.cursor/skills/`) | 8 | Top-level routers |
| **Loop state** (`.cursor/.loop-state/`) | 3 | Loop engine + queue + diff |
| **Total** | **620** | Full AI playbook |

**Loop state:** `iteration: 51, loopComplete: true, remaining: 0`. The
prompt-improvement pipeline has finished all 51 prompts.

---

## Phase 1 — What's already in Hermes (Round 3 scorecard)

Round 3 internalized 8 skills + 5 scripts into `~/.hermes/skills/`:

| Round 3 skill | Source pattern | Status |
|---|---|---|
| `prompt-quality-rubric` | Eneve `validate-prompt.prompt.md` rubric | ✅ |
| `prompt-improvement-loop` | Eneve `prompt-improvement-loop.json` engine | ✅ |
| `test-doc-standard` v0.2.0 | `jp-doc-standard.md` FORBIDDEN list | ✅ |
| `documentation-sync-checker` v0.2.0 | `jp-check-documentation-sync.md` XML schema | ✅ |
| `review-findings-triage` | `jp-address-findings.md` 3-tier model | ✅ |
| `finding-deduplication` | `jp-analyze-gaps.md` New/Tracked/Partial | ✅ |
| `quality-findings-log` | `tickets/quality-findings.md` registry | ✅ |
| `disaster-recovery` | `jp-doc-standard.md` "stop and revert" rule | ✅ |
| `simplify-code` v1.3.0 | Added Phase 1.6 (dedup) + 1.7 (triage) | ✅ |

**Total coverage of the v1 zip (40 files):** ~85% of high-value patterns.

---

## Phase 2 — What this v2 zip reveals that we missed

### 2.1 The 8 orchestrator skills (the missing orchestration layer)

These are the **routers** that composes all 188 prompts into user-facing
commands. They are the **single biggest gap** in Round 3:

| Eneve skill | What it does | Hermes equivalent today |
|---|---|---|
| `code-coverage` | Run coverage + loop until ≥70% | ❌ no orchestrator |
| `delivery-prep` | Branch validation + merge prep + release | ❌ no orchestrator |
| `jp-toolchain` | 7-command `/jp-*` router | ❌ no orchestrator |
| `manage-playbook` | `.cursor/` housekeeping sweep | ⚠️ partial (cron only) |
| `prompt-authoring` | Full lifecycle (validate→improve→enhance→extract→register) | ⚠️ partial (run_loop.py does 1 phase) |
| `quality-gate` | Build → lint → test → fix loop | ❌ no orchestrator |
| `ticket-lifecycle` | Start→execute→close ticket workflow | ❌ no orchestrator |
| `ticket-plan` | Validate plan + fix + roadmap | ❌ no orchestrator |

**Net:** Round 3 captured the **primitives** (linters, scripts, rubrics).
This zip shows the **composers** — the deterministic routers that
orchestrate primitives into user-facing workflows. **Missing 5/8.**

### 2.2 The agent-application pattern (one router per domain)

Eneve uses a **meta-pattern** that I missed entirely in Round 3:

```
For each domain (ticket, migration, agile, ...):
  ONE agent-application rule (the router)
  N operational rules (the actual standards)
```

The agent-application rule:
- Reads user intent
- Maps file pattern → appropriate operational rule
- Maps behavioral trigger (`"done"`, `"switching"`) → discipline rule
- Enforces the order of application

**Example (from `ticket/agent-application-rule.mdc`):**
| File pattern | Governing rule |
|---|---|
| `tickets/TICKET-123/plan.md` | `rule.ticket.plan.v1` |
| `tickets/TICKET-123/context.md` | `rule.ticket.context.v1` |
| `tickets/TICKET-123/progress.md` | `rule.ticket.progress.v1` |

| Behavioral trigger | Discipline rule |
|---|---|
| User claims "done" | `rule.ticket.completion-discipline.v1` |
| User requests ticket switch | `rule.ticket.switching-discipline.v1` |
| Before marking complete | `rule.ticket.validation.v1` |

**Hermes equivalent:** none. Our skills load reactively on description
match. We don't have explicit agent-application rules that route to
skill variants based on file pattern or behavior.

### 2.3 The rule frontmatter grammar (`.mdc` files)

Every Eneve rule has a **structured frontmatter** that defines its
contract:

```yaml
---
id: rule.ticket.workflow.v1
kind: rule
version: 1.1.0
description: Standard workflow for ticket documentation...
globs: **/tickets/**/*.md
governs: **/tickets/**/*.md
implements: ticket.workflow
requires:
  - rule.ticket.plan.v1
  - rule.ticket.context.v1
  - rule.ticket.progress.v1
model_hints: { temp: 0.2, top_p: 0.9 }
provenance: { owner: team-ticket, last_review: 2026-05-26 }
alwaysApply: false
---
```

Key fields:
- `id`, `kind`, `version` — stable identity (files can move, IDs stay)
- `globs` / `governs` — file-mask trigger pattern
- `implements` — capability this rule provides
- `requires` — other rules this depends on
- `provenance` — ownership + last review date
- `alwaysApply` — strategy 1/2/3 selector

**Hermes skills have frontmatter** (`name`, `description`,
`version`) but **no `requires`, `implements`, `provenance`, `globs`,
`governs`** — we don't have a way to express "skill X triggers on
file pattern Y" or "skill A depends on skill B".

### 2.4 The 3 invocation strategies

From `REPLACE_ME.mdc`:

| Strategy | Pattern | When | Use case |
|---|---|---|---|
| **Strategy 1** | File-mask triggered (`globs`, `governs`, `alwaysApply: false`) | File matches pattern | Operational rule on `plan.md` |
| **Strategy 2** | Description-triggered agentic (NO globs/governs) | User intent matches description | Agent-application rule |
| **Strategy 3** | Always-apply (`globs: ["**/*"]`, `governs: []`, `alwaysApply: true`) | Every file | Read-only validators |

**Hermes:** skills load based on `description` match only (Strategy 2).
We don't have Strategy 1 (file-mask triggering) or Strategy 3 (always-on
validators). The `auto_load` config in `config.yaml` is a crude form of
Strategy 3.

### 2.5 The validation status (compliance report)

Eneve ran a self-audit in `rules/CROSS-DOMAIN-INVOCATION-VALIDATION.md`
and found:

- **Only 4% of rules** have correct `alwaysApply` field
- All agent-application rules correctly omit `globs/governs` (Strategy 2)
- 96% of rules missing the `alwaysApply` field entirely

**Insight:** Even Eneve's own playbook has compliance gaps. Hermes would
score better than 4% if we adopt the framework properly, because our
skills all have `description` (Strategy 2).

### 2.6 The prompt frontmatter (`.prompt.md` files)

Every Eneve prompt has richer frontmatter than our skills:

```yaml
---
name: validate-prompt
description: "Validate a prompt file against Prompt Registry format..."
model: composer-2.5          # model tier
agent: cursor-agent          # which agent uses this
tools: [fileSystem]          # explicit tool allowlist
category: prompt
tags: [prompts, validation, quality-check, standards, compliance]
argument-hint: "Prompt file path"
templar: .REPLACE_ME.md
exemplar: .REPLACE_ME.md
rules:
  - .cursor/rules/prompts/prompt-creation-rule.mdc
  - .REPLACE_ME.mdc
---
```

**Hermes skills have:** `name`, `description`, `version`, `model` (sometimes).
**Missing:** `tools`, `templar`, `exemplar`, `rules`, `tags`, `argument-hint`.

**Specifically useful:**
- `templar` / `exemplar` refs — explicit pointers to output templates
  and few-shot examples. **Hermes has nothing equivalent.**
- `tools` — explicit tool allowlist per skill. Hermes has it at the
  profile level, not per skill.
- `rules` — explicit list of rule files this skill depends on. **Hermes
  has no concept of "skill dependencies".**

### 2.7 The 27 Prompt Registry collections

`prompts/collections/` has 27 YAML manifests, one per domain:

```yaml
# agile.collection.yml
domain: agile
version: 1.0.0
prompts:
  - agile/create-user-story.prompt.md
  - agile/create-business-feature.prompt.md
  - agile/create-epic.prompt.md
  - agile/create-technical-feature.prompt.md
  - agile/split-user-story.prompt.md
```

**Why this matters:** Skill discovery is keyed by collection membership.
The `validate-prompt-collections.ps1` script validates that every
prompt file is in exactly one collection, and every collection
manifest matches reality.

**Hermes:** no equivalent. The `~/.hermes/skills/` directory has 188
entries but no manifest grouping them by domain. Discovery is filename
grep only.

### 2.8 The 6-phase prompt improvement pipeline

From `manage-playbook` skill:

```
1. /find-prompts-needing-review          ← identify what needs attention
2. /process-prompt-improvement-cycle [file]  ← atomic unit
   (or steps 3-10 manually)
3. /improve-prompt [file]                ← fix critical issues
4. /enhance-prompt [file]                ← add examples, CoT, decision trees
5. /find-extraction-candidates           ← find templar/exemplar opportunities
6. extract-templar-exemplar.ps1          ← extract to .cursor/templars/
7. /find-condense-candidates             ← identify oversized prompts
8. condense-prompts.prompt.md            ← reduce size, replace bulk with pointers
9. /find-script-extraction-candidates    ← find inline scripts → toolbox
10. extract-script-templars-exemplars    ← move scripts to .cursor/scripts/
```

**Hermes `run_loop.py` does:** steps 1, 3, 4.
**Missing:** steps 5, 6, 7, 8, 9, 10 (the extraction/condense pipeline).

### 2.9 The structured-rule framework (5 phases of rule creation)

From `rules/rule-authoring/`:

1. **Extract** patterns from conversations (`rule-extraction-from-practice.mdc`)
2. **Structure** them using canonical format (`rule-file-structure.mdc`)
3. Define **invocation** strategy (`rule-invocation-strategies.mdc`)
4. Add **versioning** and provenance (`rule-provenance-and-versioning.mdc`)
5. Create **validation** checklist (`rule-validation-and-checklists.mdc`)

**Hermes:** we have `skill_manage` which creates skills, but **no
5-phase framework**. Skills are created ad-hoc, not extracted from
practice with structured provenance.

### 2.10 The 31 PowerShell fix scripts (per-diagnostic-code)

`scripts/quality/` has 31 `.ps1` scripts, one per diagnostic code:

- `fix-ca1825-static-readonly-arrays.ps1`
- `fix-ca1848-logger-message.ps1`
- `fix-ide0009-this-qualification.ps1`
- `fix-ide0028-collection-expressions.ps1`
- `fix-ide1006-async-method-naming.ps1`
- `fix-ide1006-comprehensive-references.ps1`
- `fix-ide1006-field-references.ps1`
- `fix-ide1006-naming-violations.ps1`
- `fix-ide1006-private-field-casing.ps1`
- `fix-ide1006-resource-references.ps1`
- `fix-ide1006-targeted-patterns.ps1`
- `fix-cs1570-xml-comments.ps1`
- `fix-cs1570-xml-format.ps1`
- `fix-cs1591-documentation.ps1`
- ... 18 more

**Pattern:** Each diagnostic code (CS/IDE/CA) has a dedicated fix script.
The `quality-gate` loop runs build → enumerates errors → groups by code
→ runs the matching script → re-builds → loops until zero.

**Hermes:** we have `lint_tests.py` (1 linter) and
`check_complexity_gate.py` (1 gate). **No per-diagnostic fix scripts.**
We have the FORBIDDEN list (DO NOT use scripts) but lacked the
**DO use scripts** nuance — the FORBIDDEN list is about tst/ files
specifically, not about lint loops.

### 2.11 The `validate-pre-merge.ps1` script

The "PRE-MERGE ORCHESTRATOR" — a 7-step automated workflow:

```
1. Auto-fix (run all fix scripts)
2. Build (dotnet build)
3. Test (dotnet test)
4. Validate (CRAP, CC, coverage gates)
5. Format (dotnet format)
6. Report (JSON output for AI consumption)
7. Batch processing support
```

**Hermes equivalent:** **none.** We have no pre-merge validation that
chains build + test + lint + coverage + format gates.

### 2.12 The 188 prompts — domain breakdown

Top 10 domains by prompt count:

| Domain | Count | Notes |
|---|---|---|
| code-quality | 21 | The richest domain |
| housekeeping | 20 | Discovery + cleanup + extraction + maintenance |
| ticket | 17 | Full lifecycle |
| migration | 16 | C++ → C# framework |
| script | 14 | PowerShell + Python patterns |
| documentation | 10 | XML docs + Mermaid |
| cicd | 9 | Azure Pipelines + versioning |
| git | 8 | Branch + commit + MR |
| prompt | 7 | The meta-domain (how to write prompts) |
| release | 3 | Tag-based versioning |

**Most transferable to Hermes (not Eneve-specific):**
- code-quality (we have 1 skill, they have 21 prompts)
- housekeeping (we have cron, they have 20 prompts)
- documentation (we have 1 skill, they have 10)
- prompt (we have 1 skill, they have 7)
- git (we have github-pr-workflow, they have 8)

**Eneve-specific (drop):** migration (C++→C#), azure devops, .NET diagnostics.

---

## Phase 3 — Hermes Upgrade Plan (Round 4)

### Tier 1 — Build the 5 orchestrator skills (high value, high effort)

**Estimated effort:** 8-12 hours total
**Value:** Closes the orchestration gap. Once these exist, every
existing primitive (linters, scripts, rubrics) becomes accessible via
a single slash-command.

| # | Skill | Path | What it does |
|---|---|---|---|
| 1 | `coverage-runner` | `~/.hermes/skills/coverage-runner/` | Run coverage + loop until ≥70% |
| 2 | `quality-gate` | `~/.hermes/skills/quality-gate/` | Build → lint → test → fix loop |
| 3 | `delivery-prep` | `~/.hermes/skills/delivery-prep/` | Branch validation + merge prep + release |
| 4 | `ticket-lifecycle` | `~/.hermes/skills/ticket-lifecycle/` | Start → execute → close ticket workflow |
| 5 | `manage-playbook` | `~/.hermes/skills/manage-playbook/` | `.cursor/` housekeeping sweep (full version) |

### Tier 2 — Add the structured frontmatter to Hermes skills

**Estimated effort:** 2 hours
**Value:** Every skill gains explicit metadata for discovery, deps, and provenance.

Add these optional fields to `~/.hermes/skills/*/SKILL.md` frontmatter:

```yaml
---
name: prompt-quality-rubric
description: ...
version: 1.0.0
kind: skill                   # NEW
tools: [terminal, read_file]  # NEW — explicit tool allowlist
tags: [quality, rubric]       # NEW
requires:                     # NEW — skill dependencies
  - prompt-improvement-loop
templar: references/...       # NEW — output template pointer
exemplar: references/...      # NEW — few-shot example pointer
provenance:                   # NEW — ownership + review
  owner: erebus
  last_review: 2026-07-29
---
```

Build a `validate-skill-frontmatter.py` script that:
- Checks every skill has the required fields
- Reports missing deps (skill references something that doesn't exist)
- Reports skills with no tags (low discoverability)

### Tier 3 — Build the 3 invocation strategies

**Estimated effort:** 4 hours
**Value:** Skills can trigger on file pattern, intent, or always-on.

| Strategy | Hermes implementation |
|---|---|
| Strategy 1 (file-mask) | New `globs` field in frontmatter. Add a `~/.hermes/scripts/file-mask-router.py` that detects which skill applies to a given file path. |
| Strategy 2 (description) | Current behavior. No change. |
| Strategy 3 (always-apply) | New `alwaysApply: true` field. Loaded into every session regardless of intent. Use sparingly (universal validators like `avoid-ai-writing`). |

### Tier 4 — Build the 27 Prompt Registry collections

**Estimated effort:** 3 hours
**Value:** Domain-based discovery. Currently skills are filename-only.

Create `~/.hermes/skills/collections/<domain>.yml` for each domain:
- `client-work.yml`
- `code-quality.yml`
- `documentation.yml`
- `testing.yml`
- `devops.yml`
- `housekeeping.yml`
- `meta.yml`
- ...

Plus a `validate-collections.py` script that checks every skill is in
exactly one collection and every collection manifest matches reality.

### Tier 5 — Build the 5 extraction/condense pipeline steps

**Estimated effort:** 6 hours
**Value:** Closes the "find → extract → condense" loop. Currently
`run_loop.py` does find → enhance only.

Build:
- `find-extraction-candidates.py` — find skills ready for templar/exemplar extraction
- `find-condense-candidates.py` — find skills > 200 lines ready to be condensed
- `find-script-extraction-candidates.py` — find inline scripts in skill SKILL.md that belong in scripts/
- `extract-templar.py` — extract reusable structure to a separate file
- `condense-skill.py` — replace bulk SKILL.md with pointers to extracted files

### Tier 6 — Build the structured-rule framework (5 phases of rule creation)

**Estimated effort:** 4 hours
**Value:** Skills get created with provenance and validation, not ad-hoc.

Adapt `~/.hermes/skills/rule-authoring/` or create new skill
`hermes-skill-authoring` that:
1. Extracts patterns from past sessions (use `session_search`)
2. Structures them using `skill_view` templates
3. Selects invocation strategy (file-mask / description / always)
4. Adds versioning + provenance
5. Creates validation checklist

### Tier 7 — Port the 6 most transferable prompts

**Estimated effort:** 6 hours
**Value:** Closes the prompt-library gap. Eneve has 188 prompts;
Hermes has 0 (we only have skills).

Port the 6 highest-value Eneve prompts into Hermes-style skills:

1. `code-quality/review-code-quality.prompt.md` → `~/.hermes/skills/code-review/`
2. `REPLACE_ME.prompt.md` → `~/.hermes/skills/find-dead-skills/`
3. `REPLACE_ME.prompt.md` → `~/.hermes/skills/doc-architecture/`
4. `refactoring/refactor-public-api-surface.prompt.md` → `~/.hermes/skills/api-refactor/`
5. `git/create-merge-request.prompt.md` → `~/.hermes/skills/create-pr/`
6. `release/check-release-branch.prompt.md` → `~/.hermes/skills/release-check/`

### Tier 8 — Build the `validate-pre-merge` equivalent

**Estimated effort:** 4 hours
**Value:** One command runs the full pre-merge gate.

Build `~/.hermes/scripts/pre_merge_check.py` that:
1. Auto-fixes (run any auto-fix scripts)
2. Builds (next build, tsc, etc.)
3. Tests (pytest, jest)
4. Lints (eslint, ruff, our linters)
5. Validates (CRAP, CC, coverage gates)
6. Formats (prettier, black)
7. Reports JSON for AI consumption

### Tier 9 — Pack the audit findings into the playbook

**Estimated effort:** 1 hour
**Value:** Semantic version of the integration is now complete.

- Score all Round 4 skills using `score_skill.py`
- Update `~/.hermes/inbox/cursor-loop-integration-round4.md` with results
- Bump Cron job `skill-quality-audit` to audit Round 4 skills too
- Update Kanban `prompt-quality` board with new tickets

---

## Phase 4 — What I recommend doing now (priority list)

Ranked by value-to-effort:

| Priority | Action | Effort | Value |
|---|---|---|---|
| **P0** | Build the 5 orchestrator skills (Tier 1) | 8-12h | ⭐⭐⭐⭐⭐ |
| **P1** | Add structured frontmatter to Hermes skills (Tier 2) | 2h | ⭐⭐⭐⭐ |
| **P2** | Build the 3 invocation strategies (Tier 3) | 4h | ⭐⭐⭐⭐ |
| **P3** | Build the 27 collections (Tier 4) | 3h | ⭐⭐⭐ |
| **P4** | Build the extraction/condense pipeline (Tier 5) | 6h | ⭐⭐⭐ |
| **P5** | Build the structured-rule framework (Tier 6) | 4h | ⭐⭐⭐ |
| **P6** | Port the 6 highest-value prompts (Tier 7) | 6h | ⭐⭐⭐ |
| **P7** | Build `pre_merge_check.py` (Tier 8) | 4h | ⭐⭐⭐ |
| **P8** | Final audit + Round 4 doc (Tier 9) | 1h | ⭐⭐ |

**Total to ship Round 4:** ~36 hours of work.

**Suggested approach:** Ship P0 + P1 first (10-14h), validate, then
P2-P8 iteratively. The orchestrator skills are the biggest unlock —
everything else composes on top of them.

---

## Phase 5 — Honest caveats

1. **Eneve is .NET / Azure DevOps.** Roughly 60% of the material is
   Eneve-specific (CS/IDE/CA diagnostics, .csproj, Azure Pipelines,
   C++→C# migration). Don't try to port these — they're not relevant.

2. **The 8 orchestrator skills are designed for Cursor's slash-command
   UX.** Hermes can mimic this with skill descriptions + slash-command
   auto-completion, but the UX is different. Some adaptation needed.

3. **The agent-application pattern (one router per domain) assumes
   stable domain boundaries.** Hermes has 188 skills across fuzzy
   domains. Forcing strict per-domain routing might be over-engineering.
   Better: use it as a *design principle* when adding new skills, not
   retrofit every existing skill.

4. **The structured frontmatter is great in theory** but the validation
   script would need to be backwards-compatible with existing skills
   that don't have all fields. Use `[tool: optional]` semantics.

5. **The 31 fix scripts are Enekse-specific PowerShell** but the
   *pattern* (one fix script per diagnostic code) is transferable. We
   could build a Python equivalent for our stack (one fix script per
   ruff rule, one per eslint rule, etc.).

---

## Phase 6 — Decision needed

Round 4 is ~36 hours of work. Three options:

**Option A — Ship all of Round 4** (36h, single multi-session push)
**Option B — Ship P0-P2 first** (10-14h), validate, then continue
**Option C — Ship a symbolic "Round 4 starter pack"** (4h):
- 1 orchestrator skill (highest value: `quality-gate`)
- Frontmatter parser
- Show the path; defer full execution

My recommendation: **Option B.** Ship the 5 orchestrator skills +
structured frontmatter, validate the UX, then decide whether to push
the rest. This is the highest-value, lowest-risk path.

Want me to start with Option B?
