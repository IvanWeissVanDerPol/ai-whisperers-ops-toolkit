#!/usr/bin/env python3
"""generate-agents-md.py — generate per-profile AGENTS.md operational playbooks.

Pattern from r/hermesagent "SOUL.md AND AGENTS.md" wisdom:
  AGENTS.md = operational playbook (commands, when to use what, escalation)
  SOUL.md = identity/voice/philosophy

Each profile gets a customized AGENTS.md with:
  - Role and primary tasks
  - Common commands/workflows for that role
  - Escalation rules (when to ask the user vs. proceed)
  - Cross-references to relevant skills/bundles
  - Known anti-patterns
"""
import os

PROFILES_DIR = os.path.expanduser("~/.hermes/profiles")
TEMPLATES = {
    "architect-bot": {
        "role": "Code architect and infrastructure engineer",
        "primary_tasks": [
            "Review code architecture and design patterns",
            "Plan multi-step refactors and migrations",
            "Debug complex distributed-system issues",
            "Write technical specifications",
        ],
        "commands": [
            ("/release-prep", "Plan a release: CHANGELOG, rollout strategy, FAQ"),
            ("Plan a complex refactor", "Use execplan-skill + writing-plans"),
            ("Debug a stack trace", "Use systematic-debugging"),
            ("Write a new skill", "Use the skills/ subdirectory + SKILL.md format"),
        ],
        "skills_priority": ["execplan-skill", "systematic-debugging", "writing-plans", "subagent-driven-development", "test-driven-development"],
        "escalate_when": [
            "Change affects 5+ files",
            "Touches production infrastructure",
            "Modifies billing/payment code",
            "Touches auth or secrets handling",
        ],
        "anti_patterns": [
            "Don't refactor without writing tests first",
            "Don't change 5 files in one step (community: 'one change at a time')",
            "Don't merge without review",
        ],
    },
    "closer-bot": {
        "role": "Sales closer — WhatsApp outreach and proposal writer",
        "primary_tasks": [
            "Draft WhatsApp messages for warm leads",
            "Build Paraguay-market pricing proposals",
            "Handle sales objections",
            "Convert leads to signed contracts",
        ],
        "commands": [
            ("/client-onboard", "Full client onboarding: pricing, proposal, contract, WhatsApp intro"),
            ("Draft a follow-up message", "Use paraguay-whatsapp-ghostwriting"),
            ("Handle a price objection", "Use pyme-paraguay-objections"),
            ("Build a proposal", "Use client-pricing-proposals"),
        ],
        "skills_priority": ["paraguay-whatsapp-ghostwriting", "client-pricing-proposals", "pyme-paraguay-objections", "client-contracts", "predictable-revenue"],
        "escalate_when": [
            "Lead mentions legal issues",
            "Pricing under $200 (use cheaper channels)",
            "Lead asks for refund or complaint",
            "Volume > 10 messages/hour (need automation review)",
        ],
        "anti_patterns": [
            "Don't send pricing without consulting client-pricing-proposals skill first",
            "Don't promise features that don't exist",
            "Don't use English with Paraguay Spanish-speaking clients",
        ],
    },
    "copy-bot": {
        "role": "Content writer and copywriter",
        "primary_tasks": [
            "Write blog posts and landing pages",
            "Create social media content",
            "A/B test copy variants",
            "Apply CRO principles",
        ],
        "commands": [
            ("Write a landing page", "Use made-to-stick + storybrand-messaging + cro-methodology"),
            ("Write a sales email", "Use influence-psychology + one-page-marketing"),
            ("Write a viral post", "Use contagious + copywriting/sales-page-ux"),
            ("Audit existing copy", "Use scorecard-marketing + obviously-awesome"),
        ],
        "skills_priority": ["made-to-stick", "storybrand-messaging", "cro-methodology", "hooked-ux", "scorecard-marketing"],
        "escalate_when": [
            "Copy targets a regulated industry (health, finance, legal)",
            "Translation between languages (use client-content-audit)",
            "Brand voice disputes (use copy-bot + Paraguay client feedback)",
        ],
        "anti_patterns": [
            "Don't write without checking the client's existing voice (use user memory)",
            "Don't use AI-writing patterns (audit with avoid-ai-writing)",
            "Don't publish without 2+ revisions",
        ],
    },
    "delivery-bot": {
        "role": "Site delivery engineer — deploys and ships client sites",
        "primary_tasks": [
            "Deploy Next.js client sites",
            "Audit site health and performance",
            "Ship features end-to-end",
            "Roll back bad deploys",
        ],
        "commands": [
            ("Deploy a site", "Use nextjs-docker-swarm + deployment docs"),
            ("Audit a site", "Use client-site-inventory + site-healthchecks"),
            ("Roll back a deploy", "Use swarm-service-recovery"),
            ("Performance audit", "Use web-performance-audit"),
        ],
        "skills_priority": ["nextjs-docker-swarm", "nextjs-content-audit", "client-site-inventory", "site-healthchecks", "refactoring-ui"],
        "escalate_when": [
            "Production site is down (use incident-commander)",
            "Database migration needed (use supabase-patterns)",
            "Multi-day task needed (use autonomous-multi-phase-execution)",
        ],
        "anti_patterns": [
            "Don't deploy on Friday afternoon (community wisdom)",
            "Don't skip pre-deploy backup",
            "Don't use --force in production",
        ],
    },
    "client-success-bot": {
        "role": "Client success — retention and follow-up",
        "primary_tasks": [
            "Send follow-up messages to existing clients",
            "Track client satisfaction",
            "Identify upsell opportunities",
            "Process client feedback",
        ],
        "commands": [
            ("Send a check-in", "Use client-feedback-pipeline"),
            ("Process a complaint", "Use client-channel-binding"),
            ("Identify upsell", "Use client-contracts + Paraguay pricing benchmarks"),
        ],
        "skills_priority": ["client-feedback-pipeline", "client-channel-binding", "client-contracts", "client-pricing-proposals"],
        "escalate_when": [
            "Client threatens to leave",
            "Refund request",
            "Legal issue mentioned",
        ],
        "anti_patterns": [
            "Don't send more than 1 message/week to a single client",
            "Don't pitch upsells in the first 30 days",
        ],
    },
    "explorer-bot": {
        "role": "Researcher — market intel and competitive analysis",
        "primary_tasks": [
            "Research new markets and competitors",
            "Build pricing benchmarks",
            "Identify industry trends",
            "Synthesize multi-source research",
        ],
        "commands": [
            ("/research-sprint", "Full research workflow: market intel, pricing, competitors"),
            ("Research a company", "Use domain-intel + repo-enhancement-research"),
            ("Build a pricing benchmark", "Use ai-whisperers-pricing-benchmark + py-market-research"),
            ("Multi-source synthesis", "Use multi-source-research"),
        ],
        "skills_priority": ["multi-source-research", "ai-whisperers-pricing-benchmark", "domain-intel", "py-market-research", "repo-enhancement-research"],
        "escalate_when": [
            "Research would cost >$50 in API tokens (use a cheaper model)",
            "Findings need to be cited externally (verify sources)",
        ],
        "anti_patterns": [
            "Don't cite a single source — always 3+",
            "Don't fabricate pricing data",
            "Don't use outdated (>6mo) sources for fast-moving markets",
        ],
    },
    "ops-bot": {
        "role": "Finance and operations",
        "primary_tasks": [
            "Generate and track invoices",
            "Process dunning for overdue accounts",
            "Build company health audits",
            "Manage Paraguay-specific compliance",
        ],
        "commands": [
            ("Generate an invoice", "Use ai-whisperers-invoicing"),
            ("Process dunning", "Use dunning-automation"),
            ("Company health audit", "Use ai-whisperers-company-audit"),
            ("Sunstone report", "Use ai-whisperers-sunstone-report"),
        ],
        "skills_priority": ["ai-whisperers-invoicing", "dunning-automation", "ai-whisperers-company-audit", "ai-whisperers-sunstone-report"],
        "escalate_when": [
            "Invoice > $5000 (manual review)",
            "Dispute or chargeback",
            "Tax-related question",
        ],
        "anti_patterns": [
            "Don't send invoices without client-pricing-proposals verification",
            "Don't auto-dunning without escalation rules",
        ],
    },
    "operations-conductor": {
        "role": "Infrastructure operations conductor",
        "primary_tasks": [
            "Monitor Hermes system health",
            "Manage cron jobs and automations",
            "Run cleanup and backup scripts",
            "Coordinate MCP and plugin maintenance",
        ],
        "commands": [
            ("Daily health check", "Runs at 09:00 — daily-healthcheck.py"),
            ("Weekly MCP version check", "Runs Monday 08:00 — mcp-version-check.py"),
            ("Weekly log cleanup", "Runs Sunday 04:00 — cleanup-logs.py"),
            ("Daily config backup", "Runs 03:00 — backup-config.sh"),
            ("Run self-heal", "python3 ~/.hermes/scripts/self-heal.py"),
            ("Pre-curator snapshot", "bash ~/.hermes/scripts/pre-curator-snapshot.sh"),
        ],
        "skills_priority": ["execplan", "hermes-gateway-ops", "docker-swarm-infrastructure", "lightweight-vps-ops", "cron-cost-guard"],
        "escalate_when": [
            "Disk >80% (alert immediately)",
            "Token expiry warning (alert immediately)",
            "Multiple cron jobs failing",
            "OAuth token expired",
        ],
        "anti_patterns": [
            "Don't touch cron jobs on a Friday",
            "Don't apply curator changes without pre-snapshot",
            "Don't ignore token-expiry warnings",
        ],
    },
    "tony-bot": {
        "role": "Creative director (Toni's video production)",
        "primary_tasks": [
            "Direct video shoots (story, shot list, score)",
            "Score and edit existing footage",
            "Write character continuity bibles",
            "Produce production bibles for new projects",
        ],
        "commands": [
            ("Start a new project", "Use PRODUCTION-BIBLE pipeline (story → shot list → continuity)"),
            ("Score existing footage", "Use hyperframes-pipeline"),
            ("Generate cover art", "Use image_gen"),
            ("Generate test video", "Use video_gen/fal or video_gen/xai"),
        ],
        "skills_priority": ["hyperframes-pipeline", "creative-consultation", "baoyu-comic", "animation-interaction-inventory", "pixel-art"],
        "escalate_when": [
            "Story direction needs Toni's input (don't auto-direct)",
            "Music licensing questions",
            "Actor/contract issues",
        ],
        "anti_patterns": [
            "Don't sanitize the story (creative rule #1)",
            "Don't use AI voice for the score (Toni's voice is the score)",
            "Don't auto-edit without the director's review",
        ],
    },
}


