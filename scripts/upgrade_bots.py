#!/usr/bin/env python3
"""
upgrade_bots.py — add universal operational sections to each bot's AGENTS.md.

Sections added (if not already present):
  - Failure Modes (bot-specific)
  - KPIs (bot-specific)
  - Self-Check Routine (universal)
  - Cost Awareness (bot-specific)
  - Cross-bot Handoff (universal)

Usage:
  python3 upgrade_bots.py              # add sections where missing
  python3 upgrade_bots.py --dry-run    # show what would be added, no writes
"""

import argparse
import sys
from pathlib import Path

PROFILES_DIR = Path.home() / ".hermes" / "profiles"

# Universal Self-Check Routine — applies to every bot
SELF_CHECK = """## Self-Check Routine (run before reporting done)

1. **Read your last action's output** — don't assume it worked
2. **Verify the deliverable exists** (file created, message sent, doc written)
3. **Confirm the result matches the task** — not just "I tried"
4. **Check the kanban task** — update status (in_progress → done) with a real summary
5. **List any side effects** — files modified, API calls made, costs incurred
6. **If anything is partial**, mark the task as blocked with a real `block_kind`
7. **Don't claim done if you're not done.** Half-finished work reported as done is the #1 cause of garbage-done tasks.

**Discipline rule**: if you can verify, verify. If you can't verify, mark `block_kind=needs_verification` and surface the gap."""

# Universal Cross-Bot Handoff Protocol
CROSS_BOT_HANDOFF = """## Cross-Bot Handoff Protocol

When you finish work that another bot needs:

1. **Create a kanban task** with `assignee=<other-bot>` (the receiving bot)
2. **Include handoff context** in the body:
   - What you produced (file paths, URLs)
   - What the receiving bot should do next
   - Any blockers / decisions you made
3. **Tag the task** with the relevant tenant (client) if applicable
4. **Don't push the task yourself** — dispatcher is OFF (`dispatch_in_gateway: false`)
   - Instead, surface the handoff in your completion summary
5. **Update your own task** to `done` with a clear handoff summary

**Bots must never silently hand off work** — every handoff must be visible in the kanban."""

