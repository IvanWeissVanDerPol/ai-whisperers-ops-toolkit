"""
skill_metadata — registry of all Hermes skills with token cost + applicable bots.

Solves the "load all 65 skills blindly" problem: each skill gets:
  - tier: LOW | MEDIUM | HIGH | VERY_HIGH (token cost per use)
  - bots: which bots should load this skill
  - load_priority: 1-5 (1 = always load first)

Usage:
  from skill_metadata import get_skills_for_bot, get_load_order

  skills = get_skills_for_bot("lua")  # only skills for lua
  order = get_load_order("lua")       # sorted by priority
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

SKILLS_ROOT = Path.home() / ".hermes" / "skills"

Tier = Literal["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]


def _infer_tier(skill_dir: Path) -> Tier:
    """Infer token cost from skill content + keywords.

    Tiers are about RUNTIME cost per invocation:
      LOW: text lookup / reference doc (e.g., luana-design-rules)
      MEDIUM: invokes other LLMs, runs scripts
      HIGH: image generation
      VERY_HIGH: video generation
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return "LOW"
    text = skill_md.read_text().lower()
    # Video gen keywords
    has_video = any(k in text for k in ["video_generate", "manim", "comfyui", "video_analyze"])
    if has_video:
        return "VERY_HIGH"
    # Image gen keywords
    has_image = any(k in text for k in ["image_generate", "stable diffusion", "comfyui"])
    if has_image:
        return "HIGH"
    # LLM invocation keywords
    has_llm = any(k in text for k in ["delegate_task", "inference.sh", "inference_cli",
                                       "claude-code", "codex", "opencode", "blackbox"])
    if has_llm:
        return "MEDIUM"
    return "LOW"


