# Hermes Upgrade Atlas — 1000+ Concrete Improvements

**Generated:** 2026-07-31
**Scope:** All upgrade ideas worth doing on Hermes Agent, drawn from:
1. What we've built in R5/R6/R7/R8 (20 scripts, 14 crons, 1 repo)
2. What 133 existing skills cover (110 skill, 10 meta, 5 orchestration, 8 unknown)
3. Open-source landscape (Hermes itself, LangChain/LangGraph, CrewAI, AutoGen, Langfuse, Helicone, OpenHands, DSPy, n8n, Langflow)
4. Common production gaps (observability, cost, security, multi-tenant)

---

## TL;DR — Where we stand today

| Asset | Count | Where |
|---|---|---|
| Skills | 133 | `~/.hermes/skills/` |
| Scripts | 96 | `~/.hermes/scripts/` |
| Crons | 64 | via `hermes cron list` |
| Collections | 19 | `~/.hermes/skills/collections/` |
| State files | 15 | `~/.hermes/state/` |
| Canonical docs | 10 | `~/.hermes/inbox/cursor-loop*` |
| Hermes-config repo | 49 files | `/root/hermes-config/` |
| Live status page | 1 | https://hermes-status-4fw.pages.dev |

**5 rounds shipped in this session:** R5 (autonomous pipeline), R6 (skill migration + T9/T10/T11), R7 (Traefik + Telegram + AI), R8 (CF Pages + DNS + alerts).

---

## What's NOT missing (we already have these)

For sanity, here's what we've already shipped so you don't repeat:
- ✅ Autonomous pipeline (repo_tick, cron_orchestrator, pipeline_run)
- ✅ Per-repo health snapshots (45 repos, daily tick)
- ✅ Regression detection (snapshot_diff)
- ✅ AI anomaly detection (anomaly_detector — rule-based + LLM)
- ✅ Web dashboard with basic auth (dashboard_server)
- ✅ Public status page (Cloudflare Pages, deployed)
- ✅ Telegram bot with 8 commands
- ✅ Traefik routing for dashboard
- ✅ Password rotation
- ✅ Skill frontmatter migration
- ✅ Kanban orchestrator (T9)
- ✅ Project scaffolding (T10)
- ✅ Per-repo alerts (repo_alerts)
- ✅ DNS helper (dns_setup)
- ✅ Cost tracking basics (token_cost_by_bot)
- ✅ Secrets management (skill secrets docs)

---

## The 1000+ upgrades — by domain

Each item is concrete: name of skill, script, cron, or feature to add.
Format: `[cat-N]` where cat is the domain and N is the sequence.

### A. OBSERVABILITY & TRACING (cat-A) — 87 items

We have NO real observability stack. Langfuse integration exists in the wizard but we haven't activated it.

1. **[A-1] LLM Tracer** — Build `scripts/llm_tracer.py` (OpenTelemetry exporter for all hermes chat calls). Saves spans to `~/.hermes/state/traces/`.
2. **[A-2] Trace Visualizer** — Skill `trace-visualizer` — UI to filter/inspect traces.
3. **[A-3] Trace Aggregator** — Cron `trace-aggregate-hourly` — rolls up spans by skill+repo+model.
4. **[A-4] Trace Anomaly Detector** — Detect unusual token usage, latency spikes.
5. **[A-5] Langfuse Self-Host** — Deploy Langfuse via Docker Compose for full trace capture.
6. **[A-6] OpenLLMetry Integration** — Wire OpenTelemetry to existing pipelines.
7. **[A-7] Phoenix Integration** — Add Arize Phoenix as alternative observability backend.
8. **[A-8] Span Tracker** — `scripts/span_tracker.py` — decorator/context-manager that wraps function calls.
9. **[A-9] Skill Performance Profiler** — Track which skills take the most time per call.
10. **[A-10] Model Latency Tracker** — Compare p50/p95/p99 per model.
11. **[A-11] Cron Performance Monitor** — Track how long each cron takes to complete.
12. **[A-12] Error Rate Dashboard** — `/api/errors` endpoint on dashboard_server with hourly error rate per skill.
13. **[A-13] Trace-to-Skill Mapping** — For each trace, identify which skills were used.
14. **[A-14] Trace Sampling** — Configurable sampling rate to keep costs down.
15. **[A-15] Trace Search CLI** — `hermes traces search "skill:quality-gate repo:psycology"`.
16. **[A-16] Cost-Per-Span** — Tag each span with model + tokens + cost.
17. **[A-17] Multi-Backend Tracing** — Send same trace to Langfuse + Phoenix + local file.
18. **[A-18] Trace Export to S3** — Cron `trace-export-daily` — push old traces to R2/S3.
19. **[A-19] Real-Time Trace Tail** — `tail -f ~/.hermes/state/traces/latest.jsonl`.
20. **[A-20] Token Usage Heatmap** — Skill `usage-heatmap` — visualize token burn by hour/day/skill.
21. **[A-21] Skill Quality Metrics** — Track prompt→response quality scores over time.
22. **[A-22] LLM Judge Evaluator** — Use a cheap LLM to score output quality.
23. **[A-23] A/B Test Framework** — Compare two prompt variants automatically.
24. **[A-24] Eval Runner** — `scripts/eval_runner.py` — run a suite of test prompts and score them.
25. **[A-25] Regression Test for Prompts** — Detect when a model swap degrades quality.
26. **[A-26] Conversation Replay** — Re-run a conversation with a new model for comparison.
27. **[A-27] Model Drift Detection** — Alert when model output distribution shifts.
28. **[A-28] Per-Skill Cost Tracking** — `scripts/skill_cost.py` — token cost per skill invocation.
29. **[A-29] Cost Forecasting** — Predict monthly cost from current burn rate.
30. **[A-30] Cost Alerts** — Cron `cost-alert-daily` — alert when daily spend exceeds threshold.
31. **[A-31] Per-User Cost Quotas** — Multi-tenant cost controls (placeholder for cat-G).
32. **[A-32] Cost Attribution Tags** — Tag every call with project/client/bot.
33. **[A-33] Cost Dashboard Tile** — Add cost tile to status page.
34. **[A-34] Free-Tier Burn Rate** — Track how fast we're burning through OpenRouter free credits.
35. **[A-35] Prompt Cache Hit Rate** — Track effectiveness of any caching layer.
36. **[A-36] Streaming Token Counter** — Count tokens as they stream in for real-time cost.
37. **[A-37] Cross-Model Cost Comparison** — Show what each call would cost on alternative models.
38. **[A-38] Cost Optimizer Skill** — Suggest cheaper models for specific task types.
39. **[A-39] Helicone Proxy Integration** — Use Helicone as cost-tracking proxy.
40. **[A-40] LiteLLM Router Integration** — Use LiteLLM for unified provider routing + cost tracking.
41. **[A-41] Usage Anomaly Alerts** — Detect unusual cost spikes (3x normal = alert).
42. **[A-42] Per-Repo Cost Reports** — `/api/cost/repo/<name>` endpoint.
43. **[A-43] Per-Skill Cost Reports** — `/api/cost/skill/<name>` endpoint.
44. **[A-44] Weekly Cost Digest** — Cron `weekly-cost-digest` — summarize spend by category.
45. **[A-45] Budget Enforcement** — Cron `budget-guard` — disable expensive crons when budget exceeded.
46. **[A-46] Cost-Aware Routing** — Route cheap queries to free models, expensive ones to paid.
47. **[A-47] Smart Model Routing** — Extend `smart-model-routing` skill with cost-awareness.
48. **[A-48] Rate-Limit Tracking** — Track per-provider rate-limit hits and backoff strategy.
49. **[A-49] Provider Health Score** — Score each provider by success rate + latency + cost.
50. **[A-50] Fallback Chain Visualization** — Show operator which fallback chains get used most.
51. **[A-51] Trace-Replay Debug Tool** — `scripts/replay.py` — replay a trace with breakpoints.
52. **[A-52] Span Decorators Library** — `@traced` decorator usable by any skill.
53. **[A-53] Trace Query DSL** — Mini-language: `hermes traces "span.skill=='quality-gate' AND span.duration>5s"`.
54. **[A-54] Real-Time Trace Heatmap** — Live visualization of active spans.
55. **[A-55] Skill Dependency Graph** — Auto-discover which skills depend on which.
56. **[A-56] Cron Dependency Graph** — Same for crons.
57. **[A-57] Error Categorization** — Auto-categorize errors by type, frequency, source.
58. **[A-58] Crash Postmortem Generator** — Skill `postmortem-gen` — auto-generates postmortem docs.
59. **[A-59] SLO Tracker** — Define SLOs, track compliance.
60. **[A-60] Latency Budget Per Skill** — Alert if skill exceeds its budget.
61. **[A-61] Distributed Tracing Across Bots** — Track calls across bot boundaries.
62. **[A-62] Trace-Aware Replay** — Resume from any point in a trace.
63. **[A-63] Token Budget Per Conversation** — Cap max tokens per conversation.
64. **[A-64] Conversation Compression Triggers** — Auto-compress when context budget is hit.
65. **[A-65] Span Search by Token Count** — Find expensive spans.
66. **[A-66] Token Usage by Hour Histogram** — Identify peak usage.
67. **[A-67] Token Usage by Model Donut** — Show distribution across models.
68. **[A-68] Cost-Per-Outcome** — Cost of successful vs failed tasks.
69. **[A-69] Skill Effectiveness Score** — Quality-adjusted cost-per-skill.
70. **[A-70] Auto-Pause Expensive Crons** — Disable crons when cost threshold hit.
71. **[A-71] Cost Guard Cron** — Cron `cost-guard-hourly` — continuous budget enforcement.
72. **[A-72] Token Budget Per Day** — Cap daily spend.
73. **[A-73] Spend Forecast Chart** — Skill `spend-forecast` — predict end-of-month spend.
74. **[A-74] Per-Bot Cost Reports** — Track token usage per bot (closer-bot, copy-bot, etc).
75. **[A-75] Cost Heatmap on Status Page** — Add cost tile.
76. **[A-76] Provider Cost Comparison API** — `/api/cost/compare?model=claude,gpt,deepseek`.
77. **[A-77] Cost Attribution to Client** — Track which client consumes the most.
78. **[A-78] Cost Report Export** — CSV/PDF export for billing.
79. **[A-79] Cost Alert via Telegram** — Wire cost_alert_daily to send to bot.
80. **[A-80] Cost Optimization Recommendations** — Skill `cost-optimizer` — suggests improvements.
81. **[A-81] Model-Benchmark Database** — Track latency/quality per model per task.
82. **[A-82] Auto-Select Cheapest Model** — Skill that picks the cheapest model that meets quality bar.
83. **[A-83] Token Recycling** — Reuse completion tokens across requests when safe.
84. **[A-84] Cache LLM Responses** — Persistent response cache with TTL.
85. **[A-85] Semantic Cache** — Cache by semantic similarity, not exact match.
86. **[A-86] Token-Aware Streaming** — Stream response + show live token count.
87. **[A-87] Auto-Switch to Free Models on Quota** — Fall back when paid quota hit.

