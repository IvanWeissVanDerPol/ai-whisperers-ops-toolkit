# Working With Hermes — The Complete Guide

**Author**: Erebus · **For**: Ivan (and future you) · **Updated**: 2026-08-03

This is the **single document** that tells you how to get the most out of working with Hermes. Read this once, then re-read when you feel like the agent is being slow, drifting, or not using the right tools.

---

## TL;DR — The 5 Rules

1. **Always start with the dashboard, not investigation.** `/api/health` first. The system already knows what's broken.
2. **Be specific in your requests.** "R23-1: fix X. R23-2: add Y endpoint" beats "do all of this" every time.
3. **Verify with curl, not narrative.** "Endpoint returns 432 bytes" beats "I tested it."
4. **Use the wrapper pattern for cron args.** Never pass arguments directly to `hermes cron create --script`.
5. **Trust the infrastructure after R17+.** The 9-layer self-healing + quality stack handles 90% of "broken" things automatically.

If you remember nothing else, remember those 5.

---

## What's Actually Built (the Infrastructure Map)

After R5-R22 (~17 days, 22 rounds), the system has 9 self-managing layers, 24 dashboard endpoints, 74 crons, 115 scripts, and 10 registered prompts. **You do not need to remember any of these individually** — but knowing they exist lets you ask Hermes the right questions.

### The 9-Layer Self-Managing Stack

| Layer | What | When | Verifies |
|-------|------|------|----------|
| 1. cron_health | Detects broken crons | Every 30 min | /api/health |
| 2. cron_self_heal | Auto-repairs with cost_router | Daily 04:00 | /api/orchestration |
| 3. cron_auto_disable | Disables after 5 consecutive failures | Daily 04:30 | /api/health |
| 4. cost_router | Probes providers, finds cheapest working model | On demand | /api/cost-router/audit |
| 5. anomaly_detector | Flags cost spikes / error patterns | Daily 05:00 | /api/anomalies |
| 6. anomaly_auto_pause | Pauses crons costing > threshold | Daily 04:45 | /api/anomalies |
| 7. prompt_quality_daily | Quality scores per registered prompt | Daily 06:00 | /api/prompt-quality |
| 8. prompt_ab_daily | A/B experiment status | Daily 06:30 | /api/prompt-ab |
| 9. prompt_version_recorder | Real per-version trace attribution | On demand | /api/prompt-ab/quality |

### The 24 Dashboard Endpoints (live at port 8645)

Every endpoint is `GET /api/<name>` and returns JSON.

**Health & monitoring**:
- `/api/health` — overall system status
- `/api/cron` — cron list with health status
- `/api/anomalies` — today's detected anomalies
- `/api/orchestration` — last self-heal run digest
- `/api/anomaly-pause` — anomaly auto-pause state

**Cost & model**:
- `/api/cost-forecast` — end-of-month cost projection
- `/api/cost-router/audit` — which LLM crons are expensive
- `/api/usage` — token usage over time
- `/api/usage?days=N` — usage window

**Prompts**:
- `/api/prompts/<name>` — fetch a registered prompt
- `/api/prompt-quality` — trace → prompt linkage
- `/api/prompt-ab` — list active A/B experiments
- `/api/prompt-ab/compare` — compare 2 versions
- `/api/prompt-ab/promote` — auto-promote winner
- `/api/prompt-ab/quality` — per-version trace stats

**Traces & skills**:
- `/api/traces` — recent LLM call spans
- `/api/skills` — skill analytics
- `/api/quality` — quality gate state

**Crud**:
- `/api/gh-actions` — generate CI workflow
- `/api/evals` — eval suite status

(For full endpoint inventory, run `curl -s -u admin:hermes http://127.0.0.1:8645/` or read `dashboard_server.py:1-80`.)

---

## How To Talk To Hermes So It Works Better

### Rule 1: Make Requests Specific and Decomposable

❌ **Bad**: "do all of this and all relevant things"
❌ **Bad**: "analyze and improve everything"
❌ **Bad**: "build a comprehensive upgrade"

✅ **Good**: "Build R23-1 (write working-with-hermes.md), R23-2 (update 3 skills), R23-3 (commit + push). Verify each round ends with a number that goes up (docs created, skills updated, repo advanced)."

✅ **Good**: "R23-1: Investigate why cron X keeps failing. R23-2: Fix the root cause (not the symptom). R23-3: Add a /api/X endpoint so we don't rediscover next time."

The pattern that worked across R17-R22: **each round = 5-8 tasks, each task has a measurable output, the round ends with a verification step + commit.**

### Rule 2: Anchor Work In Existing Infrastructure

When you describe a problem, **always reference what the system already knows**.

