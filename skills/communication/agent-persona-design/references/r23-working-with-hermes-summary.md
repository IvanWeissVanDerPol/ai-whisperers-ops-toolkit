# R23 Working-With-Hermes Summary — 2026-08-03

Reference companion to the agent-persona-design SKILL.md "R23 Lessons" section. This file captures the **distilled session-start protocol** so future sessions have a single load point for the user-feedback rules.

## Source Document

The full canonical guide is `/REPLACE_ME.md` (18 KB). This reference is the **indexed digest** — when a session needs the rules, load this; for full depth, follow the path to the canonical doc.

## The 5 Rules (verbatim, do not paraphrase)

1. **Always start with the dashboard, not investigation.** `/api/health` first. The system already knows what's broken.

2. **Be specific in requests.** "R23-1: fix X. R23-2: add Y endpoint" beats "do all of this."

3. **Verify with curl, not narrative.** "Endpoint returns 432 bytes" beats "I tested it."

4. **Use the wrapper pattern for cron args.** Always `wrapper.sh` containing `exec python3 /abs/path/script.py --args`.

5. **Trust the infrastructure after R17+.** The 9-layer stack handles 90% of "broken" things automatically.

## When The User Pushes Back

The agent (Erebus by default) sometimes does things the user didn't ask for. **Push back when:**
- Writes code without verifying it ran → "Did this actually work? Show me the output."
- Adds features not in scope → "That's R-N+1. Stay focused."
- Skips verification with "should work" → "Run it and show me the output."
- Adds memory entries for ephemeral facts → "Don't save that."
- Claims "all done" without a commit → "Show me the commit hash."

**Don't push back when:**
- Agent says something won't work (user's fix might be wrong)
- Agent asks clarifying questions
- Agent surfaces trade-offs

## Honest Skip Pattern

The user values honest skip over fake success:
- **Honest skip**: "I don't have enough data to decide." (R22: "candidate v2 has 0 traces (need 20)")
- **Bad skip**: "I don't know what to do, so I'll fake a result." (NEVER do this)

## Memory vs Skill vs Doc

| What | Where |
|------|-------|
| Stable user preference | MEMORY.md |
| Stable environment fact | MEMORY.md |
| Stable procedure (one-line fact) | MEMORY.md |
| Multi-step workflow | skill (load with skill_view) |
| One-time research finding | research/ subdir, NOT memory |
| Atlas implementation plan | doc (docs/hermes-cursor-loop/) |
| Round shipping summary | doc (cursor-loop-roundN-shipping.md) |

**Test**: if user would want to know this in 6 months, save it. If stale in a week, don't.

## The Daily Driver Stack (R5-R22 stable)

| Component | Value |
|-----------|-------|
| Daily driver model | `MiniMax-M3` (free, works) |
| Cron arg pattern | `wrapper.sh` containing `exec python3 /abs/path/script.py --args` |
| Commit pattern | Both repos: hermes-config local + psycology pushed |
| Self-heal window | 04:00-06:00 UTC only |
| Cost routing priority | cerebras/gpt-oss-120b > MiniMax-M3 > anthropic/claude-sonnet |
| Endpoint auth | admin:hermes (basic auth on port 8645) |

If a new persona deviates, document the deviation explicitly.

## Why This Reference Exists

R23 was a **meta round** — it didn't add new infrastructure; it improved how the user works with the agent. The 5 rules are first-class workflow corrections the user demanded. Without a skill anchor, these rules lived only in MEMORY.md, where they could drift or be missed by sessions that don't load memory early.

This reference + the SKILL.md R23 Lessons section + the canonical doc = three checkpoints that ensure the rules survive across sessions, profile changes, and skill curator cycles.

## Related Files

- **SKILL.md** — agent-persona-design skill, has the R23 Lessons section
- **WORKING_WITH_HERMES.md** — canonical guide (psycology/docs/hermes-cursor-loop/)
- **MEMORY.md** — has 5 user-feedback rules summary entry
- **cursor-loop-round23-shipping.md** — R23 shipping doc with full context

When updating the rules, update all 4 to keep them in sync.
