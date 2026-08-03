# Knowledge Graph Seed — Org Entities & Relations

After defining a new agent persona and writing SOUL.md, seed the MCP memory server so the agent has permanent structural knowledge of the organization. Without this step, the agent rediscovers the org every session.

## Entities to Create

Use `mcp call memory-server create_entities` for these entity types:

### Organization
```json
{
  "entityType": "Organization",
  "name": "Ai-Whisperers",
  "observations": [
    "Description, location, industry",
    "Stack, infrastructure, scale",
    "Domain names, key services"
  ]
}
```

### Key People
```json
{
  "entityType": "Person",
  "name": "Ivan",
  "observations": [
    "Founder of Ai-Whisperers",
    "Ultimate authority — prefers execution over options",
    "Hands-on tech lead who knows exact architecture",
    "Frustrated by import/path issues causing rework"
  ]
}
```

### AI Agent (the persona itself)
```json
{
  "entityType": "AI Agent",
  "name": "Erebus",
  "observations": [
    "AI workforce lead at Ai-Whisperers",
    "Main interaction: WhatsApp (human team) + Hermes TUI",
    "Senior engineer persona: calm, direct, proactive",
    "Ships work then reports — root cause chains"
  ]
}
```

### Infrastructure
```json
{
  "entityType": "Server",
  "name": "VPS agentzero",
  "observations": [
    "Hostinger VPS at 72.61.44.159",
    "Ubuntu 24.04, 8 vCPU, 31GB RAM, 387GB disk",
    "Runs Docker Swarm with 38 services"
  ]
}
```

### Domains
```json
{
  "entityType": "Domain",
  "name": "paragu-ai.com",
  "observations": [
    "Primary client website domain",
    "25+ subdomains for client sites",
    "Traefik reverse proxy with Let's Encrypt SSL"
  ]
}
```

### Repositories — per important repo
```json
{
  "entityType": "Repository",
  "name": "nexa-paraguay",
  "observations": [
    "Client website project",
    "Standalone Pages Router SSR site",
    "25+ pages, 4-locale blog with 59 MDX articles"
  ]
}
```

### Services
```json
{
  "entityType": "Service",
  "name": "Evolution API",
  "observations": [
    "WhatsApp Business message bridge",
    "Hosted at evolution.sunstein.cloud on port 8080",
    "Connected to Hermes Gateway for WhatsApp AI"
  ]
}
```

### Conventions
```json
{
  "entityType": "Convention",
  "name": "WhatsApp communication rules",
  "observations": [
    "Max 3 sentences per response",
    "No greetings, closings, or filler",
    "Bullet points instead of paragraphs",
    "Zero fluff phrases",
    "One actionable item per message",
    "No markdown formatting"
  ]
}
```

## Relations to Create

Use `mcp call memory-server create_relations`:

| From | Type | To |
|------|------|----|
| `Ivan` | `founded` | `Ai-Whisperers` |
| `Ivan` | `directs` | `Erebus` |
| `Erebus` | `works_at` | `Ai-Whisperers` |
| `VPS agentzero` | `hosts_infrastructure_of` | `Ai-Whisperers` |
| `Docker Swarm` | `runs_on` | `VPS agentzero` |
| `paragu-ai.com` | `resolves_to` | `VPS agentzero` |
| `sunstein.cloud` | `resolves_to` | `VPS agentzero` |
| `Hermes Agent` | `runs_on` | `VPS agentzero` |
| `Evolution API` | `feeds_into` | `Hermes Agent` |
| `nexa-paraguay` | `belongs_to` | `Ai-Whisperers` |

## Memory Updates

After seeding the graph, also save key facts in memory:

```bash
memory(action='add', target='user', content='Ivan: founder, prefers depth over options, no status reports')
memory(action='add', target='memory', content='Erebus = AI workforce lead. SOUL.md written. Graph seeded.')
```

## Verification

```bash
mcp call memory-server read_graph
# Should return all entities and relations
```

## Pitfalls

- **Don't seed job tracking in graph** — task progress, completed work, temporary TODO state belongs in session context, not permanent memory
- **Keep observations concise** — 3-5 facts per entity is enough. Don't dump logs or analytics into the knowledge graph
- **Graph is for relationships, memory is for preferences** — the graph stores structure (who works where, what depends on what). Memory stores preferences (user likes X format, don't use Y tool)
- **Update graph when infra changes** — new servers, domains, repos, or key changes should be added as nodes/relations