def render_agents_md(profile_name, tmpl):
    """Render a single AGENTS.md from a template dict."""
    skills_md = "\n".join(f"  - {s}" for s in tmpl["skills_priority"])
    tasks_md = "\n".join(f"  - {t}" for t in tmpl["primary_tasks"])
    commands_md = "\n".join(
        f"  - **{c[0]}** — {c[1]}" if c[0].startswith("/") else f"  - {c[0]}: {c[1]}"
        for c in tmpl["commands"]
    )
    escalate_md = "\n".join(f"  - {e}" for e in tmpl["escalate_when"])
    anti_md = "\n".join(f"  - {a}" for a in tmpl["anti_patterns"])

    return f"""# AGENTS.md — {profile_name}

> Operational playbook for the **{profile_name}** profile.
> See `SOUL.md` for identity/voice. This file is the *how*.

## Role
{tmpl["role"]}

## Primary Tasks
{tasks_md}

## Common Commands
{commands_md}

## Skills (priority order)
{skills_md}

## Escalate When
{escalate_md}

## Anti-Patterns (don't do these)
{anti_md}

## Cross-references

- `SOUL.md` — identity and voice for this profile
- `config.yaml` — model, tools, security level
- `~/.REPLACE_ME.md` — applies to all profiles
- `~/.hermes/skill-bundles/` — slash-command bundles
- `~/.hermes/scripts/` — operational scripts

---
*Generated by `~/.hermes/scripts/generate-agents-md.py`. Edit freely — the file is yours.*
"""


def main():
    for prof_name, tmpl in TEMPLATES.items():
        prof_dir = os.path.join(PROFILES_DIR, prof_name)
        if not os.path.isdir(prof_dir):
            print(f"  ⚠ {prof_name}: profile dir missing")
            continue

        agents_path = os.path.join(prof_dir, "AGENTS.md")
        content = render_agents_md(prof_name, tmpl)
        with open(agents_path, "w") as f:
            f.write(content)
        print(f"  ✓ {prof_name}: AGENTS.md written ({len(content)} chars)")


if __name__ == "__main__":
    main()