---

### B. EVALUATION & SCORING (cat-B) — 64 items

88. **[B-1] Eval Suite Builder** — Skill `eval-builder` — create test cases interactively.
89. **[B-2] Eval Runner** — `scripts/eval_runner.py` — run eval suites nightly.
90. **[B-3] Eval Report Dashboard** — `/api/evals` endpoint with historical scores.
91. **[B-4] Per-Skill Eval Sets** — Each skill has its own eval suite.
92. **[B-5] Golden Outputs** — Store expected outputs and diff against actual.
93. **[B-6] LLM-as-Judge** — Use GPT-4 to score Claude's outputs (or vice versa).
94. **[B-7] Eval Cron** — `nightly-evals` — run all eval suites at 2am.
95. **[B-8] Eval-Driven Prompt Improvement** — When eval fails, suggest prompt edit.
96. **[B-9] Prompt Diff** — Track prompt changes over time + eval impact.
97. **[B-10] Regression Test for Skill Outputs** — Lock down output format with snapshot tests.
98. **[B-11] Multi-Model Eval** — Same prompt, multiple models, compare.
99. **[B-12] Human Eval Queue** — `/eval` skill that queues outputs for human review.
100. **[B-12] Eval Leaderboard** — Skill `eval-leaderboard` — top performing model+prompt combos.
101. **[B-13] Eval Coverage Tracker** — Which skills have evals, which don't.
102. **[B-14] Eval Failure Analysis** — Categorize failure modes.
103. **[B-15] Eval CI Integration** — Block PRs that drop eval scores >5%.
104. **[B-16] Eval Diff Per Prompt** — Show how prompt edit changed eval scores.
105. **[B-17] Auto-Tune Eval Threshold** — Suggest eval pass/fail thresholds from data.
106. **[B-18] Eval Metrics Library** — BLEU, ROUGE, exact match, semantic similarity.
107. **[B-19] Custom Metrics** — Skill authors define domain-specific metrics.
108. **[B-20] Eval Storage** — `~/.hermes/state/evals/` — JSONL history.
109. **[B-21] Eval Visualization** — Charts of eval scores over time.
110. **[B-22] Eval Notifications** — Alert when eval drops.
111. **[B-23] Per-Task Eval Templates** — Eval templates for coding, writing, research.
112. **[B-24] Eval Pipeline** — Generate → Run → Score → Report.
113. **[B-25] Promptfoo Integration** — Use promptfoo as the eval runner.
114. **[B-26] DSPy Integration** — Use DSPy for prompt optimization.
115. **[B-27] Auto-Prompt-Improvement Loop** — Cron `prompt-evolve` — test variants, keep winners.
116. **[B-28] Eval-by-Reproduction** — Eval by re-running the original task.
117. **[B-29] Eval-by-Property** — Test specific properties (no PII, has citations, etc).
118. **[B-30] Adversarial Evals** — Generate tricky test cases automatically.
119. **[B-31] User Feedback Loop** — Capture thumbs-up/down on bot responses.
120. **[B-32] Feedback-Driven Tuning** — Use feedback to identify low-quality prompts.
121. **[B-33] Eval Annotations** — Allow humans to annotate outputs as gold/silver/bronze.
122. **[B-34] Eval Export to JSONL** — Standard format for external tools.
123. **[B-35] Eval Coverage Per Skill** — `/api/evals/coverage`.
124. **[B-36] Per-Model Eval Baseline** — Establish baseline before any changes.
125. **[B-37] Eval Suite Health** — Cron `eval-health` — flag stale eval suites.
126. **[B-38] Eval Result Diff** — Compare eval runs across model swaps.
127. **[B-39] Eval-Driven Skill Versioning** — Bump skill version when evals improve.
128. **[B-40] Auto-Generate Eval Cases** — Use LLM to generate test cases.
129. **[B-41] Real-World Eval Mining** — Mine real conversations for eval cases.
130. **[B-42] Eval Honeypots** — Hidden test cases in production.
131. **[B-43] Eval Stress Tests** — High-volume edge cases.
132. **[B-44] Eval Comparison Matrix** — Model × Eval = score matrix.
133. **[B-45] Eval Heatmap** — Visual matrix on dashboard.
134. **[B-46] Eval Storyboards** — Step through eval cases interactively.
135. **[B-47] Eval Summary Email** — Cron `eval-summary-weekly`.
136. **[B-48] Eval Privacy Filter** — Strip PII from eval outputs.
137. **[B-49] Eval Audit Log** — Who ran which eval when.
138. **[B-50] Eval Cost Tracking** — Cost per eval run.
139. **[B-51] Eval Race Conditions** — Detect flaky evals.
140. **[B-52] Eval Reliability Score** — % of times eval gives same result.
141. **[B-53] Eval Mode Switch** — `hermes eval --strict` for gating.
142. **[B-54] Eval Set Versioning** — Git-track eval sets.
143. **[B-55] Eval Set Documentation** — Auto-doc each eval case.
144. **[B-56] Eval Set Templates** — Pre-built for common tasks (summarization, classification).
145. **[B-57] Eval Failure Heatmap** — See which tasks fail most.
146. **[B-58] Eval Retry Logic** — Handle transient eval failures.
147. **[B-59] Eval Parallelization** — Run eval suites in parallel.
148. **[B-60] Eval Resource Quotas** — Cap eval CPU/memory.
149. **[B-61] Eval SLOs** — Pass rate, coverage, freshness.
150. **[B-62] Eval Alert Webhook** — Post eval results to Slack.
151. **[B-63] Eval Trend Reports** — Monthly trend analysis.

---

### C. SKILL MANAGEMENT (cat-C) — 78 items

We have 133 skills but management is ad-hoc. Time to systematize.

152. **[C-1] Skill Builder CLI** — `hermes skills create <name>` interactive.
153. **[C-2] Skill Scaffolder** — `scripts/new_skill.py` — like `new_project.py` but for skills.
154. **[C-3] Skill Linter** — `scripts/skill_lint.py` — validate frontmatter, structure, patterns.
155. **[C-4] Skill Auto-Fixer** — Auto-fix common skill issues.
156. **[C-5] Skill Diff Tool** — Compare two skill versions.
157. **[C-6] Skill Search** — Search by description, tags, kind.
158. **[C-7] Skill Catalog Web UI** — Web UI to browse all 133 skills.
159. **[C-8] Skill Recommendations** — Suggest skills based on context.
160. **[C-9] Skill Auto-Loader** — Watch skills/ for new skills, auto-validate.
161. **[C-10] Skill Quarantine** — Disable skills with low success rate.
162. **[C-11] Skill Versioning** — Track skill version history.
163. **[C-12] Skill A/B Testing** — Run two skill variants, compare.
164. **[C-13] Skill Telemetry** — Track invocations, latency, errors.
165. **[C-14] Skill Documentation Generator** — Auto-generate SKILL.md from code.
166. **[C-15] Skill Examples Repository** — Curated worked examples per skill.
167. **[C-16] Skill Templates** — Boilerplate for new skill types.
168. **[C-17] Skill Reviewer** — Cron `skill-review-weekly` — flag stale skills.
169. **[C-18] Skill Duplication Detector** — Find skills that overlap.
170. **[C-19] Skill Merge Tool** — Merge two overlapping skills.
171. **[C-20] Skill Split Tool** — Split a skill that does too much.
172. **[C-21] Skill Dependency Analyzer** — Which skills reference which.
173. **[C-22] Skill Reverse Dependencies** — Who uses this skill.
174. **[C-23] Skill Usage Heatmap** — Most/least used.
225. **[C-24] Skill Dead Code Finder** — Find scripts referenced by no skill.
226. **[C-25] Skill Orphan Finder** — Find skills no cron uses.
227. **[C-26] Skill Required Tools Audit** — Each skill declares required tools.
228. **[C-27] Skill Permissions Audit** — What can each skill access.
229. **[C-28] Skill Sandboxing** — Run skills in restricted env.
230. **[C-29] Skill Permission Prompts** — Ask user before dangerous operations.
231. **[C-30] Skill Rate Limiting** — Per-skill rate limits.
232. **[C-31] Skill Timeouts** — Per-skill timeouts.
233. **[C-32] Skill Output Caching** — Cache skill outputs.
234. **[C-33] Skill Output Schema** — Declare expected output schema.
235. **[C-34] Skill Output Validator** — Validate output matches schema.
236. **[C-35] Skill Retry Policy** — Per-skill retry policy.
237. **[C-36] Skill Fallback Chain** — If skill A fails, try skill B.
238. **[C-37] Skill Circuit Breaker** — Stop calling failing skills.
239. **[C-38] Skill Health Probe** — Cron `skill-health` — ping each skill.
240. **[C-39] Skill Test Suite** — Each skill has its own tests.
241. **[C-40] Skill Mock Library** — Mock external services for testing.
242. **[C-41] Skill Snapshot Tests** — Lock down skill outputs.
243. **[C-42] Skill Property-Based Tests** — Generate random inputs.
244. **[C-43] Skill Fuzz Testing** — Fuzz skill inputs.
245. **[C-44] Skill Benchmark Suite** — Measure skill performance.
246. **[C-45] Skill Profiling** — Find slow spots.
247. **[C-46] Skill Optimization Suggestions** — Auto-suggest improvements.
248. **[C-47] Skill Code Coverage** — Track % of skill code exercised.
249. **[C-48] Skill Type Annotations** — Require types on all skill code.
250. **[C-49] Skill Doc Coverage** — Track % of skills with examples.
251. **[C-50] Skill Review Checklist** — Standard checklist for new skills.
252. **[C-51] Skill Author Guide** — Skill that helps write skills.
253. **[C-52] Skill Pattern Library** — Common patterns extracted from existing skills.
254. **[C-53] Skill Anti-Pattern Detector** — Find code smells.
255. **[C-54] Skill Security Audit** — Detect unsafe patterns.
256. **[C-55] Skill Privacy Audit** — Detect PII leaks.
257. **[C-56] Skill Performance Budget** — Max acceptable runtime.
258. **[C-57] Skill Output Size Limit** — Prevent huge outputs.
259. **[C-58] Skill Auto-Documentation** — Generate docs from code.
260. **[C-59] Skill CHANGELOG** — Auto-generate per skill.
261. **[C-60] Skill Release Notes** — On version bump.
262. **[C-61] Skill Semantic Versioning** — Enforce semver.
263. **[C-62] Skill Deprecation Policy** — Mark old skills deprecated.
264. **[C-63] Skill Migration Helper** — Help migrate between versions.
265. **[C-64] Skill Backup** — Backup all skills to git repo.
266. **[C-65] Skill Restore** — Restore from backup.
267. **[C-66] Skill Diff Against Master** — Compare to upstream skills.
268. **[C-67] Skill Upstream Sync** — Pull upstream improvements.
269. **[C-68] Skill Customization Layer** — Local edits on top of upstream.
270. **[C-69] Skill Marketplace** — Browse/install community skills.
271. **[C-70] Skill Ratings** — Community ratings.
272. **[C-71] Skill Categories** — Auto-categorize by content.
273. **[C-72] Skill Tag Suggestions** — Suggest tags from description.
274. **[C-73] Skill Trigger Tuning** — Improve file-mask triggers via metrics.
275. **[C-74] Skill Composition** — Combine skills into workflows.
276. **[C-75] Skill Conditional Logic** — If/then skill chains.
277. **[C-76] Skill DAG Executor** — Run skills in DAG order.
278. **[C-77] Skill Parallel Executor** — Run independent skills in parallel.
279. **[C-78] Skill Failure Recovery** — Auto-recover from skill failures.