SKILL_INDEX: dict[str, dict] = {
    # Bot-applicability map. Each entry: {bots: [list], priority: 1-5}
    "luana-design-rules":        {"bots": ["lua", "design-bot"], "priority": 1},
    "designer-vocabulary-glossary": {"bots": ["lua", "design-bot"], "priority": 1},
    "designer-handoff":           {"bots": ["lua", "design-bot"], "priority": 2},
    "visual-pre-commit":          {"bots": ["design-bot", "delivery-bot"], "priority": 2},
    "wcag-audit-automation":     {"bots": ["design-bot", "lua", "delivery-bot"], "priority": 3},
    "wcag-contrast-quick-check":  {"bots": ["design-bot", "lua"], "priority": 1},
    "tailwind-v4-theme-system":   {"bots": ["design-bot"], "priority": 3},
    "tailwind-v4-silent-noop-trap": {"bots": ["design-bot"], "priority": 2},
    "refactoring-ui":             {"bots": ["design-bot"], "priority": 4},
    "design-everyday-things":     {"bots": ["design-bot", "lua"], "priority": 5},
    "design-md":                  {"bots": ["design-bot"], "priority": 3},
    "client-brand-asset-design":  {"bots": ["design-bot", "lua"], "priority": 3},
    "client-brand-photo-analysis": {"bots": ["design-bot", "lua"], "priority": 3},
    "client-component-abstraction": {"bots": ["design-bot", "delivery-bot"], "priority": 4},
    "client-site-i18n-content":   {"bots": ["design-bot", "delivery-bot"], "priority": 4},
    "placeholder-content-and-visual-polish": {"bots": ["design-bot"], "priority": 4},

    # Engineering / architect
    "execplan-skill":             {"bots": ["architect-bot"], "priority": 1},
    "systematic-debugging":       {"bots": ["architect-bot", "delivery-bot", "ops-bot"], "priority": 1},
    "writing-plans":              {"bots": ["architect-bot"], "priority": 1},
    "subagent-driven-development": {"bots": ["architect-bot"], "priority": 2},
    "test-driven-development":    {"bots": ["architect-bot", "delivery-bot"], "priority": 2},
    "simplify-code":              {"bots": ["architect-bot", "delivery-bot"], "priority": 3},
    "writing-skills":             {"bots": ["architect-bot"], "priority": 3},
    "spike":                      {"bots": ["architect-bot", "delivery-bot"], "priority": 3},
    "plan":                       {"bots": ["architect-bot"], "priority": 2},

    # Delivery / infra
    "nextjs-docker-swarm":        {"bots": ["delivery-bot", "architect-bot"], "priority": 1},
    "nextjs-docker-swarm-lightweight-dockerfile": {"bots": ["delivery-bot"], "priority": 2},
    "nextjs-client-site-maintenance": {"bots": ["delivery-bot"], "priority": 1},
    "nextjs-content-audit":       {"bots": ["delivery-bot"], "priority": 2},
    "nextjs-backend-patterns":    {"bots": ["delivery-bot", "architect-bot"], "priority": 2},
    "supabase-patterns":          {"bots": ["delivery-bot", "architect-bot"], "priority": 1},
    "supabase-secrets-audit":     {"bots": ["delivery-bot", "ops-bot"], "priority": 2},
    "client-site-inventory":      {"bots": ["delivery-bot", "operations-conductor"], "priority": 1},
    "client-site-architecture-audit": {"bots": ["delivery-bot"], "priority": 2},
    "site-healthchecks":          {"bots": ["delivery-bot", "operations-conductor"], "priority": 1},
    "site-template-validation":   {"bots": ["delivery-bot"], "priority": 2},
    "client-site-enhancement-batch": {"bots": ["delivery-bot"], "priority": 3},
    "client-site-deployment-hardening": {"bots": ["delivery-bot", "architect-bot"], "priority": 2},
    "client-site-pattern-extraction": {"bots": ["delivery-bot"], "priority": 3},
    "paragu-ai-new-client-site-scaffold": {"bots": ["delivery-bot"], "priority": 2},
    "paragu-ai-client-clone":     {"bots": ["delivery-bot"], "priority": 3},
    "paragu-ai-client-upgrades":  {"bots": ["delivery-bot"], "priority": 3},
    "paragu-ai-swarm-deploy":     {"bots": ["delivery-bot", "operations-conductor"], "priority": 1},
    "paragu-ai-platform-monorepo": {"bots": ["delivery-bot", "architect-bot"], "priority": 2},
    "paragu-ai-platform-deploy": {"bots": ["delivery-bot", "operations-conductor"], "priority": 2},
    "paragu-ai-site-architecture": {"bots": ["delivery-bot", "architect-bot"], "priority": 2},
    "ai-whisperers-business-analysis": {"bots": ["delivery-bot", "ops-bot"], "priority": 3},

    # Operations
    "operations-conductor":       {"bots": ["operations-conductor"], "priority": 1},
    "docker-management":          {"bots": ["operations-conductor", "delivery-bot"], "priority": 1},
    "docker-swarm-infrastructure": {"bots": ["operations-conductor"], "priority": 1},
    "site-healthchecks":          {"bots": ["operations-conductor", "delivery-bot"], "priority": 1},
    "hermes-ops-health":          {"bots": ["operations-conductor"], "priority": 1},
    "hermes-gateway-ops":         {"bots": ["operations-conductor"], "priority": 1},
    "ai-whisperers-company-audit": {"bots": ["operations-conductor", "ops-bot"], "priority": 2},
    "ai-whisperers-sunstone-report": {"bots": ["operations-conductor", "ops-bot"], "priority": 2},
    "ai-whisperers-fleet-health": {"bots": ["operations-conductor"], "priority": 1},
    "ai-whisperers-fleet-monitoring": {"bots": ["operations-conductor"], "priority": 1},
    "swarm-service-recovery":     {"bots": ["operations-conductor"], "priority": 1},
    "client-sites-healthcheck":   {"bots": ["operations-conductor"], "priority": 2},
    "incident-commander":         {"bots": ["operations-conductor"], "priority": 1},
    "swarm-service-recovery":     {"bots": ["operations-conductor"], "priority": 1},
    "ops-fallback-patterns":      {"bots": ["operations-conductor"], "priority": 2},

    # Sales / closer / explorer / copy
    "paraguay-whatsapp-ghostwriting": {"bots": ["closer-bot"], "priority": 1},
    "pyme-paraguay-objections":   {"bots": ["closer-bot"], "priority": 1},
    "ai-whisperers-pricing-benchmark": {"bots": ["explorer-bot", "closer-bot"], "priority": 1},
    "ai-whisperers-international-expansion": {"bots": ["explorer-bot"], "priority": 2},
    "py-market-research":         {"bots": ["explorer-bot"], "priority": 1},
    "multi-source-research":      {"bots": ["explorer-bot", "copy-bot"], "priority": 1},
    "domain-intel":               {"bots": ["explorer-bot"], "priority": 2},
    "repo-enhancement-research":  {"bots": ["explorer-bot"], "priority": 2},
    "lead-scout":                 {"bots": ["explorer-bot", "closer-bot"], "priority": 2},
    "negotiation":                {"bots": ["closer-bot"], "priority": 3},
    "predictable-revenue":        {"bots": ["closer-bot"], "priority": 4},
    "client-pricing-proposals":   {"bots": ["closer-bot", "ops-bot"], "priority": 2},
    "client-contracts":           {"bots": ["closer-bot", "ops-bot"], "priority": 3},
    "client-channel-binding":     {"bots": ["closer-bot", "client-success-bot"], "priority": 2},

    # Copy
    "client-content-production-brief": {"bots": ["copy-bot"], "priority": 1},
    "avoid-ai-writing":           {"bots": ["copy-bot"], "priority": 1},
    "humanizer":                  {"bots": ["copy-bot"], "priority": 2},
    "paraguay-micro-copywriting": {"bots": ["copy-bot"], "priority": 2},
    "seo-client-rankings":        {"bots": ["copy-bot", "explorer-bot"], "priority": 3},
    "seo-super-agent":            {"bots": ["copy-bot"], "priority": 3},
    "cro-methodology":            {"bots": ["copy-bot"], "priority": 4},
    "scorecard-marketing":        {"bots": ["copy-bot", "closer-bot"], "priority": 4},

    # Ops-bot
    "ai-whisperers-invoicing":    {"bots": ["ops-bot"], "priority": 1},
    "dunning-automation":         {"bots": ["ops-bot"], "priority": 1},
    "home-food-business-ops-spreadsheet": {"bots": ["ops-bot"], "priority": 3},
    "personal-erp-workbook":      {"bots": ["ops-bot"], "priority": 3},
    "recipe-costing-card":        {"bots": ["ops-bot"], "priority": 4},

    # Client-success-bot
    "client-feedback-pipeline":   {"bots": ["client-success-bot"], "priority": 1},
    "client-content-audit":       {"bots": ["client-success-bot", "copy-bot"], "priority": 2},
    "client-feedback-consolidation": {"bots": ["client-success-bot"], "priority": 2},
    "client-discovery-processor": {"bots": ["client-success-bot", "closer-bot"], "priority": 2},

    # Cross-bot / shared
    "whatsapp-ecommerce-integration": {"bots": ["client-success-bot", "closer-bot", "ops-bot"], "priority": 3},
    "voice-note-transcript-coverage": {"bots": ["delivery-bot"], "priority": 3},
    "audio-transcript-to-kanban": {"bots": ["delivery-bot"], "priority": 3},
    "kanban-batch-create-with-dispatcher-pause": {"bots": ["delivery-bot", "ops-bot"], "priority": 4},

    # Tony-bot — creative director for Toni's video
    "hyperframes-pipeline":        {"bots": ["tony-bot"], "priority": 1},
    "creative-consultation":       {"bots": ["tony-bot"], "priority": 1},
    "baoyu-comic":                 {"bots": ["tony-bot"], "priority": 2},
    "animation-interaction-inventory": {"bots": ["tony-bot"], "priority": 2},
    "pixel-art":                   {"bots": ["tony-bot"], "priority": 3},
    "ai-video-production-research": {"bots": ["tony-bot"], "priority": 2},
    "client-video-strategy":       {"bots": ["tony-bot"], "priority": 1},
    "hyperframes":                 {"bots": ["tony-bot"], "priority": 2},
    "kanban-video-orchestrator":   {"bots": ["tony-bot"], "priority": 2},
    "paragu-ai-video-production":  {"bots": ["tony-bot"], "priority": 2},
    "meme-generation":             {"bots": ["tony-bot"], "priority": 4},
    "humanizer":                   {"bots": ["tony-bot", "copy-bot"], "priority": 2},
    "image-content-audit":         {"bots": ["tony-bot", "design-bot"], "priority": 3},
    "tony-video-production":       {"bots": ["tony-bot"], "priority": 1},

    # Operations / health (cross-bot)
    "vps-disk-audit":              {"bots": ["operations-conductor", "ops-bot"], "priority": 2},
    "watchdog-health-monitor":     {"bots": ["operations-conductor"], "priority": 2},
    "fleet-management":            {"bots": ["operations-conductor"], "priority": 2},
    "doctor":                      {"bots": ["operations-conductor", "ops-bot"], "priority": 2},
    "kanban":                      {"bots": ["delivery-bot", "ops-bot"], "priority": 1},
    "kanban-s-grade-roadmap":      {"bots": ["delivery-bot"], "priority": 4},
    "kanban-doctor":               {"bots": ["operations-conductor"], "priority": 2},
}