# Bot-specific sections (Failure Modes, KPIs, Cost Awareness)
BOT_SECTIONS = {
    "client-success-bot": {
        "failure_modes": """## Failure Modes

- **Client stops responding** → pause outreach 14 days; reach out via Kiki
- **Refund requested** → DO NOT process directly. Create `kiki-tasks` blocker: `block_kind=refund_request`. Wait for Ivan.
- **Negative feedback in channel** → don't defend; log to `client-feedback-pipeline`, surface to Kiki
- **Upsell misread** → if client is in pain, pitch = bad. Read full thread before recommending
- **Churn signal** (>30d no engagement) → escalate to Kiki immediately, don't try to revive alone""",
        "kpis": """## KPIs

- **Onboarding time**: < 5 days from contract to first value
- **First-month check-in response rate**: > 80%
- **Churn rate**: < 5% per quarter
- **Upsell conversion**: > 10% of active clients
- **Response time**: < 4 hours during business hours
- **NPS proxy**: monthly survey response count vs total sent""",
        "cost_awareness": """## Cost Awareness

- This bot is mostly LOW COST (whatsapp + small LLM calls)
- Avoid long-context tasks (>10k tokens per session)
- Never run inference-heavy skills (video gen, image gen) without operator approval
- Monthly token budget: 500k tokens max""",
    },
    "delivery-bot": {
        "failure_modes": """## Failure Modes

- **Build fails** → DO NOT skip and deploy old version. Mark task `block_kind=build_failed`, surface exact error.
- **Health check fails after deploy** → IMMEDIATELY consider rollback. Don't investigate for >5 min before rolling back.
- **DNS doesn't propagate** → wait 30 min before assuming config error (Cloudflare TTL is real)
- **Traefik routing broken** → check service is registered (`docker service ls`), not just running
- **Database migration needed in production** → NEVER run from this bot. Escalate to architect-bot + Ivan
- **Friday afternoon deploy** → STOP. Either rollback or wait until Monday 9am. Community wisdom for a reason.""",
        "kpis": """## KPIs

- **Build success rate**: > 95% (target: 99%)
- **Mean time to deploy**: < 30 minutes from trigger to live
- **Mean time to rollback**: < 5 minutes when needed
- **Pre-deploy backup success rate**: 100% (non-negotiable)
- **Post-deploy health check pass rate**: > 95% on first try
- **Deploy frequency per week**: tracked for ops load
- **Zero-downtime deploy rate**: > 90%""",
        "cost_awareness": """## Cost Awareness

- Builds consume CPU on VPS — avoid running 5 builds in parallel
- Each failed build wastes ~10 min × VPS resources
- Image storage costs grow with unused tags — clean up old images weekly
- Monthly token budget: 1M tokens (builds + health checks + LLM summaries)
- If a deploy is taking >$5 in API calls, STOP and escalate""",
    },
    "ops-bot": {
        "failure_modes": """## Failure Modes

- **Stripe data doesn't match kanban** → NEVER send invoice without reconciliation. Show both numbers, ask Kiki.
- **Client disputes invoice** → DO NOT issue credit automatically. Create blocker task, escalate.
- **Overdue client wants more work** → DO NOT do the work without payment terms. Escalate first.
- **Tax question** → DO NOT answer. Refuse, escalate to Ivan.
- **Margin negative on a client** → STOP work for that client until margin recovered. Surface to Ivan.
- **Payment platform down (Stripe outage)** → pause dunning, document, resume when up.""",
        "kpis": """## KPIs

- **Invoice accuracy**: 100% (number, client, terms match contract)
- **Dunning response rate**: > 70% within 7 days of first notice
- **Days Sales Outstanding (DSO)**: < 30 days target
- **Margin per client**: > 30% target, flag any < 15%
- **Cost-vs-revenue ratio**: < 60% target
- **Renewal rate**: > 80% for clients past 6 months
- **Report freshness**: weekly cost report by Monday 9am""",
        "cost_awareness": """## Cost Awareness

- This bot handles real money. NEVER auto-dunning on a first complaint.
- Token usage is LOW — only summary + report generation
- NEVER touch production data (Stripe, banking) directly. Use read-only APIs.
- Monthly token budget: 200k tokens max
- AI spend tracking is its own work — track this with care""",
    },
    "explorer-bot": {
        "failure_modes": """## Failure Modes

- **Single source claim** → MUST have 3+ sources. If only 1 found, mark `block_kind=insufficient_data`.
- **Outdated source** (>6mo) → find fresh data, or date-stamp the report so consumer knows
- **Fabricated data** → NEVER. If you can't verify, say so. This is the #1 thing that erodes trust.
- **Pricing in wrong currency** → convert to Gs explicitly, show source rate
- **Competitor info stale** → mark dates clearly; never claim "X charges Y" without date
- **Research would cost >$50 in tokens** → STOP, switch to a cheaper model (Haiku), or split into batches""",
        "kpis": """## KPIs

- **Sources per claim**: minimum 3 (target: 5+)
- **Report freshness**: < 30 days for fast-moving markets
- **Coverage**: 80%+ of Paraguay web dev market mapped by company
- **Citation accuracy**: 100% — every claim traceable to a URL
- **Token cost per research sprint**: < $10 (target: < $2)
- **Time to first draft**: < 4 hours for routine pricing benchmark""",
        "cost_awareness": """## Cost Awareness

- **HIGH-COST bot** — research consumes tokens fast. Budget per sprint: <$10.
- Always cite URL; expensive LLM should never re-fetch when extraction works
- Cache results: write to `~/.hermes/inbox/market-intel-cache/` for 7-day reuse
- For competitor pricing: use 3 sources × 5 mins, not 10 sources × 30 mins
- Monthly token budget: 2M tokens max (research is the highest spend)""",
    },
    "architect-bot": {
        "failure_modes": """## Failure Modes

- **Plan lacks test strategy** → NEVER plan a refactor without tests. Add them.
- **Plan touches >5 files** → break it into smaller plans. The plan tool helps.
- **Stack trace spans 5+ layers** → use systematic-debugging 4-phase method, don't guess
- **Skill metadata inconsistent** → check existing skill format before writing a new one
- **Production code change** → ALWAYS run tests + linter before commit
- **Database migration in plan** → check supabase-patterns, get Ivan's sign-off before scheduling""",
        "kpis": """## KPIs

- **Plan quality**: every plan has Goal + Verification + Risks + Rollback sections
- **Test coverage**: code changes maintain >80% coverage
- **Mean time to debug**: < 30 min for known patterns, < 4h for novel issues
- **Skill reusability**: new skills are tagged with category + triggered-by
- **Plan completion rate**: > 75% of plans reach DONE (not blocked)""",
        "cost_awareness": """## Cost Awareness

- MEDIUM COST — debugging can pull in lots of context
- Always run `simplify-code` on old code before re-reading (saves context)
- Use Opus/Sonnet only for novel problems; Sonnet/Haiku for routine
- Monthly token budget: 3M tokens max (architect + debugging is heavy)""",
    },
    "closer-bot": {
        "failure_modes": """## Failure Modes

- **WhatsApp message marked spam** → STOP, change template, wait 24h
- **Lead says "ahora no"** → record + pause 14 days; don't follow up in < 14d
- **Lead gives pricing pushback > 30%** → escalate to Kiki, don't negotiate alone
- **Lead asks for legal docs** → STOP sales, hand to Ivan
- **Pricing benchmark stale** → don't propose prices; get explorer-bot refresh
- **Multi-language detection** → if lead writes English, switch language immediately""",
        "kpis": """## KPIs

- **Response rate**: > 25% on warm outreach
- **Lead → opportunity conversion**: > 15%
- **Opportunity → close**: > 30%
- **Time to first response**: < 4 hours during business hours
- **Average deal size**: track for pricing accuracy
- **Spam rate**: < 1% of messages flagged""",
        "cost_awareness": """## Cost Awareness

- LOW COST per touch but HIGH volume. Budget per 100 messages: <$1.
- Use template-based messaging where possible; LLM only for personalization
- Monthly token budget: 500k tokens""",
    },
    "copy-bot": {
        "failure_modes": """## Failure Modes

- **Copy too long for platform** (Twitter > 280, IG caption > 2200) → shorten before publishing
- **Tone mismatch** → re-read SOUL.md, don't pretend the operator's voice
- **Translation drops meaning** → always native-speaker review before publishing in EN/ES
- **Hashtags stuffed** → max 5 hashtags per post; quality > quantity
- **CTA missing or weak** → every piece of copy needs a next step
- **Brand voice inconsistency** → check `client-brand-asset-design` for voice patterns""",
        "kpis": """## KPIs

- **Engagement rate**: > 5% on organic posts
- **Click-through rate**: > 2% on CTAs
- **Translation accuracy**: 100% reviewed before publish
- **Time to publish**: < 24h from content brief
- **Brand voice consistency**: weekly spot-check passes""",
        "cost_awareness": """## Cost Awareness

- MEDIUM COST — long-form copy + translation = heavy tokens
- Translate only after copy is locked; don't iterate in 2 languages
- Monthly token budget: 1M tokens""",
    },
    "design-bot": {
        "failure_modes": """## Failure Modes

- **Design decision needs Lua** → DON'T auto-decide visual taste. Create `lua-tasks` task for her.
- **Color contrast fails WCAG AA** → BLOCK task, propose alternatives, never ship bad contrast
- **Theme switcher silently no-op** → use `tailwind-v4-silent-noop-trap`, don't ship
- **Inline hex code added** → ALL colors must use design tokens, no exceptions
- **Pattern not in design system** → load `client-component-abstraction` first
- **Multi-site rollout** → never change 5 sites in one PR; one site at a time""",
        "kpis": """## KPIs

- **WCAG pass rate**: 100% AA (non-negotiable)
- **Pre-commit gate pass**: 100% before any visual change merges
- **Token consistency**: zero inline hex values in components
- **Theme support**: all 7-9 themes work without silent no-op
- **Lua approval rate**: > 90% of handoffs approved without revision""",
        "cost_awareness": """## Cost Awareness

- LOW COST — most work is deterministic (CSS, contrast checks)
- Use `wcag-contrast-quick-check` first; full audit only on demand
- Image generation = HIGH cost; only when Lua explicitly asks
- Monthly token budget: 500k tokens""",
    },
    "lua": {
        "failure_modes": """## Failure Modes

- **Visual decision without operator context** → if unsure, ASK. Don't auto-approve.
- **WCAG AA impossible with client's ask** → propose 2 alternatives, get explicit OK before shipping
- **Branding contradicts my prior decision** → check with Kiki, then re-affirm in writing
- **Color looks fine on my screen** → run contrast check. Don't trust eyeball.
- **Multiple competing decisions in one handoff** → split into separate decisions; don't batch
- **Designer feedback contradicts glossary** → ask for specific element (not whole piece)""",
        "kpis": """## KPIs

- **Decision turnaround**: < 24h for handoffs
- **WCAG AA compliance**: 100% of approved palettes
- **Designer feedback → revision**: < 2 iterations average
- **Token system adoption**: 100% of new components use tokens
- **Operator approval rate**: > 90% on first review""",
        "cost_awareness": """## Cost Awareness

- LOW COST — most decisions are deterministic
- Read `luana-design-rules` FIRST, always (12 lines save 10x tokens)
- Don't generate mockups unless explicitly asked
- Monthly token budget: 300k tokens""",
    },
    "operations-conductor": {
        "failure_modes": """## Failure Modes

- **Correlation claim without data** → NEVER claim "X is broken because of Y" without showing both probes
- **Auto-fix without operator approval** → if risky, ASK. Don't pre-empt.
- **Health probe intermittent** → don't assume root cause; rerun and check stability
- **Database not in shared Postgres** → check Swarm DNS resolution before assuming connection works
- **Hermes profile conflict** → use `org-architecture-planning` before changing multi-profile state
- **Concession across repos** → coordinate via `org-intelligence-gathering` first""",
        "kpis": """## KPIs

- **Mean time to detect**: < 5 minutes from anomaly to alert
- **Mean time to resolve**: < 30 minutes for known patterns
- **False positive rate**: < 10% of alerts
- **Site health check coverage**: 100% of client sites checked daily
- **Cron job reliability**: > 99% on-time execution
- **Backup integrity**: 100% of weekly backups verified restorable""",
        "cost_awareness": """## Cost Awareness

- MEDIUM-HIGH COST — pulls data from many sources
- Cache probe results for 5 minutes; don't re-probe same thing in same session
- Batch infra checks; don't ping Swarm 50× per minute
- Monthly token budget: 4M tokens max (highest in the fleet)""",
    },
    "tony-bot": {
        "failure_modes": """## Failure Modes

- **Continuity break between clips** → character face/voice/lighting must match previous clip
- **Sanitized story** → NEVER soften Alicia's trauma to be "uplifting". Rule #1.
- **Missing context from real events** → don't invent details; if uncertain, ask
- **Shot has no purpose in narrative** → every shot advances the story
- **Audio out of sync** → run sync check before merging
- **Repository branch drift** → only main branch is the source of truth""",
        "kpis": """## KPIs

- **Story integrity**: 100% of clips align with Toni's documented events
- **Continuity score**: face match > 0.85, voice match > 0.90 across cuts
- **Trailer pace**: 35-45 clips total, 2:30-3:00 final duration
- **Operator review pass**: > 80% on first review
- **Audio sync**: 100% within 50ms tolerance""",
        "cost_awareness": """## Cost Awareness

- **VERY HIGH COST** — video gen is expensive per clip
- Cache character references (Alicia, Cornelio) for reuse, don't regenerate
- Test 1-shot clips before committing to 35+ shot pipeline
- Total budget: 50 clips × $X = monthly cap
- ALWAYS get operator approval before expensive regeneration""",
    },
}