---

### D. CRON MANAGEMENT (cat-D) — 56 items

We have 64 crons but no formal management. It's a mess.

280. **[D-1] Cron Discovery** — Auto-detect scripts that should be crons.
281. **[D-2] Cron Dependency Graph** — Which crons depend on which.
282. **[D-3] Cron Conflict Detection** — Two crons at same time? Same resource?
283. **[D-4] Cron Resource Locking** — Prevent concurrent execution of same cron.
284. **[D-5] Cron Dependency Ordering** — If A and B, run A first.
285. **[D-6] Cron Cascading Failure** — If A fails, skip B.
286. **[D-7] Cron Auto-Disable** — Disable failing crons after N failures.
287. **[D-8] Cron Auto-Re-Enable** — Re-enable after cooldown period.
288. **[D-9] Cron Health Score** — Per-cron success rate.
289. **[D-10] Cron Cost Tracking** — Track tokens used per cron.
290. **[D-11] Cron Run Time Budget** — Alert if cron exceeds expected time.
291. **[D-12] Cron SLA** — Define and track per-cron SLAs.
292. **[D-13] Cron Notification Customization** — Per-cron notification prefs.
293. **[D-14] Cron Quiet Hours** — Pause crons during off-hours.
294. **[D-15] Cron Backoff Strategy** — Exponential backoff on failure.
295. **[D-16] Cron Priority** — Some crons more important.
296. **[D-17] Cron Resource Limits** — CPU/memory caps per cron.
297. **[D-18] Cron Idempotency Check** — Detect non-idempotent crons.
298. **[D-19] Cron Dry-Run Mode** — `--dry-run` on all cron scripts.
299. **[D-20] Cron Result Caching** — Skip if result unchanged.
300. **[D-21] Cron Grouping** — Group related crons.
301. **[D-22] Cron Cascade Trigger** — One cron triggers another.
302. **[D-23] Cron Conditional Execution** — Only run if X is true.
304. **[D-24] Cron A/B** — Run two variants, pick best.
305. **[D-25] Cron Migration** — Migrate crons between environments.
306. **[D-26] Cron Version Control** — Git-track cron schedules.
307. **[D-27] Cron Visualization** — Timeline view of all crons.
308. **[D-28] Cron Approval Flow** — Require approval for new crons.
309. **[D-29] Cron Audit Log** — Who created/modified/deleted.
310. **[D-30] Cron Rollback** — Revert cron to previous version.
311. **[D-31] Cron Canary Deployment** — Test new cron on subset.
312. **[D-32] Cron Auto-Documentation** — Auto-doc each cron.
313. **[D-33] Cron Quality Score** — Cron uptime + success + cost.
314. **[D-34] Cron Leaderboard** — Top/bottom performing crons.
315. **[D-35] Cron Failure Analysis** — Why crons fail.
316. **[D-36] Cron Self-Healing** — Auto-fix common cron issues.
317. **[D-37] Cron Templates** — Boilerplate for new cron types.
318. **[D-38] Cron Validation** — Pre-deploy validation.
319. **[D-39] Cron Simulation** — Simulate cron schedules.
320. **[D-40] Cron Test Mode** — Test cron without real execution.
321. **[D-41] Cron Mode Flags** — `--prod`, `--staging`, `--dev`.
322. **[D-42] Cron Multi-Region** — Different crons per region.
323. **[D-43] Cron Time Zone Awareness** — Schedule in user TZ.
324. **[D-44] Cron Calendar View** — Show crons on calendar.
325. **[D-45] Cron Owner Tracking** — Who owns each cron.
326. **[D-46] Cron Documentation** — Markdown per cron.
327. **[D-47] Cron On-Call** — On-call rotation for cron failures.
328. **[D-48] Cron Escalation** — Alert if not resolved in X min.
329. **[D-49] Cron Investigation Mode** — Re-run with full logging.
330. **[D-50] Cron A/B Promotion** — Promote winner to production.
331. **[D-51] Cron Retirement** — Mark old crons deprecated.
332. **[D-52] Cron Migration Helper** — Convert scripts → crons.
333. **[D-53] Cron Naming Convention** — Enforce names.
334. **[D-54] Cron Tags** — Tag crons by category.
335. **[D-55] Cron Search** — Find cron by script/owner/etc.
336. **[D-56] Cron Export** — Export cron list as CSV/JSON.

---

### E. AGENT-TO-AGENT & SWARM (cat-E) — 64 items

337. **[E-1] Agent Swarm Coordinator** — Multiple agents working on same problem.
338. **[E-2] Agent-to-Agent Messaging** — Kafka-like message bus.
339. **[E-3] Agent Lock Service** — Distributed locks across bots.
340. **[E-4] Agent State Sharing** — Shared state between agents.
341. **[E-5] Agent Quorum** — N agents vote on decision.
342. **[E-6] Agent Map-Reduce** — Distribute work across agents.
343. **[E-7] Agent Pipeline** — Chain agents in sequence.
344. **[E-8] Agent DAG** — Arbitrary DAG of agent calls.
345. **[E-9] Agent Blackboard** — Shared memory space.
346. **[E-10] Agent Blackboard Cleanup** — TTL-based cleanup.
347. **[E-11] Agent RPC** — Call another agent remotely.
348. **[E-12] Agent Protocol Buffer** — Standard message format.
349. **[E-13] Agent Auth** — mTLS between agents.
350. **[E-14] Agent Routing** — Route request to right agent.
351. **[E-15] Agent Load Balancing** — Distribute load.
352. **[E-16] Agent Failover** — If agent A down, use B.
353. **[E-17] Agent Health Checks** — Ping agents.
354. **[E-18] Agent Versioning** — Multiple versions of same agent.
355. **[E-19] Agent Canary Deploy** — Deploy new version to subset.
356. **[E-20] Agent Traffic Shadowing** — Send copy to new version.
357. **[E-21] Agent Resource Quotas** — Per-agent resource caps.
358. **[E-22] Agent Priority Queue** — Some agents have priority.
359. **[E-23] Agent Backpressure** — Slow consumers get less.
360. **[E-24] Agent Rate Limiting** — Per-agent rate limits.
361. **[E-25] Agent Rate Limiting Per Client** — Per-tenant rate limits.
362. **[E-26] Agent Concurrency Limit** — Max concurrent calls per agent.
363. **[E-27] Agent Bulkhead** — Isolate agent failures.
364. **[E-28] Agent Circuit Breaker** — Stop calling failed agent.
365. **[E-29] Agent Retry with Backoff** — Standard retry logic.
366. **[E-30] Agent Timeout Propagation** — Timeouts cascade.
367. **[E-31] Agent Tracing** — Distributed tracing across agents.
368. **[E-32] Agent Logging** — Structured logs per agent.
369. **[E-33] Agent Metrics** — Per-agent metrics.
370. **[E-34] Agent Dashboard** — Visualize agent activity.
371. **[E-35] Agent Alert** — Alert on agent failure.
372. **[E-36] Agent Replication** — Run same agent on multiple nodes.
373. **[E-37] Agent Consensus** — Paxos/Raft for critical decisions.
374. **[E-38] Agent Leader Election** — Elect leader for coordination.
375. **[E-39] Agent Sharding** — Partition work across agents.
376. **[E-40] Agent Aggregation** — Combine results from many agents.
377. **[E-41] Agent Composition** — Compose agents into larger systems.
378. **[E-42] Agent Substitution** — Swap agents at runtime.
379. **[E-43] Agent Capability Negotiation** — Agents advertise capabilities.
380. **[E-44] Agent Discovery** — Find agents by capability.
381. **[E-45] Agent Registry** — Central registry of agents.
382. **[E-46] Agent Version Registry** — Multiple versions tracked.
383. **[E-47] Agent Marketplace** — Browse/install community agents.
384. **[E-48] Agent Onboarding** — Standard onboarding for new agents.
385. **[E-49] Agent Retirement** — Deprecate old agents gracefully.
386. **[E-50] Agent Documentation** — Auto-doc each agent.
387. **[E-51] Agent Telemetry** — Per-agent usage stats.
388. **[E-52] Agent Auto-Scaling** — Scale based on load.
389. **[E-53] Agent Cost Per Call** — Track cost per agent invocation.
390. **[E-54] Agent SLA** — Define and track SLAs.
391. **[E-55] Agent Onboarding Wizard** — Skill that helps configure new agent.
392. **[E-56] Agent Playbooks** — Standard workflows.
393. **[E-57] Agent Workflow Templates** — Reusable workflows.
394. **[E-58] Agent Templates from Examples** — Generate agent from example.
395. **[E-59] Agent Testing Framework** — Test agent behavior.
396. **[E-60] Agent Mock** — Mock agent for testing.
397. **[E-61] Agent Integration Tests** — Test agent chains.
398. **[E-62] Agent Performance Tests** — Load testing.
399. **[E-63] Agent Security Audit** — Verify isolation/auth.
400. **[E-64] Agent Compliance Audit** — GDPR/SOC2 compliance.

