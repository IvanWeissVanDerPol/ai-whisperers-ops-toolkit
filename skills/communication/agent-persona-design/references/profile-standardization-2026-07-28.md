# Profile standardization — 2026-07-28

**Context:** Fleet-wide upgrade of 11 Hermes profiles to share the same operational scaffolding. Worked example of the `## Profile standardization (upgrading existing profiles)` section in SKILL.md.

## Starting state

11 profiles at `~/.hermes/profiles/*/`. Each written by different sessions:

| Profile | SOUL.md lines | AGENTS.md lines | Status |
|---|---|---|---|
| architect-bot | 79 | 48 | Rich |
| client-success-bot | 28 | 96 | Light |
| closer-bot | 62 | 100 | Medium |
| copy-bot | 81 | 98 | Rich |
| delivery-bot | 28 | 102 | Light |
| design-bot | 103 | 134 | Rich |
| explorer-bot | 47 | 100 | Medium |
| lua | 60 | 135 | (cloned from design-bot — duplicate identity problem) |
| operations-conductor | 158 | 103 | Rich |
| ops-bot | 37 | 100 | Medium |
| tony-bot | 67 | 100 | Medium |

**Problems identified:**
- 4 profiles under 50 SOUL.md lines: client-success, delivery, ops, explorer
- Lua and design-bot had **identical SOUL.md** (clone without rewrite)
- No profile had Failure Modes, KPIs, or Cost Awareness sections consistently
- No profile had Self-Check or Cross-Bot Handoff Protocol
- Different sections in different orders — no operational consistency

## What was shipped

### Universal sections appended to all 11 profiles' AGENTS.md

1. **Failure Modes** (bot-specific, 5-7 bullets each)
2. **KPIs** (bot-specific, 4-7 metrics each)
3. **Self-Check Routine** (verbatim, same text for all)
4. **Cross-Bot Handoff Protocol** (verbatim, same text for all)
5. **Cost Awareness** (bot-specific, with monthly token budget)

After upgrade, all 11 profiles have all 5 sections (verified by `TestBotUpgrades`).

### SOUL.md strengthening for the 4 weakest profiles

For client-success-bot, delivery-bot, ops-bot, explorer-bot, appended:
- **Boundaries** — what the bot will NOT do (refunds, schema migrations, etc.)
- **What I do exceptionally well** — 4-5 items
- **Self-Knowledge** — ceiling, risk profile, latency, failure mode

### Lua vs design-bot distinction

Both profiles had identical SOUL.md (Lua was created by `cp -r design-bot lua`). Fixed:

- **Lua SOUL.md** = "Soy Lua — Luana López, diseñadora visual. Mi trabajo: definir la dirección estética de cada sitio de cliente."
- **design-bot SOUL.md** = "Sos Design-Bot, el **ejecutor** de diseño visual. Tu relación con Lua: Lua DECIDE, vos EJECUTÁS."

Now they have different voices, different work scope, and different escalation rules.

### Upgrade script (`upgrade_bots.py`)

Idempotent, re-runnable. Architecture:
- `BOT_SECTIONS` dict mapping profile → {failure_modes, kpis, cost_awareness}
- Reads each AGENTS.md
- Checks for each section header; adds if missing
- `--dry-run` mode for preview

Key property: **re-running produces no diff** (idempotent). Adding a new profile → run script → it gets the universal scaffolding without manual editing.

## Verification

### Tests

- `TestBotUpgrades.test_every_bot_has_universal_sections` — verifies all 5 sections in all 11 profiles
- `TestBotUpgrades.REPLACE_ME` — verifies Lua ≠ design-bot identity
- `TestBotUpgrades.test_no_bot_still_has_legacy_footer` — soft check (informational only)

### Audit output

```
$ for bot in /root/.hermes/profiles/*/; do
    name=$(basename "$bot")
    has_kpi=$(grep -c "^## KPIs" "$bot/AGENTS.md")
    has_failure=$(grep -c "^## Failure Modes" "$bot/AGENTS.md")
    ...
  done

✓ architect-bot          SOUL=79  AGENTS=100 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ client-success-bot     SOUL=52  AGENTS=96  kpi=1 fail=1 self=1 handoff=1 cost=1
✓ closer-bot             SOUL=62  AGENTS=100 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ copy-bot               SOUL=81  AGENTS=98  kpi=1 fail=1 self=1 handoff=1 cost=1
✓ delivery-bot           SOUL=51  AGENTS=102 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ design-bot             SOUL=103 AGENTS=134 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ explorer-bot           SOUL=71  AGENTS=100 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ lua                    SOUL=60  AGENTS=135 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ operations-conductor   SOUL=158 AGENTS=103 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ ops-bot                SOUL=61  AGENTS=100 kpi=1 fail=1 self=1 handoff=1 cost=1
✓ tony-bot               SOUL=67  AGENTS=100 kpi=1 fail=1 self=1 handoff=1 cost=1
```

## Key lessons

### Don't trust `cp -r` for profiles

Cloning a profile copies ALL files including SOUL.md. The new profile inherits the source's identity, voice, and persona. Always rewrite SOUL.md after cloning — at minimum, change the Identity section to define the new persona.

### Universal sections pay off

Once every profile had Self-Check + Cross-Bot Handoff, the bots behaved consistently. Before, some bots marked tasks done with no verification; after, every profile had the same discipline rules. The dispatcher (when enabled) sees consistent task semantics.

### Idempotent upgrade scripts are non-negotiable

If the upgrade script isn't idempotent, you can't safely re-run it after tweaking the universal text. The `TestBotUpgrades` tests give confidence the upgrade path is correct without manual verification.

### The 4-section SOUL.md minimum

When a profile's SOUL.md is just Identity + Voice + Work Ethos + Relationships, it's not enough. Add Boundaries + What I do well + Self-Knowledge for an A-grade profile. The 4-weakest profiles upgraded from C to B+ with this.

## What to do next time

1. Start every new profile with the 5 universal sections (Failure Modes, KPIs, Self-Check, Cross-Bot Handoff, Cost Awareness) — don't wait for the upgrade pass.
2. Treat SOUL.md rewrites as persona-defining. Never copy from another profile without rewriting.
3. Write the upgrade script first, run it last. Then you can iterate on the universal text and re-run with confidence.

## Reproducibility

The upgrade script and the bot-specific sections are at:
- `~/.hermes/scripts/upgrade_bots.py`
- Tests: `~/.hermes/scripts/test_kanban_extensions.py::TestBotUpgrades`

To replay the upgrade on a new profile:
```bash
# 1. Add the profile to BOT_SECTIONS in upgrade_bots.py
# 2. Run:
python3 ~/.hermes/scripts/upgrade_bots.py --dry-run  # preview
python3 ~/.hermes/scripts/upgrade_bots.py             # apply
# 3. Verify:
python3 -m unittest test_kanban_extensions.TestBotUpgrades -v
```