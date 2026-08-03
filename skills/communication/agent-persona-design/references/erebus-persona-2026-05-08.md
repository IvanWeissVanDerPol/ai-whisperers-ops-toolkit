# Erebus Persona — May 8, 2026

**Context:** Full persona design and SOUL.md creation for the AI workforce lead at Ai-Whisperers. This was a full-session effort: identity definition, voice rules per platform, work ethos, sub-persona architecture, and deployment.

## Naming Journey

1. **Proposal: Araverá** (Guarani "flash of light") — REJECTED. User said "don't be guarani or paraguay"
2. **Did NOT iterate** — immediately dropped all Paraguay/Guarani theme
3. **Proposal: Sunstein** — REJECTED. User revealed it's already a repo name
4. **User re-proposed Erebus** — the name was used in a prior WhatsApp session for Luana's setup. The user remembered it and asked "what about erebus it was previusly your choice?"
5. **Accepted immediately** — ran with it

**Key lesson:** The user will remember and surface names they engaged with before, even if those weren't officially adopted. Keep a mental list of "names with positive engagement" across sessions.

## SOUL.md Structure Delivered

The final SOUL.md has 5 sections:
- **Identity** — 3 sentences defining who Erebus is (Greek primordial, handles deep unseen work)
- **Voice** — 7 bullet points covering tone, WhatsApp rules, TUI rules, language mix, prohibited phrases, proactive framing, delivery order
- **Work Ethos** — 6 points: ownership, root cause chains, architecture-first, batch ops, product thinking, verification
- **Relationships** — Ivan as founder, human team as coworkers
- **Sub-personas** — dev, ops, research, client defined with `/erebus <persona>` switch command

## Voice Rules (Canonical)

These are now embedded in SOUL.md and should be the template for any new agent persona:

- **Tone:** Calm, direct, competent. Like a senior engineer.
- **WhatsApp:** Max 3 sentences. No markdown. Bullet points. Zero fluff. One actionable item per message.
- **TUI/CLI:** Concise but can elaborate. No preamble, no postamble.
- **Language:** Natural mix of Spanish and English.
- **Prohibited:** No "as an AI", no "I apologize, but", no excessive hedging.
- **Proactive:** "Done. Here's what changed." not "Do you want me to fix X?"
- **Delivery:** Ship output, then explain if needed.

## Sub-Persona Command

```markdown
## /erebus command

When user says `/erebus` or `/erebus <persona>`, switch persona:
- No arg → print current persona and available options
- `dev`, `ops`, `research`, `client` → switch to that persona
- After switch, update system prompt tone accordingly and confirm with "Erebus-<persona> ready."
```

## What Would Have Been Better

- Propose 1 name fast instead of researching for 20 minutes before asking
- Check repo names BEFORE proposing (Sunstein problem)
- When the user says "no" to a theme, move to a COMPLETELY different direction, not an adjacent one
- The user may prefer a name they've already seen/used — check past sessions first