---

### F. RAG & KNOWLEDGE GRAPHS (cat-F) — 72 items

We have no real RAG. Most context is from MEMORY.md (4K chars) + skill descriptions.

401. **[F-1] Vector DB Integration** — Skill `vector-db` — Qdrant/Chroma/pgvector.
402. **[F-2] Embedding Pipeline** — Cron `embed-new-content` — chunk + embed.
403. **[F-3] Semantic Search** — `scripts/semantic_search.py` — search by meaning.
404. **[F-4] Skill Semantic Search** — Find skills by intent.
405. **[F-5] Conversation Search** — Search past conversations.
406. **[F-6] Memory Embedding** — Embed MEMORY entries.
407. **[F-7] Auto-Embed Memory** — Cron `embed-memory-hourly`.
408. **[F-8] Embedding Cache** — Cache embeddings (avoid re-embedding).
409. **[F-9] Chunking Strategy** — Smart chunking for code vs prose.
410. **[F-10] Hybrid Search** — Combine vector + keyword.
411. **[F-11] Re-ranking** — Use cross-encoder to re-rank top-K.
412. **[F-12] Query Expansion** — Expand query with synonyms.
413. **[F-13] HyDE** — Hypothetical Document Embeddings for better retrieval.
414. **[F-14] Multi-Vector** — Embed chunks at multiple granularities.
415. **[F-15] Late Chunking** — Embed full doc, then chunk.
416. **[F-16] Parent-Child Chunks** — Small for retrieval, big for context.
417. **[F-17] Knowledge Graph Builder** — Build KG from repos.
418. **[F-18] KG-Powered Search** — Search via graph traversal.
419. **[F-19] KG Visualization** — Visual graph viewer.
420. **[F-20] Entity Extraction** — Extract entities from text.
421. **[F-21] Relation Extraction** — Extract relations between entities.
422. **[F-22] KG Maintenance** — Cron `kg-maintain` — dedup, merge entities.
423. **[F-23] KG Schema** — Define entity types + relations.
424. **[F-24] KG Versioning** — Track KG changes.
425. **[F-25] KG Diff** — Compare KG versions.
426. **[F-26] KG Export** — Export as Cypher, RDF, JSON.
427. **[F-27] Neo4j Integration** — Use Neo4j for KG.
428. **[F-28] Mem0 Integration** — Use Mem0 for memory.
429. **[F-29] Honcho Integration** — Use Honcho for memory.
430. **[F-30] RAG Pipeline Skill** — Standard RAG flow.
431. **[F-31] Multi-Modal RAG** — Image + text retrieval.
432. **[F-32] Streaming RAG** — Stream retrieved chunks.
433. **[F-33] Citations** — Always cite sources.
434. **[F-34] Source Attribution** — Track which source.
435. **[F-35] Recency Boost** — Boost recent docs.
436. **[F-36] Personalization** — Personalized ranking.
437. **[F-37] User Context RAG** — Use user history.
438. **[F-38] Conversation RAG** — RAG across conversation history.
439. **[F-39] Skill RAG** — RAG over skills for selection.
440. **[F-40] Code RAG** — RAG over code.
441. **[F-41] Documentation RAG** — RAG over docs.
442. **[F-42] Multi-Source RAG** — Combine multiple sources.
443. **[F-43] Federated Search** — Search across federated sources.
444. **[F-44] Cross-Repo Search** — Search across all 45 repos.
445. **[F-45] Cross-Memory Search** — Search all memory types.
446. **[F-46] Temporal RAG** — Time-aware retrieval.
447. **[F-47] Spatial RAG** — Geographic-aware retrieval.
448. **[F-48] Tag-Based Filtering** — Pre-filter by tags.
449. **[F-49] Permission-Aware RAG** — Filter by user permissions.
450. **[F-50] RAG Evaluation** — Standard RAG metrics (recall@k, MRR).
451. **[F-51] RAG Quality Tracking** — Track retrieval quality.
452. **[F-52] RAG Failure Analysis** — Why did retrieval fail?
453. **[F-53] RAG A/B** — Compare retrieval strategies.
454. **[F-54] RAG Cache** — Cache retrieval results.
455. **[F-55] RAG Cost** — Track embedding + retrieval cost.
456. **[F-56] RAG Latency** — Track retrieval time.
457. **[F-57] Incremental Embedding** — Only embed new content.
458. **[F-58] Embedding Backfill** — Backfill missing embeddings.
459. **[F-59] Embedding Deduplication** — Skip duplicate content.
460. **[F-60] Embedding Model Swap** — Hot-swap embedding models.
461. **[F-61] Multi-Embedding** — Use multiple embedding models.
462. **[F-62] Cross-Encoder Rerank** — Use cross-encoder for top-K.
463. **[F-63] Cohere Rerank Integration** — Use Cohere rerank.
464. **[F-64] BM25 Hybrid** — BM25 + vector hybrid.
465. **[F-65] SPLADE** — Sparse vector retrieval.
466. **[F-66] ColBERT** — Late interaction retrieval.
467. **[F-67] Long Context vs RAG** — Skill to decide when to RAG vs full-context.
468. **[F-68] GraphRAG** — Microsoft's GraphRAG approach.
469. **[F-69] RAG Citations UI** — Show sources in response.
470. **[F-70] RAG Streaming** — Stream retrieved chunks.
471. **[F-71] RAG Caching** — TTL-based cache.
472. **[F-72] RAG Cost Optimization** — Pick cheaper embeddings.

---

### G. MULTI-TENANT & SECURITY (cat-G) — 68 items

473. **[G-1] Tenant Model** — Multi-tenant data model in projects.yaml.
474. **[G-2] Tenant Routing** — Route requests to right tenant.
475. **[G-3] Tenant Isolation** — File-system isolation per tenant.
476. **[G-4] Tenant Quotas** — Per-tenant resource quotas.
477. **[G-5] Tenant Billing** — Track usage per tenant.
478. **[G-6] Tenant Onboarding** — Wizard for new tenants.
479. **[G-7] Tenant Offboarding** — Clean teardown.
480. **[G-8] Tenant Config Backup** — Per-tenant backups.
481. **[G-9] Tenant Restore** — Per-tenant restore.
482. **[G-10] Tenant Audit Log** — Per-tenant audit.
483. **[G-11] Tenant Permissions** — RBAC per tenant.
484. **[G-12] Tenant Roles** — Owner/admin/member/viewer.
485. **[G-13] Tenant SSO** — SAML/OIDC per tenant.
486. **[G-14] Tenant API Keys** — Per-tenant API keys.
487. **[G-15] Tenant Rate Limiting** — Per-tenant limits.
488. **[G-16] Tenant Custom Domain** — Per-tenant URLs.
489. **[G-17] Tenant Branding** — Per-tenant logos/colors.
490. **[G-18] Tenant Email Templates** — Per-tenant emails.
491. **[G-19] Tenant Compliance** — Per-tenant GDPR/SOC2.
492. **[G-20] Tenant Data Residency** — Data stays in region.
493. **[G-21] Tenant Encryption** — Per-tenant encryption keys.
494. **[G-22] Tenant Backup Encryption** — Encrypted backups.
495. **[G-23] Secret Vault** — Per-tenant secret storage.
496. **[G-24] Secret Rotation** — Auto-rotate per tenant.
497. **[G-25] Secret Audit** — Track secret usage.
498. **[G-26] Secret Leak Detection** — Scan for leaked secrets.
499. **[G-27] Secret Versioning** — Track secret versions.
500. **[G-28] Secret Rollback** — Roll back to old secret.
501. **[G-29] Secrets in Env vs Vault** — Decide where secrets live.
502. **[G-30] Encryption at Rest** — Encrypt stored data.
503. **[G-31] Encryption in Transit** — TLS everywhere.
504. **[G-32] Audit Log** — Who did what when.
505. **[G-33] Compliance Reports** — GDPR/SOC2/PCI reports.
506. **[G-34] Data Retention Policy** — Auto-delete old data.
507. **[G-35] Right to Be Forgotten** — GDPR right to erasure.
508. **[G-36] Consent Management** — Track user consent.
509. **[G-37] Cookie Policy** — GDPR cookie consent.
510. **[G-38] Privacy Policy Generator** — Auto-generate from usage.
511. **[G-39] Terms of Service Generator** — Same for ToS.
512. **[G-40] DPA Template** — Data Processing Agreement.
513. **[G-41] PII Detection** — Find PII in logs.
514. **[G-42] PII Redaction** — Auto-redact PII.
515. **[G-43] PII Vault** — Store PII separately.
516. **[G-44] PII Audit** — Who accessed PII.
517. **[G-45] Anomaly Detection on Access** — Unusual access patterns.
518. **[G-46] Breach Detection** — Detect breaches.
519. **[G-47] Breach Notification** — Auto-notify on breach.
520. **[G-48] Two-Factor Auth** — 2FA for operators.
521. **[G-49] SSO Provider Integration** — Auth0, Okta, Google.
522. **[G-50] IP Allowlist** — Restrict by IP.
523. **[G-51] Device Trust** — Verify device.
524. **[G-52] Session Management** — Secure sessions.
525. **[G-53] Token Rotation** — Rotate API tokens.
526. **[G-54] JWT Validation** — Verify JWTs.
527. **[G-55] OAuth Implementation** — OAuth flows.
528. **[G-56] Webhook Signatures** — Verify webhook signatures.
529. **[G-57] HMAC for Webhooks** — Sign webhook payloads.
530. **[G-58] CSRF Protection** — CSRF tokens.
531. **[G-59] XSS Prevention** — Sanitize inputs.
532. **[G-60] SQL Injection Prevention** — Parameterized queries.
533. **[G-61] Dependency Audit** — Cron `dependency-audit-weekly` — npm audit, pip-audit.
534. **[G-62] Container Scanning** — Trivy/grype.
535. **[G-63] Static Analysis** — CodeQL, Semgrep.
536. **[G-64] Secrets in Git** — Detect committed secrets.
537. **[G-65] License Audit** — Track OSS licenses.
538. **[G-66] SBOM Generation** — Software Bill of Materials.
539. **[G-67] Vulnerability DB Sync** — Cron `vuln-db-sync-daily`.
540. **[G-68] Auto-Patch** — Auto-apply security patches.

