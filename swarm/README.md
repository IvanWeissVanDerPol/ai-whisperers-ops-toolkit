# swarm — Atlas E-1 Agent Swarm Architecture

**Multi-agent coordination for complex goals.** Decomposes a goal into parallel
subtasks (researcher, coder, tester, reviewer), spawns each as a subprocess
worker, and threads state across them via shared memory.

## Architecture

```
┌──────────────────────────────────────────────┐
│  swarm.py (CLI entry)                        │
│  "Build a tool that converts CSV to JSON"     │
└────────────────┬─────────────────────────────┘
                 │
        ┌────────▼─────────┐
        │  Orchestrator     │  Decomposes goal, picks workers, monitors
        │  (orchestrator.py)│  Max parallel: 3
        └────────┬─────────┘
                 │ spawns subprocess
   ┌─────────────┼─────────────┐
   ▼             ▼             ▼
┌───────┐   ┌───────┐   ┌───────┐
│Worker │   │Worker │   │Worker │
│research│   │ coder │   │tester │
│  .py  │   │  .py  │   │  .py  │
└───┬───┘   └───┬───┘   └───┬───┘
    │           │           │
    └───────────┼───────────┘
                ▼
       ┌────────────────┐
       │ Shared Memory  │  Append-only log + named snapshots + blackboard
       │ shared_memory.py
       └────────────────┘
```

## Quick start

```bash
cd /root/ai-whisperers-ops-toolkit/swarm

# Show the plan (no execution)
python3 swarm.py --plan-only "Build a CLI that converts CSV to JSON"

# Execute (default: researcher → coder → tester → reviewer)
python3 swarm.py "Build a CLI that converts CSV to JSON"

# Research-only
python3 swarm.py --plan-only "What are the top 3 competitors for AI Whisperers?"

# Custom memory dir + parallelism
python3 swarm.py --memory-dir /tmp/my-state --max-parallel 5 "Fix the bug in cron_health.py"

# Inspect what happened
python3 shared_memory.py --dir /tmp/swarm-state/run-123 status
python3 shared_memory.py --dir /tmp/swarm-state/run-123 log --agent w-code-1234567890
ls /tmp/swarm-state/run-123/snapshots/
```

## Roles

| Role | Job | Tools |
|------|-----|-------|
| **researcher** | Gather info, analyze data, find patterns | web_search, web_extract, file reads |
| **coder** | Write/modify code, run commands | patch, write_file, terminal |
| **reviewer** | Check code, plans, findings for issues | file reads |
| **tester** | Verify claims by actually running things | terminal, smoke tests |
| **writer** | Produce polished prose/docs | reads, web search |

Add new roles by editing `ROLE_PROMPTS` in `worker.py`.

## Execution model

1. **Orchestrator** decomposes goal into subtasks (depends on goal type)
2. **Subtasks** marked with role + dependencies
3. **Ready subtasks** (deps all done) launched in parallel up to `max_parallel`
4. Each **worker** is a subprocess running `claude` CLI with role-specific prompt
5. Worker logs to shared memory, publishes results
6. Orchestrator polls memory, decides next batch
7. Cycle or failure → skip dependent tasks

## Shared memory

Three layers:

| Layer | Purpose | Use |
|-------|---------|-----|
| `memory.jsonl` | Append-only event log | Audit trail, replay |
| `snapshots/<name>.json` | Named structured data | Pass results between workers |
| `blackboard/<key>` | Free-form key-value | Scratch space, ad-hoc notes |

CLI:

```bash
# Append a log entry
python3 shared_memory.py log --agent w1 --role researcher --event "started" --payload '{"task":"..."}'

# Publish a snapshot (worker result)
python3 shared_memory.py publish --name "result-research" --data '{"findings":[...]}'

# Read a snapshot
python3 shared_memory.py read --name "result-research"

# Write blackboard key
python3 shared_memory.py blackboard-write --key "todo" --value "fix the bug in line 42"

# Status
python3 shared_memory.py status
```

## Why this design

