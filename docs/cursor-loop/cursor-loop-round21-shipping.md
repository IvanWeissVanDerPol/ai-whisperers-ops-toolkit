# Round 21 — A/B Testing Infrastructure for Prompts (Shipped 2026-08-03)

**Source:** R20 identified "A/B testing automation" as the highest-ROI open item. R21 ships the foundational infrastructure.

**Outcome:**
- **`prompt_ab_tester.py` (15.3 KB)** — full A/B test framework with status/compare/promote
- **3 new endpoints:** `/api/prompt-ab`, `/api/prompt-ab/compare`, `/api/prompt-ab/promote`
- **1 new daily cron:** `prompt-ab-daily` at 06:30 UTC
- **5 AB test log entries** capturing the first experiments
- **Honest limitation surfaced:** no per-version trace data yet (limitation documented)

---

## What R21 actually shipped

### R21-1: Investigation

Found **1 active A/B experiment** in the registry:
- `delivery_prep_summary`: v1 (stable tag) vs v2 (prod tag)
  - v1: 141 chars, simple build/test/lint check
  - v2: 190 chars, adds anomaly check + complexity delta + evidence output

The tag system already supports multi-version prompts. The framework just needed tooling.

### R21-2: `prompt_ab_tester.py`

**15.3 KB** — comprehensive A/B test framework with 4 subcommands:

```
python3 prompt_ab_tester.py status              # show all active experiments
python3 prompt_ab_tester.py compare --name X    # compare 2 versions
python3 prompt_ab_tester.py promote --name X    # auto-promote winner
python3 prompt_ab_tester.py promote --all --dry-run  # check all
```

Features:
- **Status:** find all multi-version prompts, show tags
- **Compare:** side-by-side content diff + metrics
- **Promote:** auto-promote winner (with safety rails)
- **Logging:** every decision written to `/root/.hermes/state/prompt_ab_tests.log`

### R21-3: 3 New Dashboard Endpoints

```
/api/prompt-ab         → 326 bytes JSON (list experiments)
/api/prompt-ab/compare → 643 bytes JSON (v1 vs v2 diff + metrics)
/api/prompt-ab/promote → 411 bytes JSON (decision)
```

### R21-4: Auto-Promote Logic

The promote logic uses a **safety-first decision tree**:

1. Find current stable tag (baseline)
2. Find candidate versions (anything not stable)
3. Compare shared metrics from traces
4. If candidate beats baseline by threshold (default 1.1x) AND has 20+ traces → promote
5. If no per-version data → **skip with recommendation** (no false promotion)

The current limitation: traces don't record which prompt version was used. They all use `prompt_registry.get --tag stable` → v1. So promotion is currently **honest-skip**:
```
🟡 delivery_prep_summary: skip
   reason: no per-version trace data; using content-size heuristic
   recommendation: per-version trace tagging needed
```

### R21-5: Daily `prompt-ab-daily` Cron

```
prompt-ab-daily    30 6 * * *    No-agent
```

Runs at 06:30 UTC — after `prompt-quality-daily` (06:00 UTC). Reports active experiments.

---

## The honest limitation (R21)

The promotion logic **works** but currently **always skips** because:
- All traces use the prompt from `prompt_registry.get --tag stable`
- We don't record which version was actually used in the trace
- Without per-version trace data, we can't compare v1 vs v2 metrics

To enable real A/B testing, future work needs:

1. **Cron-side modification:** when a cron uses prompt_registry, also record the version in the trace
2. **LLM call modification:** when the LLM request is built, tag with prompt version
3. **Trace metadata:** add `prompt_version` field to trace schema

This is significant work but enables **real statistical A/B testing** of prompts.

---

## Live demo (R21 right now)

```
$ prompt_ab_tester.py status
=== Prompt A/B Test Status ===

Total prompts: 9
Multi-version: 1

--- Active experiments ---
  • delivery_prep_summary: v1, v2 [tags: stable=v1, prod=v2]

$ prompt_ab_tester.py compare --name delivery_prep_summary --v1 v1 --v2 v2
  v1 size: 141 chars
  v2 size: 190 chars (35% larger)
  Tags: stable=v1, prod=v2
  Diff:
    - Build status
    - Test status
    - Lint warnings
    +- Anomaly check      ← NEW
    +- Complexity delta   ← NEW
    -Output: PASS or FAIL.
    +Output: PASS or FAIL with evidence.
```

The infrastructure is **ready** for when per-version trace data becomes available.

---

## The 8-layer self-healing + quality + AB stack (now complete)

```
1. cron_health runs every 30 min → detects broken crons
2. cron_self_heal runs daily → auto-repairs with cost_router
3. cron_auto_disable runs daily → disable after N failures
4. cost_router probes tiers → finds cheapest working model
5. anomaly_detector runs daily → flags cost spikes / errors
6. anomaly_auto_pause runs daily → pauses high-cost crons
7. prompt_quality_daily → quality scores per prompt
8. prompt_ab_daily → A/B experiment status (R21 ★ NEW)
```

---

## Git state

```
psycology:     <pending>
hermes-config: <pending>
```

---

## What's open for R22+

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | Per-version trace tagging (adds version field to trace lines) | 4h | **Enables real A/B** |
| 2 | Auto-promote v2 → stable when real A/B data shows 1.1x improvement | 2h | High |
| 3 | Prompt quality dashboard (HTML/SVG with sparklines) | 4h | Medium |
| 4 | Atlas E-1 Agent Swarm architecture | 6h | Strategic |
| 5 | Atlas F-1 Vector DB foundation | 4h | Strategic |

**R21 honest assessment:** The A/B testing **infrastructure** is complete — registry, CLI, endpoints, cron, logging. The **capability** is partial — we can find experiments and compare content, but can't make real data-driven promotion decisions without per-version trace tagging. The next round (R22) should focus on bridge infrastructure to enable real A/B testing.