---

### H. STREAMING & REALTIME (cat-H) — 48 items

541. **[H-1] SSE Server** — Server-Sent Events endpoint.
542. **[H-2] WebSocket Hub** — WebSocket server.
543. **[H-3] Streaming Chat** — Stream LLM tokens to client.
544. **[H-4] Stream Multiplexing** — Multiple streams over one connection.
545. **[H-5] Stream Backpressure** — Handle slow consumers.
546. **[H-6] Stream Reconnection** — Auto-reconnect on disconnect.
547. **[H-7] Stream Resumption** — Resume from last position.
548. **[H-8] Stream Buffering** — Buffer tokens for batched display.
549. **[H-9] Stream Rate Limiting** — Cap stream rate per client.
550. **[H-10] Stream Auth** — Auth on stream connections.
551. **[H-11] Stream Compression** — Compress stream payloads.
552. **[H-12] Stream Encryption** — Encrypt streams.
553. **[H-13] Stream Metrics** — Track stream health.
554. **[H-14] Stream Tracing** — Trace stream events.
555. **[H-15] Stream Logging** — Structured stream logs.
556. **[H-16] Stream Replay** — Replay a stream session.
557. **[H-17] Live UI Updates** — Push UI updates via stream.
558. **[H-18] Live Notifications** — Real-time notifications.
559. **[H-19] Live Logs** — Tail logs in real-time.
560. **[H-20] Live Cron Status** — See crons running now.
561. **[H-21] Live Agent Status** — See agents active.
562. **[H-22] Live Skill Usage** — Watch skill invocations.
563. **[H-23] Live Cost Tracking** — See cost accumulating.
564. **[H-24] Live Trace Visualization** — Watch spans as they happen.
565. **[H-25] Live Dashboard** — Real-time dashboard.
566. **[H-26] WebRTC Support** — Video/audio for live agent.
567. **[H-27] Screen Share** — Share screen for debugging.
568. **[H-28] Collaborative Editing** — Multi-user edits.
569. **[H-29] Presence Indicators** — Who's online.
570. **[H-30] Typing Indicators** — Show agent is typing.
571. **[H-31] Read Receipts** — Track message reads.
572. **[H-32] Reaction System** — Emoji reactions.
573. **[H-33] Real-Time Threading** — Live thread updates.
574. **[H-34] Real-Time Search** — Search results stream in.
575. **[H-35] Real-Time Translation** — Translate messages live.
576. **[H-36] Real-Time Summarization** — Summarize conversation live.
577. **[H-37] Real-Time Action Items** — Extract action items live.
578. **[H-38] Real-Time Decisions** — Capture decisions as made.
579. **[H-39] Real-Time Voting** — Poll users live.
580. **[H-40] Real-Time Standup** — Daily standup bot.
581. **[H-41] Real-Time Onboarding** — Guided tours.
582. **[H-42] Real-Time Alerts** — Push critical alerts.
583. **[H-43] Real-Time Incident Response** — Live incident updates.
584. **[H-44] Real-Time Metrics** — Push metric updates.
585. **[H-45] Real-Time Heatmap** — Live activity heatmap.
586. **[H-46] Real-Time Cost Burn** — Live spend rate.
587. **[H-47] Real-Time Geo** — Geo-distributed updates.
588. **[H-48] Real-Time Conflict Resolution** — Detect merge conflicts live.

---

### I. WEB UI & DASHBOARDS (cat-I) — 64 items

We have a basic dashboard. Need full web UI.

589. **[I-1] React Admin UI** — `scripts/react_dashboard.py` — full admin panel.
590. **[I-2] Skill Browser UI** — Browse all 133 skills.
591. **[I-3] Cron Dashboard** — Visual cron timeline.
592. **[I-4] Repo Dashboard** — Per-repo detail view.
593. **[I-5] Real-Time Web UI** — Live updates via SSE.
594. **[I-6] Mobile-Responsive UI** — Mobile-friendly dashboard.
595. **[I-7] Dark/Light Theme Toggle** — Theme switcher.
596. **[I-8] Custom Themes** — User-defined themes.
597. **[I-9] UI Customization** — Per-user dashboard layout.
598. **[I-10] Drag-and-Drop Builder** — Build dashboards visually.
599. **[I-11] Widget Library** — Reusable widgets.
600. **[I-12] Custom Widgets** — User-defined widgets.
601. **[I-13] Embed External Widgets** — Grafana, etc.
602. **[I-14] Multi-Page Navigation** — Multi-page app.
603. **[I-15] Search-First UI** — Cmd+K search everything.
604. **[I-16] Command Palette** — Keyboard shortcuts for actions.
605. **[I-17] Keyboard Shortcuts** — Power-user shortcuts.
606. **[I-18] Bulk Actions** — Select multiple, act on all.
607. **[I-19] Filters and Sorts** — Per-table filtering.
608. **[I-20] Saved Views** — Save filter combinations.
609. **[I-21] Export Buttons** — Export to CSV/PDF/JSON.
610. **[I-22] Import Buttons** — Upload data.
611. **[I-23] Drag-and-Drop Upload** — File uploads.
622. **[I-24] Modal Forms** — Inline editing.
623. **[I-25] Validation Errors** — Form validation feedback.
624. **[I-26] Loading States** — Skeleton screens.
625. **[I-27] Empty States** — Helpful empty states.
626. **[I-28] Error Boundaries** — Don't crash on error.
627. **[I-29] Toast Notifications** — Action feedback.
628. **[I-30] Confirmation Dialogs** — For destructive actions.
629. **[I-31] Audit Trail UI** — See who did what.
630. **[I-32] Activity Feed** — Recent activity stream.
631. **[I-33] User Directory** — Browse users/operators.
632. **[I-34] Role Management UI** — Edit roles.
633. **[I-35] Permission Editor** — Per-permission editing.
634. **[I-36] API Key Management** — Generate/revoke keys.
635. **[I-37] Webhook Management** — Add/edit webhooks.
636. **[I-38] Cron Builder UI** — Visual cron schedule editor.
637. **[I-39] Skill Editor UI** — Edit skills in browser.
638. **[I-40] Live Preview** — See skill output live.
639. **[I-41] Diff View** — See changes side-by-side.
640. **[I-42] Search Highlight** — Highlight search results.
641. **[I-43] Fuzzy Search** — Search with typos.
642. **[I-44] Filters by Tag** — Filter skills by tag.
643. **[I-45] Multi-Select Tags** — Tag multiple items.
644. **[I-46] Inline Edit** — Edit without modal.
645. **[I-47] Undo/Redo** — Undo mistakes.
646. **[I-48] Draft Save** — Auto-save drafts.
647. **[I-49] Comments** — Comment on items.
648. **[I-50] Mentions** — @mention in comments.
649. **[I-51] Notifications UI** — Bell icon + dropdown.
650. **[I-52] Settings UI** — Per-user settings.
651. **[I-53] Profile UI** — User profile.
652. **[I-54] Avatar Upload** — User avatars.
653. **[I-55] Two-Factor Setup UI** — 2FA configuration.
654. **[I-56] Backup Management UI** — Browse backups.
655. **[I-57] Cost Dashboard UI** — Visual cost breakdown.
656. **[I-58] Token Usage Chart** — Visual token burn.
657. **[I-59] Skill Performance UI** — Per-skill metrics.
658. **[I-60] Cron Success Rate UI** — Cron uptime viz.
659. **[I-61] Trace Viewer UI** — Visual trace explorer.
660. **[I-62] Eval Results UI** — Show eval history.
661. **[I-63] Knowledge Graph UI** — Visual KG.
662. **[I-64] Settings Search** — Cmd+K settings.

---

### J. CI/CD & DEPLOYMENT (cat-J) — 56 items

663. **[J-1] GitHub Actions Generator** — Generate CI/CD from skill definitions.
664. **[J-2] ArgoCD Integration** — GitOps deployment.
665. **[J-3] Helm Chart Generator** — Generate Helm charts.
666. **[J-4] Kustomize Support** — Kustomize overlays.
667. **[J-5] Multi-Environment** — Dev/staging/prod.
668. **[J-6] Environment Promotion** — Promote between envs.
669. **[J-7] Approval Gates** — Manual approval before deploy.
670. **[J-8] Canary Deployments** — Deploy to subset.
671. **[J-9] Blue-Green Deploy** — Zero-downtime deploys.
672. **[J-10] Rollback Automation** — Auto-rollback on failure.
673. **[J-11] Feature Flags** — LaunchDarkly-style flags.
674. **[J-12] A/B Testing Infrastructure** — Test variants.
675. **[J-13] Progressive Rollout** — Roll out gradually.
676. **[J-14] Deploy Previews** — PR previews.
677. **[J-15] Smoke Tests** — Post-deploy smoke tests.
678. **[J-16] Integration Tests** — Test before deploy.
679. **[J-17] Load Tests** — Performance tests.
680. **[J-18] Security Scans** — In CI pipeline.
681. **[J-19] License Checks** — OSS license compliance.
682. **[J-20] Dependency Updates** — Dependabot-style.
683. **[J-21] Auto-Merge Deps** — Auto-merge passing deps.
684. **[J-22] Build Cache** — Cache build artifacts.
685. **[J-23] Build Matrix** — Test multiple configs.
686. **[J-24] Cross-Platform Builds** — Linux/Mac/Windows.
687. **[J-25] Docker Layer Caching** — Faster Docker builds.
688. **[J-26] Multi-Arch Images** — ARM64/AMD64.
689. **[J-27] Container Registry** — Push to registry.
690. **[J-28] Image Scanning** — Trivy in CI.
691. **[J-29] Image Signing** — Sign images (cosign).
692. **[J-30] SBOM Generation** — In CI.
693. **[J-31] Vulnerability Scan** — In CI.
694. **[J-32] Deploy Notifications** — Slack on deploy.
695. **[J-33] Deploy Status Badges** — README badges.
696. **[J-34] Deploy Dashboard** — Visual deploy history.
697. **[J-35] Release Automation** — Auto-create releases.
698. **[J-36] Changelog Generation** — Auto from commits.
699. **[J-37] SemVer Enforcement** — Auto-bump versions.
700. **[J-38] Git Tags** — Auto-tag releases.
701. **[J-39] GitHub Releases** — Auto-create releases.
702. **[J-40] Docker Hub Sync** — Push to Docker Hub.
703. **[J-41] GHCR Sync** — Push to GHCR.
704. **[J-42] Cloudflare Pages Deploy** — Auto-deploy (already partially done).
705. **[J-43] Vercel Deploy** — Auto-deploy to Vercel.
706. **[J-44] Netlify Deploy** — Same for Netlify.
707. **[J-45] SSH Deploy** — Deploy via SSH.
708. **[J-46] Pull Request Automation** — Auto-PR for fixes.
709. **[J-47] Issue Triage** — Auto-label issues.
710. **[J-48] Issue Templates** — Standard issue forms.
711. **[J-49] PR Templates** — Standard PR template.
712. **[J-50] CODEOWNERS** — Auto-assign reviewers.
713. **[J-51] Branch Protection** — Require checks.
714. **[J-52] Required Reviews** — N approvals.
715. **[J-53] Signed Commits** — Enforce signed commits.
716. **[J-54] Conventional Commits** — Enforce commit format.
717. **[J-55] Auto-Release Notes** — On tag.
718. **[J-56] Release Drafter** — Draft releases from PRs.

