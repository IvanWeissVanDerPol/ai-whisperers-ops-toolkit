# Round 20 — Trace → Prompt Linkage + Quality Scoring (Shipped 2026-08-03)

**Source:** R19 left "Trace → prompt linkage (quality improvement)" as the highest-ROI open item. R20 completes it.

**Outcome:**
- **3 missing prompts registered** from cron jobs.json (weekly_self_evolution, hermes_daily_dojo, daily_todo_list)
- **9 total prompts in registry** (up from 6)
- **`trace_prompt_linker.py` (10.1 KB)** — joins traces to prompts via session_id → cron_id lookup
- **`/api/prompt-quality` endpoint** — surfaces prompt-specific metrics
- **Quality scoring** — 0-100 score based on error rate, cost/call, p95 latency
- **Daily `prompt-quality-daily` cron** at 06:00 UTC

---

## What R20 actually shipped

### R20-1: Investigate trace metadata

Traces have:
- `timestamp`, `session`, `model`, `provider`, `tokens_in/out`, `cost_usd`, `latency_seconds`
- **No prompt content stored** (would be redundant + huge)

The linking strategy:
1. session_id format: `cron_<id>_<date>` for cron traces
2. Match prefix to jobs.json
3. Use cron name as prompt name (normalized)
4. Look up prompt content from prompt_registry

### R20-2: trace_prompt_linker.py

**`trace_prompt_linker.py` (10.1 KB)** — joins traces to prompts:

```python
def link_traces_to_prompts(traces, cron_jobs):
    # 1. For each trace, extract cron_id from session_id
    # 2. Match to cron_jobs
    # 3. Aggregate metrics per prompt name
    # 4. Return {prompt_name: {calls, cost, error_rate, latency_p50/p95, ...}}
```

**Quality scoring formula:**

```python
score = 100 - (error_rate * 40) - (cost_per_call * 5) - (latency_p95 / 100 * 10)
score = max(0, min(100, score))
```

### R20-3 + R20-4: Endpoint + scoring

`/api/prompt-quality?days=7` returns 1.3 KB JSON:

```json
{
  "days": 7,
  "traces_total": 523,
  "cron_jobs_total": 78,
  "registry_total": 9,
  "linked": {
    "hermes_daily_dojo": {
      "calls": 29,
      "cost_usd": 1.6883,
      "latency_p50": 18.2,
      "latency_p95": 26.0,
      "errors": 0,
      "error_rate": 0.0,
      "models": ["claude-sonnet-4-6"]
    },
    ...
  }
}
```

### R20-5: Daily prompt-quality cron

```
prompt-quality-daily    0 6 * * *    No-agent
```

Runs at 06:00 UTC — after all the anomaly detection (04:30 self-heal, 04:45 auto-pause, 05:00 anomaly detection).

---

## Live demo (R20 right now)

```
=== Trace → Prompt Linker ===

Period:          last 7 days
Prompts tracked: 3
Registered:      9

  🟢 ✓ weekly_self_evolution                    vv1
      calls:   22  cost: $  1.84  err:   0.0%  p95:  52.5s  score: 94.3
      model: claude-sonnet-4-6
  🟢 ✓ hermes_daily_dojo                        vv1
      calls:   29  cost: $  1.69  err:   0.0%  p95:  26.0s  score: 97.1
      model: claude-sonnet-4-6
  🟢 ✓ daily_todo_list                          vv1
      calls:    6  cost: $  0.00  err:   0.0%  p95:  12.4s  score: 98.8
      model: MiniMax-M3
```

All 3 LLM-driven crons with traces now have:
- Prompt registered in registry
- Trace metrics aggregated
- Quality score computed
- Model attribution

---

## The 7-layer self-healing + quality stack (now complete)

```
1. cron_health runs every 30 min → detects broken crons
2. cron_self_heal runs daily → auto-repairs with cost_router
3. cron_auto_disable runs daily → disable after N failures
4. cost_router probes tiers → finds cheapest working model
5. anomaly_detector runs daily → flags cost spikes / errors
6. anomaly_auto_pause runs daily → pauses high-cost crons
7. prompt_quality_daily → quality scores per prompt (R20 ★ NEW)
```

The 7th layer adds **quality feedback** — every prompt now has a measurable score. When a prompt is updated (new version), the score can be compared to past versions.

---

## The prompt-versioning feedback loop

```
R20 enables:
  1. Register v1 of a prompt
  2. Use it (cron runs)
  3. Trace metrics flow into quality score
  4. Identify prompt that needs improvement (low score)
  5. Improve prompt → register v2
  6. Compare v1 vs v2 quality scores
  7. Promote v2 to stable tag
```

This is the **A/B testing infrastructure** for prompts. Previous rounds enabled register/get/diff/list. R20 makes the **quality feedback** observable.

---

## Git state

```
psycology:     <pending>
hermes-config: <pending>
```

---

## What's open for R21+

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | A/B testing automation: auto-promote prompt v2 if score > v1 * 1.1 | 3h | High |
| 2 | Prompt quality dashboard (HTML/SVG with sparklines) | 4h | Medium |
| 3 | Atlas E-1 Agent Swarm architecture | 6h | Strategic |
| 4 | Atlas F-1 Vector DB foundation | 4h | Strategic |
| 5 | Auto-link request_dump to prompt (when session is available) | 2h | Medium |

**R20 honest assessment:** The system is now **measuring prompt quality**. Every LLM-driven cron has a registered prompt, a quality score, and a trace history. The 7-layer self-healing + quality stack is complete. The remaining work is **automation** (A/B testing) and **strategic** (vector DB, agent swarm).