def get_skills_for_bot(bot: str) -> list[str]:
    """Return skills applicable to a given bot, sorted by priority."""
    matches = [
        (name, meta["priority"])
        for name, meta in SKILL_INDEX.items()
        if bot in meta.get("bots", [])
    ]
    matches.sort(key=lambda x: (x[1], x[0]))
    return [name for name, _ in matches]


def get_load_order(bot: str) -> list[tuple[str, int]]:
    """Return [(skill_name, priority)] for a bot, sorted by priority."""
    return [
        (name, prio)
        for name, prio in sorted(
            [(n, m["priority"]) for n, m in SKILL_INDEX.items() if bot in m.get("bots", [])],
            key=lambda x: (x[1], x[0]),
        )
    ]


def get_skill_tier(skill_name: str) -> Tier:
    """Get inferred token cost tier for a skill."""
    skill_dir = SKILLS_ROOT / skill_name
    return _infer_tier(skill_dir)


def get_bot_token_budget(bot: str) -> int:
    """Recommended monthly token budget per bot (rough heuristic)."""
    skills = get_skills_for_bot(bot)
    if not skills:
        return 100_000
    # Sum tier weights
    weights = {"LOW": 50_000, "MEDIUM": 150_000, "HIGH": 400_000, "VERY_HIGH": 1_000_000}
    base = 200_000
    for s in skills:
        base += weights.get(get_skill_tier(s), 50_000)
    return base


def print_bot_summary(bot: str) -> None:
    """Print a bot's skill set with tiers and budget."""
    skills = get_load_order(bot)
    print(f"\n=== {bot} ({len(skills)} skills) ===")
    for name, prio in skills:
        tier = get_skill_tier(name)
        marker = {1: "★", 2: "◆", 3: "·"}.get(prio, " ")
        print(f"  {marker} [{tier:<10}] prio={prio}  {name}")
    print(f"\n  Monthly budget: ~{get_bot_token_budget(bot):,} tokens")


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "lua"
    print_bot_summary(bot)