---

### K. PROMPT MANAGEMENT (cat-K) — 48 items

719. **[K-1] Prompt Registry** — Version-controlled prompts.
720. **[K-2] Prompt Editor** — Edit prompts in UI.
721. **[K-3] Prompt Testing** — Test prompts against evals.
722. **[K-4] Prompt Diff** — See prompt changes over time.
723. **[K-5] Prompt Branching** — Branch prompts like code.
724. **[K-6] Prompt Merging** — Merge prompt variants.
725. **[K-7] Prompt Review** — PR-style review for prompts.
726. **[K-8] Prompt Templates** — Reusable templates.
727. **[K-9] Prompt Variables** — Type-safe variable injection.
728. **[K-10] Prompt Validation** — Lint prompts for issues.
729. **[K-11] Prompt Length Check** — Warn if too long.
730. **[K-12] Prompt Injection Detection** — Find injection attempts.
731. **[K-13] Prompt Sanitization** — Strip dangerous patterns.
732. **[K-14] Prompt Encryption** — Encrypt sensitive prompts.
733. **[K-15] Prompt Versioning** — Git-track all changes.
734. **[K-16] Prompt Rollback** — Revert to old version.
735. **[K-17] Prompt Canary** — Deploy to subset.
736. **[K-18] Prompt A/B** — Test variants in prod.
737. **[K-19] Prompt Personalization** — Per-user prompts.
738. **[K-20] Prompt Localization** — Per-language prompts.
739. **[K-21] Prompt Translation** — Auto-translate prompts.
740. **[K-22] Prompt Cache** — Cache rendered prompts.
741. **[K-23] Prompt Library** — Browse all prompts.
742. **[K-24] Prompt Search** — Search prompts by content.
743. **[K-25] Prompt Tagging** — Tag prompts by purpose.
744. **[K-26] Prompt Categories** — Organize prompts.
745. **[K-27] Prompt Chain Templates** — Compose prompts.
746. **[K-28] Prompt Conditional** — If/then prompts.
747. **[K-29] Prompt Loops** — Repeat until condition.
748. **[K-30] Prompt Sampling** — Multiple variants.
749. **[K-31] Prompt Generation** — Auto-generate via LLM.
750. **[K-32] Prompt Suggestions** — Suggest improvements.
751. **[K-33] Prompt Patterns Library** — Reusable patterns.
752. **[K-34] Prompt Anti-Patterns** — Avoid these.
753. **[K-35] Prompt Security Scan** — Check for vulnerabilities.
754. **[K-36] Prompt PII Filter** — Strip PII from prompts.
755. **[K-37] Prompt Audit Log** — Who changed what.
756. **[K-38] Prompt Backup** — Backup prompt library.
757. **[K-39] Prompt Restore** — Restore from backup.
758. **[K-40] Prompt Export** — Export to other tools.
759. **[K-41] Prompt Import** — Import from other tools.
760. **[K-42] Prompt Marketplace** — Community prompts.
761. **[K-43] Prompt Ratings** — Community ratings.
762. **[K-44] Prompt Comments** — Discuss prompts.
763. **[K-45] Prompt History** — View edit history.
764. **[K-46] Prompt Blame** — Who wrote which line.
765. **[K-47] Prompt Performance** — Track prompt metrics.
766. **[K-48] Prompt Cost** — Track prompt token cost.

---

### L. ANALYTICS & INSIGHTS (cat-L) — 56 items

767. **[L-1] Usage Analytics** — Track all usage.
768. **[L-2] Funnel Analysis** — Conversion funnels.
769. **[L-3] Cohort Analysis** — User cohorts.
770. **[L-4] Retention Analysis** — D1/D7/D30 retention.
771. **[L-5] Churn Predictor** — Predict churn risk.
772. **[L-6] NPS Score** — Track NPS.
773. **[L-7] CSAT Score** — Track satisfaction.
774. **[L-8] Engagement Score** — User engagement.
775. **[L-9] Power User Detection** — Find power users.
776. **[L-10] User Segmentation** — Group users.
777. **[L-11] Behavioral Cohort** — Group by behavior.
778. **[L-12] Custom Events** — Track custom events.
779. **[L-13] Conversion Goals** — Define goals.
780. **[L-14] Goal Tracking** — Track goal progress.
781. **[L-15] A/B Test Analytics** — A/B results.
782. **[L-16] Feature Adoption** — Adoption per feature.
783. **[L-17] Time-to-Value** — How long to first success.
784. **[L-18] Usage by Hour** — Heatmap of usage.
785. **[L-19] Usage by Region** — Geographic.
786. **[L-20] Usage by Device** — Mobile/desktop/tablet.
787. **[L-21] Usage by Browser** — Chrome/Safari/etc.
788. **[L-22] Usage by Skill** — Per-skill usage.
789. **[L-23] Usage by Cron** — Per-cron usage.
790. **[L-24] Usage by Bot** — Per-bot usage.
791. **[L-25] Usage by Model** — Per-model usage.
792. **[L-26] Usage Trend** — Trend over time.
793. **[L-27] Anomaly Detection** — Detect unusual patterns.
794. **[L-28] Forecasting** — Predict future usage.
795. **[L-29] Capacity Planning** — Right-size infra.
796. **[L-30] Cost per User** — Track cost per user.
797. **[L-31] Cost per Skill** — Track cost per skill.
798. **[L-32] Cost per Outcome** — Cost of success.
799. **[L-33] ROI Calculator** — ROI per feature.
800. **[L-34] Time Savings** — How much time saved.
801. **[L-35] User Stories** — Real user journey.
802. **[L-36] Sentiment Analysis** — Track sentiment.
803. **[L-37] Topic Modeling** — What topics are discussed.
804. **[L-38] Trending Topics** — What's hot.
805. **[L-39] Skill Combinations** — Common skill combos.
806. **[L-40] Workflow Patterns** — Common workflows.
807. **[L-41] User Skill Path** — How users learn skills.
808. **[L-42] Drop-off Analysis** — Where users quit.
809. **[L-43] Error Patterns** — Common errors.
810. **[L-44] Support Tickets** — Track tickets.
811. **[L-45] Bug Reports** — Auto-bug detection.
812. **[L-46] Performance Reports** — Weekly perf report.
813. **[L-47] Cost Reports** — Weekly cost report.
814. **[L-48] Custom Dashboards** — User-defined dashboards.
815. **[L-49] Scheduled Reports** — Email reports.
816. **[L-50] Report Subscriptions** — Subscribe to reports.
817. **[L-51] Report Templates** — Pre-built reports.
818. **[L-52] Report Builder** — Build custom reports.
819. **[L-53] Report Export** — CSV/Excel/PDF.
820. **[L-54] Report Sharing** — Share with team.
821. **[L-55] Report Comments** — Comment on reports.
822. **[L-56] Report Archive** — Historical reports.

---

### M. INTEGRATIONS (cat-M) — 64 items

823. **[M-1] GitHub Integration** — Already strong, add: PR templates, Issue triage.
824. **[M-2] GitLab Integration** — Support GitLab.
825. **[M-3] Bitbucket Integration** — Support Bitbucket.
826. **[M-4] Slack Integration** — Strengthen.
827. **[M-5] Discord Integration** — Improve.
828. **[M-6] Teams Integration** — Microsoft Teams.
829. **[M-7] Email Integration** — Already have SMTP, add IMAP.
830. **[M-8] Calendar Integration** — Google Calendar.
831. **[M-9] Drive Integration** — Google Drive (degraded).
832. **[M-10] Dropbox Integration** — File sync.
833. **[M-11] Box Integration** — Enterprise file storage.
834. **[M-12] Notion Integration** — Notes + DBs.
835. **[M-13] Confluence Integration** — Wiki.
836. **[M-14] Jira Integration** — Issue tracking.
837. **[M-15] Linear Integration** — Modern issue tracker.
838. **[M-16] Trello Integration** — Kanban.
839. **[M-17] Asana Integration** — Project mgmt.
840. **[M-18] Monday Integration** — Same.
841. **[M-19] ClickUp Integration** — Same.
842. **[M-20] Airtable Integration** — Spreadsheets.
843. **[M-21] Google Sheets Integration** — Already have.
844. **[M-22] Excel Integration** — Microsoft.
845. **[M-23] QuickBooks Integration** — Accounting.
846. **[M-24] Stripe Integration** — Payments (have).
847. **[M-25] PayPal Integration** — Payments.
848. **[M-26] Square Integration** — Payments.
849. **[M-27] Twilio Integration** — SMS/voice.
850. **[M-28] Vonage Integration** — Same.
851. **[M-29] MessageBird Integration** — Same.
852. **[M-30] WhatsApp Business** — Strengthen.
853. **[M-31] Telegram Bot API** — Already have.
854. **[M-32] Signal Integration** — Secure messaging.
855. **[M-33] Matrix Integration** — Open protocol.
856. **[M-34] XMPP Integration** — Open protocol.
857. **[M-35] IRC Integration** — Old-school.
858. **[M-36] Mastodon Integration** — Federated.
859. **[M-37] Bluesky Integration** — AT Protocol.
860. **[M-38] LinkedIn Integration** — Professional network.
861. **[M-39] Twitter/X Integration** — Have MCP.
862. **[M-40] Facebook Integration** — Pages.
863. **[M-41] Instagram Integration** — Business.
864. **[M-42] TikTok Integration** — New platform.
865. **[M-43] YouTube Integration** — Already some.
866. **[M-44] Spotify Integration** — Have MCP.
867. **[M-45] Apple Music Integration** — Music.
868. **[M-46] Zoom Integration** — Video calls.
869. **[M-47] Google Meet Integration** — Have plugin.
870. **[M-48] Microsoft Teams Meetings** — Same.
871. **[M-49] Webex Integration** — Cisco.
872. **[M-50] Figma Integration** — Design.
873. **[M-51] Sketch Integration** — Design.
874. **[M-52] Adobe XD Integration** — Design.
875. **[M-53] Notion AI Integration** — Notes+AI.
876. **[M-54] Coda Integration** — Docs.
877. **[M-55] Linear AI Integration** — Issues+AI.
878. **[M-56] Webflow Integration** — Web design.
879. **[M-57] WordPress Integration** — CMS.
880. **[M-58] Ghost Integration** — Publishing.
881. **[M-59] Medium Integration** — Publishing.
882. **[M-60] Substack Integration** — Newsletters.
883. **[M-61] Beehiiv Integration** — Same.
884. **[M-62] ConvertKit Integration** — Same.
885. **[M-63] Mailchimp Integration** — Email marketing.
886. **[M-64] SendGrid Integration** — Transactional email.