❌ **Bad**: "Why is the cost so high?"
✅ **Good**: "Why does `/api/cost-router/audit` show `weekly-self-evolution` at $1.84? Check `/api/anomalies` for that prompt, then `/api/cost-router probe` to find the cheapest working model."

When the agent asks "should I check X or Y?", tell it which existing endpoint to use. Don't make the agent rediscover.

### Rule 3: Demand Verification, Not Narrative

Every change should end with one of these proofs:

| Type of change | Verification |
|----------------|--------------|
| New script | `python3 script.py` exit 0 + correct output |
| New endpoint | `curl -s -u admin:hermes http://127.0.0.1:8645/api/X | head -c 200` shows real JSON |
| New cron | `hermes cron list` shows it, `hermes cron run X` succeeds, last_run < 5 min |
| New prompt | `python3 prompt_registry.py get --name X --version v1` returns content |
| New skill | `skill_view(name='X')` shows frontmatter + content |
| Bug fix | Run it again + show the bad behavior is gone |

If the agent says "I implemented X" without showing one of these, push back.

### Rule 4: Don't Re-Decide Settled Things

The system has made many decisions over R5-R22. Re-deciding them wastes time and creates inconsistency.

Settled decisions (don't reopen without strong reason):
- **Daily driver model**: `MiniMax-M3` (free, works)
- **Cron arg pattern**: wrapper.sh containing `exec python3 /abs/path/script.py --args`
- **Commit pattern**: both repos, hermes-config local + psycology pushed
- **Self-heal window**: 04:00-06:00 UTC only (not midnight)
- **Cost routing priority**: cerebras/gpt-oss-120b > MiniMax-M3 > anthropic/claude-sonnet
- **Atlas items shipped**: 11/20 — only revisit if you're shipping an atlas item
- **Quality formula**: 100 - (error_rate × 40) - (cost_per_call × 5) - (p95/100 × 10)
- **Sidecar file**: `/root/.hermes/state/prompt_version_map.jsonl`
- **Endpoint password**: admin:hermes (basic auth on port 8645)

If you want to change one of these, **explicitly say so** ("let's revisit the daily driver model — the free tier is throttling").

### Rule 5: Use The Existing Skills

There are 200+ skills. The most useful ones for "working with Hermes":

| Skill | When to use |
|-------|-------------|
| `hermes-agent` | Anything about Hermes itself (config, profiles, cron, gateways) |
| `memory-display-censorship-workaround` | When memory tool shows truncation |
| `skill-view-guard` | When skill_view returns weird content |
| `session-search-patterns` | When searching past sessions |
| `prompt-quality-rubric` | When evaluating a prompt |
| `avoid-ai-writing` | When cleaning up AI-tells in client-facing text |
| `one-three-one-rule` | When asking for architecture decisions |
| `agent-persona-design` | When defining sub-personas |
| `hermes-dojo` | Continuous self-improvement patterns |
| `cost-report` | When analyzing spend |

The full list is in `~/.hermes/skills/SKILLS_INDEX.md`. The agent should auto-load relevant ones — but you can explicitly say "load X skill before answering."

---

## What To Do In Different Session Types

### Type 1: Infrastructure / "let's upgrade the system"

```
Step 1: Check current state
  → /api/health, /api/anomalies
  → ls scripts/cron, count crons

Step 2: Plan with todo
  → "R-N-1: build X, R-N-2: integrate Y, R-N-3: verify Z, R-N-4: commit"

Step 3: Build with parallel discovery
  → delegate_task (leaf, "scan for X")
  → delegate_task (leaf, "research how Claude Code does X")

Step 4: Wire each piece end-to-end
  → New script → test it → chmod +x
  → New cron → wrapper.sh → register with no_agent
  → New endpoint → restart dashboard → curl test

Step 5: Round-end verification
  → python3 cron_health.py --json → confirm count went up
  → curl all new endpoints → confirm all return JSON
  → write R-N doc → commit both repos
```

**Reference**: any R17-R22 doc (`REPLACE_ME.md` etc.).

### Type 2: Debugging Broken Things

```
Step 1: Dashboard says what's broken
  → /api/health, /api/anomalies, /api/cron (filter by error)

Step 2: Get trace-level detail
  → /api/traces (filter by session, model, error)
  → /api/cost-router/audit (if cost issue)
  → /api/prompt-quality (if quality issue)

Step 3: Apply the fix
  → For model issues: cost_router probe, then update jobs.json
  → For cost issues: anomaly_auto_pause or model swap
  → For quality issues: prompt_registry compare + v2

Step 4: Re-verify (don't trust the fix)
  → Trigger the cron manually
  → /api/health after the fix
  → If still broken: keep digging (don't claim "fixed" prematurely)

Step 5: Document the fix in the relevant doc
  → Don't lose the lesson in MEMORY.md unless it's stable
```

**Anti-pattern to avoid**: spending 30 minutes reading logs manually when `/api/anomalies` already shows what's wrong.

### Type 3: Building New Client Sites / Apps

```
Step 1: Use existing platform
  → Search for an existing client-site scaffold (`paragu-ai-client-clone` skill)
  → Or use a Next.js starter (`nextjs-docker-swarm-lightweight-dockerfile`)

Step 2: Plan content first
  → Use `client-content-production-brief` if you have voice notes
  → Or `client-intake-analysis` if you have transcripts

Step 3: Build, test, deploy
  → Don't reinvent — most pieces exist (Tailwind v4 system, Lang-Driven JSON, MCP, etc.)

Step 4: Client deliverables
  → Use `client-stakeholder-pack` for the final delivery package
```

### Type 4: Research / Investigation

```
Step 1: Parallel discovery
  → delegate_task (leaf) × 3-5 — each with a clear scope
  → e.g. "scan 100 GitHub repos for X pattern"
  
Step 2: Synthesize
  → Wait for all to complete (one consolidated message)
  → Categorize: HIGH/MEDIUM/LOW relevance
  → Surface trade-offs, don't hide them

Step 3: 3-layered outputs
  → Cheat sheet (5 min read)
  → Deep analysis (30 min read)
  → Per-item docs (deep dives)

Step 4: Save to a research/ subdir, not docs/ (research is ephemeral)
```

**Reference**: the Paragu-Auditor session (2026-06-10) shipped 100-repo research in 3 layered formats.

### Type 5: Quality / Prompt Improvements

```
Step 1: Find low-scoring prompts
  → /api/prompt-quality → look for red/yellow scores

Step 2: Register v2 of the prompt
  → prompt_registry.py register --name X --version v2 --content "..."

Step 3: Plan A/B
  → Edit cron to use v2 (50/50 split with v1 if you want)
  → Run for 1 week

Step 4: Check results
  → /api/prompt-ab/quality?name=X&days=7
  → prompt_ab_tester.py promote --name X

Step 5: Promote if winner
  → The script auto-tags v2 as stable if v2_score > v1_score × 1.1
```

---

## Common Patterns That Have Emerged

### Pattern: Round-Based Commits

Every "upgrade round" (R-N) follows this exact shape:

```
1. todo: R-N-1 through R-N-K
2. Each task = small unit (15-45 min)
3. Round-end verification (numbers go up)
4. Write cursor-loop-roundN-shipping.md
5. Copy to hermes-config/docs/ and psycology/docs/hermes-cursor-loop/
6. Commit both with "feat(R-N):" prefix
7. Push psycology (hermes-config stays local)
```

18 rounds followed this pattern. **Don't break it** — it works because it's predictable.

### Pattern: Watchdog Cron Semantics

All no_agent crons follow the R16 lesson:
- Exit 0 = "ran successfully, here's the output"
- Exit 1 = "alert — script broken"
- Non-zero + timeout = "alert — script broken or hung"

**The output is the signal, not the exit code's success/failure.** A cron that detects 5 anomalies and exits 0 is HEALTHY (it's doing its job). A cron that detects 0 anomalies and exits 1 is BROKEN.