1. **Workers are subprocesses**: no Python concurrency headaches, true parallelism
2. **Files for memory**: debuggable from any tool (cat/jq), no DB required
3. **Append-only log**: every event traceable, no silent state mutations
4. **Simple roles**: prompts in a dict, easy to add new ones
5. **Heuristic planner**: complex enough to handle common patterns, simple enough to understand
6. **LLM planner**: when heuristic doesn't fit, ask the LLM to decompose (with same fallback)
7. **Retry policy**: failures don't cascade — retry, escalate, or skip cleanly
8. **Cost tracking**: every worker records tokens + cost so you can budget the swarm
9. **Persistent state**: plan + subtask history saved to disk; resume interrupted runs
10. **Cost optimizer**: downgrades model per task to the cheapest that meets quality floor

## Resilience + recovery flow

```
failure detected
        │
        ▼
RetryPolicy.decide(attempt, reason)
        │
        ├─ attempt < max_retries      → RETRY (same role, 1.5× timeout)
        │
        ├─ attempt < escalate_after   → ESCALATE (add reviewer subtask + retry after)
        │
        └─ else                       → FAIL (skip dependents)
                │
                ▼
        state persisted to disk via PersistentState
                │
                ▼
        New Orchestrator.continue_if_interrupted() + resume()
                │
                ▼
        Picks up where we left off (succeeded tasks reused, pending re-run)
```

Verified by `examples/dry_run_with_retry.py` (retry) and `examples/resume_interrupted.py` (interrupt + resume, 2 tasks reused from state, 3 re-executed, 5/5 succeed).

## Limits / not-yet-implemented

- LLM-based planner (current: keyword heuristic). For complex goals, replace
  `Orchestrator.plan()` with a planner that calls claude with the goal.
- Built-in retry policy (current: retry once manually, then mark failed)
- Cost tracking (would need to parse worker subprocess outputs)
- Real-time progress UI (use `python3 swarm.py --status` periodically)

## Files

| File | Size | Purpose |
|------|------|---------|
| `shared_memory.py` | ~9 KB | Append-only log + snapshots + blackboard |
| `worker.py` | ~10 KB | Worker subprocess template (one task per worker) |
| `orchestrator.py` | ~16 KB | Decomposes goal + spawns workers + monitors + retries |
| `swarm.py` | ~7 KB | CLI entry point + run management |
| `planner.py` | ~10 KB | LLM-based task decomposition (with heuristic fallback) |
| `retry.py` | ~7 KB | Retry + escalation policy (resilient failure handling) |
| `cost_tracker.py` | ~8 KB | Per-worker token + cost tracking |
| `persistent_state.py` | ~8 KB | Save/load plan to disk + resume detection |
| `cost_optimizer.py` | ~10 KB | Pick cheapest viable model per task based on quality floor |
| `README.md` | this | Architecture + usage docs |
| `examples/dry_run.py` | 5 KB | End-to-end test (no auth needed) |
| `examples/dry_run_with_retry.py` | 7 KB | End-to-end retry + cost tracking test |
| `examples/resume_interrupted.py` | 9 KB | End-to-end interrupt + resume test |
| `examples/cost_optimization.py` | 6 KB | Cost optimizer comparison demo |
| `examples/research_workflow.py` | 3 KB | Real-world example (3 parallel → synthesis → review) |

## Roadmap

- [x] LLM-based planner (`planner.py` ships with heuristic fallback)
- [x] Retry policy with escalation (`retry.py` ships)
- [x] Cost tracking (`cost_tracker.py` ships)
- [x] Persistent state + resume (`persistent_state.py` ships, verified)
- [x] Cost optimizer (`cost_optimizer.py` ships, verified)
- [ ] Real-time WebSocket progress UI
- [ ] Multi-host swarm coordination (workers on different machines)

## See also

- `cron_orchestrator.py` in `~/.hermes/scripts/`: single-orchestrator pattern
- `kanban_orchestrator.py`: task-board coordination (different model)
- Atlas roadmap item E-1 in `atlas/hermes-upgrade-atlas.md`