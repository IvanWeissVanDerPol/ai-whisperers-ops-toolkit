# AI-Whisperers Ops Toolkit

**One repo to bootstrap any VPS, client, or workspace with the full Hermes Agent operational stack.**

Built over 23+ rounds of work (R5–R23, July–August 2026), this toolkit contains every script, doc, config, and skill we use to run a production-grade Hermes Agent environment. Clone it, run the bootstrap, and you have:

- 9-layer self-managing infrastructure (cron health, auto-repair, cost routing, anomaly detection, prompt quality, A/B testing)
- 24 dashboard endpoints (HTTP API on port 8645)
- 74 production-tested cron jobs
- 115 Python scripts + 79 wrapper scripts
- 10 registered prompts (versioned, A/B tested)
- 226 skills (3 hand-picked ones included; full set auto-installed)
- 22+ shipping docs explaining what shipped, when, and why

## Quick Start

```bash
# Clone
git clone https://github.REPLACE_ME.git
cd ai-whisperers-ops-toolkit

# Bootstrap on a new VPS or client machine
./bootstrap.sh

# Verify
curl -s -u admin:hermes http://127.0.0.1:8645/api/health
```

That's it. The bootstrap handles:
- Python deps (auto-installed via pip)
- Directory structure (`~/.hermes/scripts`, `~/.hermes/state`, `~/.hermes/memories`)
- Config templates (you fill in `.env` with your real API keys)
- Cron registrations (74 crons auto-imported)
- Dashboard API server (systemd service)
- Initial state (9 prompt templates seeded)

## What's Inside

```
ai-whisperers-ops-toolkit/
├── README.md                    ← You are here
├── INSTALL.md                   ← Detailed installation guide
├── LICENSE                      ← MIT
├── .gitignore                   ← Secrets, state, env files excluded
├── bootstrap.sh                 ← Single command to install everything
│
├── scripts/                     ← 115 Python scripts (all .py files)
│   ├── cron_health.py           ← Detects broken crons
│   ├── cost_router.py           ← Routes LLM calls to cheapest working model
│   ├── prompt_ab_tester.py      ← A/B tests prompt versions
│   ├── anomaly_detector.py      ← Flags cost spikes / error patterns
│   ├── prompt_version_recorder.py ← Sidecar for per-version attribution
│   ├── usage_analytics.py       ← Token usage breakdown
│   ├── trace_skill_analytics.py ← Maps traces to skills
│   ├── gh_actions_generator.py  ← Generates GitHub Actions workflows
│   ├── prompt_registry.py       ← Versioned prompts with tags
│   ├── ... (115 total)
│   └── wrappers/                ← 79 shell wrappers for crons
│       ├── anomaly_auto_pause_daily.sh
│       ├── prompt_quality_daily_wrapper.sh
│       ├── ... (79 total)
│
├── configs/                     ← Sanitized configs (you fill in real values)
│   ├── config.example.yaml      ← Hermes config template
│   ├── env.example              ← API keys template
│   ├── jobs.example.json        ← 74 cron jobs template
│   ├── MEMORY.template.md       ← Memory template
│   └── prompts/                 ← 9 prompt templates
│
├── docs/                        ← All upgrade docs
│   ├── WORKING_WITH_HERMES.md   ← The canonical "how to work" guide
│   ├── cursor-loop/             ← 23 round shipping docs
│   │   ├── cursor-loop-round5-shipping.md
│   │   └── ... (round23 latest)
│   └── ops/                     ← Per-feature operational guides
│       ├── (generated from docs/cursor-loop)
│
├── skills/                      ← 3 hand-picked upgrade skills
│   ├── communication/
│   │   ├── agent-persona-design/
│   │   └── one-three-one-rule/
│   └── avoid-ai-writing/
│
├── atlas/                       ← Strategic roadmap
│   ├── hermes-upgrade-atlas.md  ← 20 atlas items
│   └── hermes-infra-audit-r16.md ← Comprehensive infra audit
│
└── bootstrap/                   ← Bootstrap scripts
    ├── new-vps.sh               ← New VPS deployment
    └── new-client.sh            ← New client workspace setup
```