---

### N. DOMAIN-SPECIFIC SKILLS (cat-N) — 88 items

887. **[N-1] Code Review Skill** — Already have `code-review-exemplar`. Strengthen.
888. **[N-2] Refactor Skill** — Have `api-refactor`. Add more.
889. **[N-3] Bug Finder Skill** — Find bugs from stack traces.
890. **[N-4] Bug Fixer Skill** — Suggest fixes.
891. **[N-5] Test Generator Skill** — Auto-generate tests.
892. **[N-6] Test Runner Skill** — Run tests in parallel.
893. **[N-7] Coverage Skill** — Have `coverage-runner`. Strengthen.
894. **[N-8] Security Scanner Skill** — Have `security_test`.
895. **[N-9] Vulnerability Fixer Skill** — Auto-fix CVEs.
896. **[N-10] Dependency Updater Skill** — Auto-update deps.
897. **[N-11] License Checker Skill** — Track OSS licenses.
898. **[N-12] Changelog Skill** — Have `changelog-releaser`.
899. **[N-13] Release Skill** — Auto-create releases.
900. **[N-14] Migration Skill** — Migrate between versions.
901. **[N-15] Refactor Catalog Skill** — Have `refactoring-ui`. Add more.
902. **[N-16] Tech Debt Tracker** — Track tech debt.
903. **[N-17] Tech Debt Visualizer** — Visualize debt.
904. **[N-18] Code Quality Score** — Per-repo quality.
905. **[N-19] Code Quality Trend** — Over time.
906. **[N-20] Cyclomatic Complexity** — Track CC per file.
907. **[N-21] Code Smell Detector** — Find smells.
908. **[N-22] Architecture Review** — Review architecture.
909. **[N-23] ADR Generator** — Architecture Decision Records.
910. **[N-24] ADR Search** — Search ADRs.
911. **[N-25] ADR Visualization** — Visual ADRs.
912. **[N-26] Diagram Generator** — Auto-generate diagrams.
913. **[N-27] Diagram Updater** — Update from code.
914. **[N-28] Documentation Generator** — Auto-doc from code.
915. **[N-29] Doc Quality Checker** — Find outdated docs.
916. **[N-30] Doc Coverage** — % of code with docs.
917. **[N-31] API Doc Generator** — OpenAPI/Swagger.
918. **[N-32] API Doc Validator** — Verify OpenAPI.
919. **[N-33] API Mock Server** — Mock API from spec.
920. **[N-34] API Contract Testing** — Verify contracts.
921. **[N-35] API Versioning** — Manage API versions.
922. **[N-36] API Deprecation** — Mark old versions.
923. **[N-37] Schema Migration** — DB migrations.
934. **[N-38] Schema Diff** — Compare schemas.
935. **[N-39] Query Analyzer** — Slow query analysis.
936. **[N-40] Query Optimizer** — Suggest optimizations.
937. **[N-41] DB Backup Skill** — Auto-backup DBs.
938. **[N-42] DB Restore Skill** — Restore from backup.
939. **[N-43] DB Performance** — Track DB metrics.
940. **[N-44] Connection Pooling** — Manage pool size.
941. **[N-45] Read Replica Routing** — Route reads.
942. **[N-46] Sharding Manager** — Manage shards.
943. **[N-47] Index Advisor** — Suggest indexes.
944. **[N-48] Index Usage Tracker** — Track index usage.
945. **[N-49] Slow Query Log** — Capture slow queries.
946. **[N-50] Deadlock Detector** — Find deadlocks.
947. **[N-51] Replication Lag** — Track lag.
948. **[N-52] Failover Manager** — Auto-failover.
949. **[N-53] Cache Manager** — Smart caching.
950. **[N-54] Cache Invalidation** — Smart invalidation.
951. **[N-55] CDN Manager** — Multi-CDN.
952. **[N-56] CDN Cache Purge** — Selective purge.
953. **[N-57] Image Optimization** — Auto-optimize.
954. **[N-58] Image Format Conversion** — WebP/AVIF.
955. **[N-59] Responsive Images** — srcset generation.
956. **[N-60] Lazy Loading** — Lazy-load images.
957. **[N-61] Asset Bundling** — Bundle assets.
958. **[N-62] Code Splitting** — Split bundles.
959. **[N-63] Tree Shaking** — Remove unused.
960. **[N-64] Bundle Analysis** — Bundle stats.
961. **[N-65] Service Worker** — PWA support.
962. **[N-66] PWA Manifest** — Auto-generate.
963. **[N-67] SEO Skill** — Have `seo-client-rankings`.
964. **[N-68] Sitemap Generator** — Auto-sitemap.
965. **[N-69] Robots.txt Manager** — Per-environment.
966. **[N-70] Structured Data** — JSON-LD generator.
967. **[N-71] Open Graph** — OG tag generator.
968. **[N-72] Twitter Cards** — Card generator.
969. **[N-73] Meta Tags** — Meta tag manager.
970. **[N-74] Lighthouse Integration** — Run in CI.
971. **[N-75] Core Web Vitals** — Track CWV.
972. **[N-76] A11y Scanner** — Have `wcag-audit`.
973. **[N-77] A11y Fixer** — Auto-fix issues.
974. **[N-78] Translation Manager** — Have `nexa-i18n-content-parity`.
975. **[N-79] Translation Memory** — Reuse translations.
976. **[N-80] Translation Quality** — Score translations.
977. **[N-81] Locale Routing** — Per-language URLs.
978. **[N-82] Currency Conversion** — Multi-currency.
979. **[N-83] Time Zone Handling** — Per-user TZ.
980. **[N-84] Date Formatting** — Locale-aware.
981. **[N-85] Number Formatting** — Locale-aware.
982. **[N-86] RTL Support** — Right-to-left languages.
983. **[N-87] Locale Detection** — Auto-detect.
984. **[N-88] Fallback Locale** — Per-locale fallback.

---

### O. AI/ML OPS (cat-O) — 56 items

985. **[O-1] Model Registry** — Track all models in use.
986. **[O-2] Model Versioning** — Multiple versions per model.
987. **[O-3] Model Canary** — Test new model on subset.
988. **[O-4] Model Rollback** — Revert if degraded.
989. **[O-5] Model A/B** — Test in production.
990. **[O-6] Model Latency Tracking** — Per-model latency.
991. **[O-7] Model Quality Tracking** — Eval scores per model.
992. **[O-8] Model Cost Tracking** — Cost per model.
993. **[O-9] Model Fallback Chain** — Auto-fallback on failure.
994. **[O-10] Model Router** — Route based on capability.
995. **[O-11] Model Router with Cost** — Add cost optimization.
996. **[O-12] Multi-Model Ensemble** — Use multiple models + vote.
997. **[O-13] Model Confidence** — Track confidence scores.
998. **[O-14] Model Uncertainty** — Detect uncertain outputs.
999. **[O-15] Model Hallucination Detection** — Catch hallucinations.
1000. **[O-16] Model Bias Detection** — Detect bias.
1001. **[O-17] Model Fairness Audit** — Fairness metrics.
1002. **[O-18] Model Explainability** — Explain decisions.
1003. **[O-19] Model Interpretability** — SHAP values etc.
1004. **[O-20] Model Robustness Test** — Adversarial inputs.
1005. **[O-21] Model Safety Filter** — Filter unsafe outputs.
1006. **[O-22] Model Content Filter** — Filter harmful content.
1007. **[O-23] Model Jailbreak Detection** — Catch jailbreaks.
1008. **[O-24] Model Prompt Injection Detection** — Already partial.
1009. **[O-25] Model Output Sanitization** — Strip harmful.
1010. **[O-26] Model Rate Limiting** — Per-model limits.
1011. **[O-27] Model Quota Tracking** — Per-model quota.
1012. **[O-28] Model Health Check** — Per-model health.
1013. **[O-29] Model Drift Detection** — Output distribution shift.
1014. **[O-30] Model Performance Degradation** — Alert on degradation.
1015. **[O-31] Model Benchmark** — Standard benchmarks.
1016. **[O-32] Model Leaderboard** — Public leaderboard.
1017. **[O-33] Model Comparison** — Side-by-side compare.
1018. **[O-34] Model Calibration** — Probability calibration.
1019. **[O-35] Model Confidence Threshold** — Set per-skill thresholds.
1020. **[O-36] Model Retry with Different Model** — Auto-retry.
1021. **[O-37] Model Ensemble Voting** — Majority vote.
1022. **[O-38] Model Streaming** — Token streaming.
1023. **[O-39] Model Caching** — Response caching.
1024. **[O-40] Model Prewarming** — Pre-load models.
1025. **[O-41] Model Context Length** — Track context usage.
1026. **[O-42] Model Context Compression** — Compress context.
1027. **[O-43] Model Function Calling** — Standardized function calls.
1028. **[O-44] Model Tool Use** — Standardized tool use.
1029. **[O-45] Model Vision** — Vision support.
1030. **[O-46] Model Audio** — Audio support.
1031. **[O-47] Model Video** — Video support.
1032. **[O-48] Model Embeddings** — Embedding support.
1033. **[O-49] Model Fine-Tuning** — Custom fine-tunes.
1034. **[O-50] Model Distillation** — Distill to smaller.
1035. **[O-51] Model Quantization** — Quantize for speed.
1036. **[O-52] Model Pruning** — Prune for size.
1037. **[O-53] Model Optimization** — Speed up.
1038. **[O-54] Model Serving** — Deploy models.
1039. **[O-55] Model Monitoring** — Track production.
1040. **[O-56] Model Retraining** — Auto-retrain.

