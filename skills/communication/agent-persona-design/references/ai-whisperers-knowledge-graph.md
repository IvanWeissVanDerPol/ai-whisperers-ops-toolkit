# Knowledge Graph Seeding Guide

Seed the MCP memory server (`@modelcontextprotocol/server-memory`) with entities
and relations about Ai-Whisperers so the agent doesn't need to re-scan everything
each session.

## Prerequisites

- The `memory-server` MCP server must be configured in `config.yaml` and enabled
- Use `mcp_call("memory-server", "create_entities", ...)` and `mcp_call("memory-server", "create_relations", ...)`
- Batch entities in groups of 5-10 to keep tool calls efficient

## Batch 1: Core Identity

```json
{
  "entities": [
    {"name": "Ai-Whisperers", "entityType": "Organization", "observations": ["Paraguay AI web agency", "40+ repos across 4 tiers", "28+ Docker services on Hostinger VPS", "Next.js + Docker Swarm + Traefik + Cloudflare", "Founded by Ivan"]},
    {"name": "Erebus", "entityType": "AI Agent", "observations": ["AI workforce lead at Ai-Whisperers", "Main interaction: WhatsApp (human team) + Hermes TUI", "Senior engineer persona: calm, direct, proactive", "Ships work then reports — root cause chains", "Sub-personas: Dev, Ops, Research, Client"]},
    {"name": "ArchMagus", "entityType": "AgentPersona", "observations": ["Telegram bot username", "@ArchMagusBot"]},
    {"name": "Ivan", "entityType": "Person", "observations": ["Founder and lead developer", "Also known as ParaguAI", "Technical architect for all systems", "Prefers comprehensive execution over picking options", "Wants root cause chains, not status reports"]}
  ]
}
```

## Batch 2: Active Client Sites (Tier 1)

For each active client site, create an entity with observations:
- Repo/stack (Next.js, SvelteKit)
- Docker service name
- Domain
- Status (ACTIVE/DOWN)
- Whether it has a public GitHub repo or is missing one

```json
{
  "entities": [
    {"name": "elviajero", "entityType": "Repository", "observations": ["Paraguayan food e-commerce", "Next.js 15+", "Docker service: elviajero:prod (2/2)", "Domains: viajero.paragu-ai.com, el-viajero.paragu-ai.com", "No public GitHub repo", "Has a local project at /root/elviajero"]},
    {"name": "nexa-paraguay", "entityType": "Repository", "observations": ["Paraguay business portal", "Next.js Pages Router", "4 locales", "59 MDX blog articles", "Docker service: nexa:prod (1/1)", "Has full docs/ with 13 categories", "Published npm packages: @aiw/* v0.2.0+", "No public GitHub repo"]},
    {"name": "paragu-ai-builder", "entityType": "Repository", "observations": ["AI website builder for beauty & wellness", "Next.js/TypeScript", "Docker service: paragu-ai:prod (3/3)", "GitHub: Ai-Whisperers/paragu-ai-builder", "STATUS: ACTIVE"]},
    {"name": "depiflash", "entityType": "Repository", "observations": ["Laser hair removal website", "Next.js 15", "Docker service: depiflash:prod (2/2)", "GitHub: Ai-Whisperers/depiflash", "STATUS: ACTIVE"]},
    {"name": "fun4me", "entityType": "Repository", "observations": ["Adult store e-commerce", "Next.js 16", "Docker service: fun4me:prod (0/2)", "GitHub: Ai-Whisperers/fun4me", "STATUS: DOWN — needs investigation"]},
    {"name": "anthro-party-argentina", "entityType": "Repository", "observations": ["Event website for Anthro Party Argentina", "SvelteKit", "GitHub: Ai-Whisperers/anthro-party-argentina", "STATUS: ACTIVE"]}
  ]
}
```

Then create relations:
```json
{
  "relations": [
    {"from": "elviajero", "relationType": "belongs_to", "to": "Ai-Whisperers"},
    {"from": "nexa-paraguay", "relationType": "belongs_to", "to": "Ai-Whisperers"},
    {"from": "paragu-ai-builder", "relationType": "belongs_to", "to": "Ai-Whisperers"},
    {"from": "Erebus", "relationType": "works_at", "to": "Ai-Whisperers"},
    {"from": "Ivan", "relationType": "founded", "to": "Ai-Whisperers"}
  ]
}
```

## Batch 3: Infrastructure Services

```json
{
  "entities": [
    {"name": "VPS-agentzero", "entityType": "Infrastructure", "observations": ["Hostinger VPS", "IP: 72.61.44.159", "31GB RAM, 387GB disk, 8 vCPUs", "Ubuntu 24.04.4 LTS", "Tailscale: 100.91.243.120"]},
    {"name": "traefik", "entityType": "Service", "observations": ["Reverse proxy", "SSL/TLS via Let's Encrypt", "Routes all 28+ sites", "Version: v3.5.3", "Ports: 80/443"]},
    {"name": "evolution_api", "entityType": "Service", "observations": ["WhatsApp message bridge", "Domain: evolution.sunstein.cloud", "Port: 8080"]},
    {"name": "grafana", "entityType": "Service", "observations": ["Monitoring dashboard", "Domain: monitor.paragu-ai.com", "Port: 3030"]},
    {"name": "postgres", "entityType": "Service", "observations": ["Primary database", "Port: 5432"]}
  ]
}
```

## Batch 4: Domains

```json
{
  "entities": [
    {"name": "paragu-ai.com", "entityType": "Domain", "observations": ["Main client sites domain", "Cloudflare proxied", "28+ subdomains"]},
    {"name": "sunstein.cloud", "entityType": "Domain", "observations": ["Infrastructure domain", "Workspace, Evolution API, etc."]},
    {"name": "workspace.sunstein.cloud", "entityType": "URL", "observations": ["Hermes Workspace web UI", "Chat + terminal + memory browser"]}
  ]
}
```

## Maintenance

- **Re-seed** whenever a new repo goes live or a major service changes
- **Check** for existing entities before creating duplicates: `mcp_call("memory-server", "read_graph")` or query specific entities
- **Remove** outdated entities when repos are archived
