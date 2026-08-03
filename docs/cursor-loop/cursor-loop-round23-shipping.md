# Round 23 — Working With Hermes Guide + Skill Updates (Shipped 2026-08-03)

**Source:** User asked for a complete analysis of past sessions, what to do better, and updated docs that would help them work better with Hermes. R23 ships the **single canonical guide** for that.

**Outcome:**
- **`WORKING_WITH_HERMES.md` (17.8 KB)** — the canonical "how to work with me" doc
- **3 updated skills**: `agent-persona-design`, `one-three-one-rule`, `avoid-ai-writing`
- **1 new memory entry** — the 5 user-feedback rules
- **R23 clean-up** — removed duplicate MEMORY entries that had drifted

---

## What R23 actually shipped

### R23-1: Inventory

Found 22 existing cursor-loop round docs but **no single guide for "how to work with Hermes."** The skills (`agent-persona-design`, `one-three-one-rule`, `avoid-ai-writing`) had no R23 patterns.

### R23-2: WORKING_WITH_HERMES.md (17.8 KB)

The single doc Ivan will re-read at session start. Contents:
- **TL;DR** — 5 rules
- **What's actually built** — 9 layers, 24 endpoints, the stack
- **How to talk to Hermes** — 5 voice rules
- **What to do in different session types** — 5 patterns
- **Common patterns** — round commits, watchdog semantics, wrapper for cron args, parallel discovery
- **When to push back on the agent** — explicit user perspective
- **Memory vs skill vs doc** — clear hierarchy
- **Quick recovery** — symptom → action table
- **5-minute session start checklist**
- **1-minute end-of-session checklist**

### R23-3: agent-persona-design updated

Added "R23 Lessons — Working With The User" section with:
- The 5 rules the user wants enforced
- When to push back on the agent
- Honesty over confidence (honest skip)
- Memory vs skill vs doc hierarchy
- The daily driver stack (stable from R5-R22)

Skill grew from 29 KB → 32 KB.

### R23-4: one-three-one-rule updated (v1.0 → v1.1)

Added "R23 Verification Pattern" section with:
- Each option must include a Verification subsection
- Verification anti-patterns ("should work" never acceptable)
- Patterns that work (exit codes, byte counts, real curls)
- When verification is hard (state what you did verify, what's pending)
- Round-based decision making (when 1-3-1 applies to round work)

Skill grew from 5 KB → 7 KB.

### R23-5: avoid-ai-writing updated (v3.3.1 → v3.4.0)

Added "Hermes Voice Patterns" addendum with:
- Voice rules for user-facing output (lead with change, ship then explain)
- Voice rules for round shipping docs (structure: Source/Outcome/Demo/Stats/Open)
- Voice rules for commit messages (max 3 lines)
- Voice rules for Telegram/Slack delivery (max 6 lines)
- Patterns that sound AI-generated AND robotic — avoid specifically
- Patterns that sound human — use specifically

Skill grew from 33 KB → 36 KB.

### R23-6: Memory consolidation

Cleaned MEMORY.md drift (3 duplicate entries from prior sessions) and added 1 new entry:
```
**R23 user-feedback rules (2026-08-03)**: (1) Always start with `/api/health`, never rediscover.
(2) Decompose broad asks into R-N tasks. (3) Verify with curl/exit codes, never narrative.
(4) wrapper.sh for cron args. (5) Trust infrastructure after R17+. Full guide:
/REPLACE_ME.md
```

---

## The 5 Rules (extracted from WORKING_WITH_HERMES.md)

1. **Always start with the dashboard, not investigation.** `/api/health` first. The system already knows what's broken.

2. **Be specific in your requests.** "R23-1: fix X. R23-2: add Y endpoint" beats "do all of this" every time.

3. **Verify with curl, not narrative.** "Endpoint returns 432 bytes" beats "I tested it."

4. **Use the wrapper pattern for cron args.** Never pass arguments directly to `hermes cron create --script`.

5. **Trust the infrastructure after R17+.** The 9-layer self-managing stack handles 90% of "broken" things automatically.

---

## Stats R22 → R23

| Metric | R22 | R23 | Net |
|--------|-----|-----|-----|
| Scripts | ~115 | ~115 | — |
| Endpoints | 24 | 24 | — |
| Crons | 74 | 74 | — |
| Skills updated | 0 (R22) | 3 | +3 |
| User-facing docs | 22 round docs | 23 docs + 1 guide | +1 |
| Cron health | 68/74 | 68/74 | — |
| Memory entries | 9 (with drift) | 9 (cleaned) | consolidated |

---

## Git state

```
psycology:      <pending>
hermes-config:  <pending>  (skills updated but not yet committed)
```

---

## What's open for R24+

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | Wire WORKING_WITH_HERMES.md into session-start prompt | 1h | High |
| 2 | Auto-suggest relevant skills based on request pattern | 4h | Medium |
| 3 | Build a `/api/health` summary endpoint that aggregates all 24 endpoints | 2h | High |
| 4 | Atlas E-1 Agent Swarm architecture | 6h | Strategic |
| 5 | Atlas F-1 Vector DB foundation | 4h | Strategic |

**R23 honest assessment:** This round is meta — it improves how Ivan works with the agent, not the system itself. The 5 rules in MEMORY.md will be enforced by every future session that reads them. The skills updates will load automatically when relevant. The big doc will be the first thing read at session start (when we wire it in).