## The 5 Rules (After R23)

1. **Always start with the dashboard.** `curl -s -u admin:hermes http://127.0.0.1:8645/api/health`
2. **Be specific.** "R-N-1: fix X. R-N-2: add Y endpoint" beats "do all of this"
3. **Verify with curl.** "Endpoint returns 432 bytes" beats "I tested it"
4. **Use wrapper.sh for cron args.** Always.
5. **Trust the infrastructure after R17+.** The 9-layer stack handles 90% of "broken" things.

Full guide: [`docs/WORKING_WITH_HERMES.md`](docs/WORKING_WITH_HERMES.md)

## The 9-Layer Self-Managing Stack

| # | Layer | What | When |
|---|-------|------|------|
| 1 | cron_health | Detects broken crons | Every 30 min |
| 2 | cron_self_heal | Auto-repairs with cost_router | Daily 04:00 |
| 3 | cron_auto_disable | Disables after 5 failures | Daily 04:30 |
| 4 | cost_router | Probes providers, finds cheapest | On demand |
| 5 | anomaly_detector | Flags cost spikes / errors | Daily 05:00 |
| 6 | anomaly_auto_pause | Pauses high-cost crons | Daily 04:45 |
| 7 | prompt_quality_daily | Quality scores per prompt | Daily 06:00 |
| 8 | prompt_ab_daily | A/B experiment status | Daily 06:30 |
| 9 | prompt_version_recorder | Real per-version trace data | On demand |

## The 24 Dashboard Endpoints

After bootstrap, all 24 endpoints live on port 8645:

```bash
# Health
curl -s -u admin:hermes http://127.0.0.1:8645/api/health
curl -s -u admin:hermes http://127.0.0.1:8645/api/cron
curl -s -u admin:hermes http://127.0.0.1:8645/api/anomalies
curl -s -u admin:hermes http://127.0.0.1:8645/api/orchestration

# Cost & model
curl -s -u admin:hermes http://127.0.0.1:8645/api/cost-forecast
curl -s -u admin:hermes http://127.0.0.1:8645/api/cost-router/audit
curl -s -u admin:hermes http://127.0.0.1:8645/api/usage

# Prompts
curl -s -u admin:hermes http://127.0.0.1:8645/api/prompt-quality
curl -s -u admin:hermes http://127.0.0.1:8645/api/prompt-ab
curl -s -u admin:hermes http://127.0.0.1:8645/api/prompt-ab/quality?name=weekly_self_evolution
curl -s -u admin:hermes http://127.0.0.1:8645/api/prompt-ab/promote

# Traces & skills
curl -s -u admin:hermes http://127.0.0.1:8645/api/traces
curl -s -u admin:hermes http://127.0.0.1:8645/api/skills
```

## When To Use This Repo

| Scenario | Use this repo |
|----------|---------------|
| New VPS, fresh Ubuntu | `./bootstrap.sh new-vps` |
| New client workspace | `./bootstrap.sh new-client <client-name>` |
| Existing Hermes install, want upgrades | Clone + cherry-pick what you need |
| Just want the docs | Browse `docs/` and `atlas/` |
| Just want a single script | `scripts/cron_health.py` is standalone |
| Want to see what was built | Read `docs/cursor-loop/round5-shipping.md` onwards |

## Customization

After bootstrap, customize in this order:
1. Edit `~/.hermes/.env` with real API keys
2. Edit `~/.hermes/config.yaml` to match your providers
3. Edit `~/.hermes/memories/MEMORY.md` with your preferences
4. Run `hermes cron list` to see all registered jobs
5. Run `hermes cron disable <id>` to turn off ones you don't want

## License

MIT — see [LICENSE](LICENSE).

## Contributing

This repo is owned by Ivan + Erebus. Rounds are committed with `feat(R-N):` prefix. See [`docs/cursor-loop/`](docs/cursor-loop/) for history.

---

**Built by**: Erebus (Hermes Agent) · **Maintained by**: Ivan Weiss Van der Pol · **Last updated**: 2026-08-03 (R23)