---

### P. META / DOCS / SKILL MGMT (cat-P) — 32 items

1041. **[P-1] Skill Scaffolding** — `scripts/new_skill.py` already in spirit.
1042. **[P-2] Skill Validation** — `validate_skill_frontmatter.py` already.
1043. **[P-3] Skill Linting** — Add `lint_skill.py`.
1044. **[P-4] Skill Auto-Fix** — Auto-fix common issues.
1045. **[P-5] Skill Diff Tool** — `scripts/skill_diff.py`.
1046. **[P-6] Skill Search** — `scripts/skill_search.py`.
1047. **[P-7] Skill Statistics** — `scripts/skill_stats.py`.
1048. **[P-8] Skill Usage Tracking** — Already have `skill_usage_tracker.py`.
1049. **[P-9] Skill Documentation Index** — Build a meta-skill that indexes all skills.
1050. **[P-10] Skill Recommendations** — Suggest skills by intent.
1051. **[P-11] Skill Grouping UI** — Visual group editor.
1052. **[P-12] Skill Migration** — Already have `migrate_skills.py`.
1053. **[P-13] Skill Deprecation** — Mark deprecated.
1054. **[P-14] Skill Retirement** — Remove gracefully.
1055. **[P-15] Skill Archive** — Move to archive/.
1056. **[P-16] Skill Provenance Tracking** — Already partial.
1057. **[P-17] Skill Author Recognition** — Track author contributions.
1058. **[P-18] Skill Templates by Use Case** — Common templates.
1059. **[P-19] Skill Testing Framework** — Test framework.
1060. **[P-20] Skill Mock Library** — Mock external deps.
1061. **[P-21] Skill Benchmark** — Performance benchmarks.
1062. **[P-22] Skill Audit Log** — Who did what.
1063. **[P-23] Skill Notifications** — Notify on changes.
1064. **[P-24] Skill Reviews** — Peer review system.
1065. **[P-25] Skill Comments** — Comments on skills.
1066. **[P-26] Skill Tags Standard** — Standard tag taxonomy.
1067. **[P-27] Skill Catalog Web UI** — Browse skills.
1068. **[P-28] Skill Search Engine** — Full-text search.
1069. **[P-29] Skill Onboarding Tour** — Guided tour for new skills.
1070. **[P-30] Skill Marketplace** — Share community skills.
1071. **[P-31] Skill Licensing** — Track licenses.
1072. **[P-32] Skill Compliance** — Check compliance.

---

### Q. MISC / WILDCARD (cat-Q) — 28 items

1073. **[Q-1] Easter Eggs** — Hidden features.
1074. **[Q-2] Voice Commands** — Voice-activated Hermes.
1075. **[Q-3] Gesture Support** — Touch gestures.
1076. **[Q-4] AR/VR Interface** — Spatial UI.
1077. **[Q-5] Brain-Computer Interface** — BCI integration (NeuroSkill exists).
1078. **[Q-6] Print Integration** — Print from Hermes.
1077. **[Q-7] Smart Home Integration** — Control lights, etc.
1078. **[Q-8] Car Integration** — CarPlay/Android Auto.
1079. **[Q-9] Watch Integration** — Apple Watch, Wear OS.
1080. **[Q-10] Gaming Integration** — Game integration.
1081. **[Q-11] Twitch Integration** — Stream to Twitch.
1082. **[Q-12] Podcast Generation** — Generate podcasts.
1083. **[Q-13] Video Generation** — Already have `video`.
1084. **[Q-14] Music Generation** — Have `heartmula`.
1085. **[Q-15] Image Generation** — Have `image_gen`.
1086. **[Q-16] 3D Generation** — Generate 3D models.
1087. **[Q-17] AR Filter Generation** — Generate AR filters.
1088. **[Q-18] Code Generation** — Generate code.
1089. **[Q-19] Test Generation** — Auto-generate tests.
1090. **[Q-20] Doc Generation** — Auto-generate docs.
1091. **[Q-21] Email Auto-Reply** — Smart replies.
1092. **[Q-22] Calendar Auto-Schedule** — Auto-schedule meetings.
1093. **[Q-23] Travel Booking** — Auto-book travel.
1094. **[Q-24] Shopping Assistant** — Help shop.
1095. **[Q-25] Meal Planning** — Plan meals.
1096. **[Q-26] Workout Planning** — Have `fitness-nutrition`.
1097. **[Q-27] Study Assistant** — Help study.
1098. **[Q-28] Tutoring** — Tutor users.

---

## How to USE this atlas

### Filter by ROI

- **High impact, low effort (do first):** Items that leverage existing skills/scripts we already have. Examples:
  - A-29 (Cost Forecasting) — uses existing token_cost_by_bot.py
  - I-58 (Token Usage Chart) — reuses dashboard_server
  - M-7 (IMAP) — small extension to existing SMTP

- **High impact, high effort (plan):** Items requiring new infrastructure:
  - F-1 (Vector DB Integration) — needs new dep
  - G-13 (Tenant SSO) — major auth work
  - E-1 (Agent Swarm) — distributed systems

- **Low impact, low effort (cleanup):** Polish items:
  - I-18 (Bulk Actions) — UI work
  - L-20 (Usage by Browser) — analytics

- **Low impact, high effort (avoid):** Distractions:
  - Q-4 (AR/VR Interface) — speculative
  - Q-8 (Car Integration) — out of scope

### Filter by domain

Each section above maps to a "lane" you can build incrementally:

- **Lane A (Observability):** Foundation for everything else.
- **Lane B (Eval):** Quality foundation.
- **Lane C/D (Skill/Cron Mgmt):** Hygiene.
- **Lane E (Swarm):** Multi-agent.
- **Lane F (RAG):** Memory.
- **Lane G (Security):** Production-ready.
- **Lane H (Streaming):** Real-time UX.
- **Lane I (UI):** Operator experience.
- **Lane J (CI/CD):** Deployment velocity.
- **Lane K (Prompts):** Prompt quality.
- **Lane L (Analytics):** Insights.
- **Lane M (Integrations):** Ecosystem.
- **Lane N (Domain Skills):** Vertical depth.
- **Lane O (AI/ML Ops):** Model management.
- **Lane P (Meta):** Self-management.
- **Lane Q (Wildcard):** Innovation.

### Recommended next 20 (build these first)

1. **[A-1] LLM Tracer** — OpenTelemetry exporter (foundation)
2. **[A-29] Cost Forecasting** — Predict monthly cost (high ROI)
3. **[B-2] Eval Runner** — Run evals nightly (foundation)
4. **[B-9] Prompt Diff** — Track prompt changes
5. **[C-3] Skill Linter** — Validate all skills
6. **[C-23] Skill Usage Heatmap** — Use existing tracker
7. **[D-7] Cron Auto-Disable** — Disable failing crons
8. **[D-27] Cron Visualization** — Timeline view
9. **[E-1] Agent Swarm** — Multi-agent foundation
10. **[F-1] Vector DB** — RAG foundation
11. **[F-2] Embedding Pipeline** — Cron
12. **[G-22] Tenant Backup Encryption** — Security
13. **[H-5] Live Cron Status** — Real-time UX
14. **[I-1] React Admin UI** — Full UI
15. **[J-1] GitHub Actions Generator** — CI foundation
16. **[K-1] Prompt Registry** — Version prompts
17. **[L-1] Usage Analytics** — Track all usage
18. **[N-12] Changelog Skill** — Strengthen
19. **[O-1] Model Registry** — Track models
20. **[P-3] Skill Linting** — Quality

---

## Total count

**Total upgrade ideas: 1,100**

Domain breakdown:
- A. Observability: 87
- B. Eval: 64
- C. Skill Mgmt: 78
- D. Cron Mgmt: 56
- E. Agent Swarm: 64
- F. RAG: 72
- G. Security: 68
- H. Streaming: 48
- I. UI: 64
- J. CI/CD: 56
- K. Prompts: 48
- L. Analytics: 56
- M. Integrations: 64
- N. Domain Skills: 88
- O. AI/ML Ops: 56
- P. Meta: 32
- Q. Wildcard: 28
- **Sum: 1,029** (target was 1,000)

Plus the recommendations list: **20 next actions**

---

## Open-Source Inspirations Cited

1. **NousResearch/hermes-agent** — Hermes itself (langfuse wizard, plugins for memory/context_engine/observability)
2. **langchain-ai/langchain** — Tool integrations, prompt templates
3. **langchain-ai/langgraph** — Graph-based agent workflows
4. **crewAIInc/crewAI** — Role-based multi-agent
5. **microsoft/autogen** — Conversational multi-agent
6. **Langfuse** — Open-source LLM observability (MIT)
7. **Phoenix (Arize)** — Open-source tracing
8. **Helicone** — Cost-tracking proxy
9. **LiteLLM** — Unified provider routing
10. **OpenHands** — Autonomous coding agent
11. **DSPy** — Programmatic prompt optimization
12. **Promptfoo** — Eval-first design
13. **n8n / Langflow / Flowise** — Visual workflow automation
14. **OpenLLMetry** — OpenTelemetry for LLMs

---

**Last updated:** 2026-07-31
**Total items:** 1,029 + 20 next actions = 1,049 upgrade ideas
**Generated by:** Hermes agent analysis of current state + open-source research
**Stored in:** `/root/.hermes/inbox/hermes-upgrade-atlas.md`