### Pattern: Wrapper for Cron Args

Hermes cron scheduler searches for the **literal script name**. `--script "foo.py --bar"` creates a job that searches for `foo.py --bar` (which doesn't exist). The fix:

```bash
# foo_wrapper.sh
#!/usr/bin/env bash
exec python3 /root/.hermes/scripts/foo.py --bar
```

Then `--script foo_wrapper.sh`. This is in MEMORY.md as the "CRITICAL GOTCHA" — don't forget.

### Pattern: Parallel Discovery via delegate_task

For research / scanning / inventory tasks, use 3-5 leaf subagents in parallel:

```python
delegate_task(tasks=[
    {"goal": "scan /root/.hermes/scripts/ for X", "role": "leaf"},
    {"goal": "scan /root/psycology/ for Y", "role": "leaf"},
    {"goal": "research Z (web search)", "role": "leaf"},
])
```

Each subagent has its own context. You only see the final summary. This cuts discovery time from 30 min to 5 min.

### Pattern: Honest Skip vs Bad Skip

The infrastructure has 2 kinds of "skip":

- **Honest skip**: "I don't have enough data to decide." (R22 example: "candidate v2 has only 0 traces (need 20)")
- **Bad skip**: "I don't know what to do, so I'll fake a result." (NEVER do this)

Always demand honest skip. If the agent can't decide, it should say so with the exact reason.

---

## When To Push Back On The Agent

The agent (Erebus by default) tries to be proactive. That sometimes means it does things you didn't ask for. **Push back when:**

- It writes code without verifying it ran (`"Did this actually work? Show me the output."`)
- It adds features not in the round scope (`"That's R-N+1. Stay focused."`)
- It skips verification with `"should work"` instead of `"exit 0 confirmed"` (`"Run it and show me the output."`)
- It adds memory entries for ephemeral facts (`"Don't save that, it changes weekly."`)
- It claims "all done" without a commit (`"Show me the commit hash."`)

**Don't push back when:**

- It tells you something won't work (your fix might be wrong)
- It asks clarifying questions (that's free research)
- It surfaces trade-offs you didn't think about (valuable signal)

---

## When To Switch Personas

Erebus has 4 sub-personas via `/erebus`:

| Persona | When to use |
|---------|-------------|
| `dev` | Pure coding. Code-only mode, minimal chatter. |
| `ops` | Docker Swarm, Traefik, monitoring, VPS. |
| `research` | Market intel mode. Web search, scraping, competitive analysis. |
| `client` | Client-facing mode. Professional tone, Spanish-first. |

Default (no persona) = full Erebus. Switch with `/erebus dev` for code-heavy sessions where the user is technical. Switch with `/erebus client` when the agent needs to act as if it's speaking to a client.

---

## When To Use Memory vs Skill vs Doc

There's a hierarchy. Don't put things in the wrong place.

| What kind of fact | Where it goes |
|-------------------|---------------|
| Stable user preference ("likes concise responses") | MEMORY.md |
| Stable environment fact ("MiniMax-M3 daily driver") | MEMORY.md |
| Stable procedure ("use wrapper.sh for cron args") | MEMORY.md (as fact) or skill (as procedure) |
| Multi-step workflow (debug broken cron) | skill (load with skill_view) |
| One-time research finding (100-repo analysis) | research/ subdir, NOT memory |
| Atlas implementation plan | doc (docs/hermes-cursor-loop/) |
| Round shipping summary | doc (docs/hermes-cursor-loop/cursor-loop-roundN.md) |

**The test**: if you'd want to know this in 6 months, it's worth saving. If it's stale in a week, it's not.

---

## What To Do When Things Break (Quick Recovery)

| Symptom | First action |
|---------|--------------|
| Cron failing repeatedly | `/api/health` → `/api/anomalies` → `cost_router probe` |
| Agent seems "lost" | Tell it: "run `/api/health`, summarize the system state" |
| Memory tool returns errors | Load `memory-display-censorship-workaround` skill |
| Skill not loading | Load `skill-view-guard` skill |
| Want to undo something | `git log --oneline -10` then `git revert <hash>` |
| Need to find past session | `session_search(query="keywords from that session")` |
| Dashboard API not responding | `systemctl restart hermes-dashboard-api` |
| Agent seems to be hallucinating | `hermes doctor` |
| Budget exceeded | `/api/cost-forecast` → pause expensive crons via `cost_alert` |

---

## The 5-Minute Session Start Checklist

If you're starting a session and want to be effective fast, run this checklist:

1. **Read MEMORY.md** (your persistent notes) — 30 sec
2. **Read this doc** (working-with-hermes.md) — 3 min
3. **Ask the agent to run `/api/health` and summarize** — 1 min
4. **State your goal in 1 sentence + decompose into R-N tasks** — 1 min
5. **Tell the agent which verification to run at the end of each round** — 30 sec

Total: 6 minutes. Saves you 30 minutes of "where are we? what's broken?"

---

## The 1-Minute End-of-Session Checklist

Before you close a session:

1. Did the agent verify each round? (Look for curl output, exit codes, byte counts.)
2. Are the commits pushed? (psycology) / committed locally? (hermes-config)
3. Did the agent save things in the right places? (memory, skill, doc — not all 3)
4. Is there anything new to remember? (Stable facts only.)
5. Does the next session have what it needs? (Round doc, skills loaded, MEMORY updated.)

If any of these are no, push back before closing.

---

## What's NOT In This Doc

- **Round-by-round details**: each round has its own shipping doc (`cursor-loop-roundN-shipping.md`)
- **Skill-specific workflows**: load the skill itself
- **Atlas item specifics**: see `hermes-upgrade-atlas.md`
- **Past session archaeology**: use `session_search`

This doc is the **entry point**. From here, branch out as needed.

---

## Honoring The Work Already Done

22 rounds. ~17 days. 115 scripts. 24 endpoints. 74 crons. 10 prompts. 11/20 atlas items. 9-layer stack.

This is not a starting state. This is a mature system.

The next 22 rounds should be **leverage**, not rebuild. The question isn't "what should I build?" — it's "what existing thing should I compose to ship the next thing?"

That's the mindset. Work the system, don't fight it.

— Erebus, 2026-08-03