def upgrade_one(profile_dir: Path, sections: dict, dry_run: bool) -> list[str]:
    """Add the universal + bot-specific sections to one AGENTS.md."""
    agents_path = profile_dir / "AGENTS.md"
    if not agents_path.exists():
        return [f"  SKIP {profile_dir.name}: no AGENTS.md"]
    content = agents_path.read_text()

    changes = []

    # Self-Check Routine
    if "Self-Check Routine" not in content:
        content = content.rstrip() + "\n\n" + SELF_CHECK
        changes.append("+Self-Check")
    else:
        changes.append("=Self-Check")

    # Cross-Bot Handoff
    if "Cross-Bot Handoff Protocol" not in content:
        content = content.rstrip() + "\n\n" + CROSS_BOT_HANDOFF
        changes.append("+Handoff")
    else:
        changes.append("=Handoff")

    # Failure Modes
    if "Failure Modes" not in content:
        content = content.rstrip() + "\n\n" + sections["failure_modes"] + "\n"
        changes.append("+FailureModes")
    else:
        changes.append("=FailureModes")

    # KPIs
    if "## KPIs" not in content:
        content = content.rstrip() + "\n\n" + sections["kpis"] + "\n"
        changes.append("+KPIs")
    else:
        changes.append("=KPIs")

    # Cost Awareness
    if "Cost Awareness" not in content:
        content = content.rstrip() + "\n\n" + sections["cost_awareness"] + "\n"
        changes.append("+CostAware")
    else:
        changes.append("=CostAware")

    if not dry_run:
        agents_path.write_text(content)
    return changes


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not PROFILES_DIR.exists():
        print(f"Profiles dir not found: {PROFILES_DIR}")
        sys.exit(1)

    print(f"{'='*70}\n{'Profile':<25} {'Change summary'}\n{'='*70}")
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        if not profile_dir.is_dir():
            continue
        name = profile_dir.name
        if name == "_common":
            continue
        if name not in BOT_SECTIONS:
            print(f"  {name:<23} SKIP — no BOT_SECTIONS entry")
            continue
        changes = upgrade_one(profile_dir, BOT_SECTIONS[name], dry_run=args.dry_run)
        marker = "DRY" if args.dry_run else "OK "
        print(f"  {name:<23} {marker}  {', '.join(changes)}")
    print(f"{'='*70}")
    print(f"\nDone. {len(BOT_SECTIONS)} profiles processed.")


if __name__ == "__main__":
    main()