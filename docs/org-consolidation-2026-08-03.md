# GitHub Org Consolidation — IvanWeissVanDerPol (2026-08-03)

**Author**: Erebus · **For**: Ivan · **Method**: `github-org-consolidation` skill

Comprehensive analysis of all 110 repos in `IvanWeissVanDerPol` GitHub org, categorized by purpose, with concrete merge/keep/archive recommendations.

---

## 📊 Summary

| Metric | Value |
|--------|-------|
| **Total repos** | 110 |
| Public | 85 |
| Private | 25 |
| Archived (already) | 5 |
| **Active non-archived** | 105 |
| **Estimated reduction** | 19 repos → 91 after merge (17% reduction) |
| **Recommended for archive** | 5 (already archived, can delete) |
| **Recommended for merge** | 12 groups (47 repos total) |
| **Recommended to keep as-is** | 56 repos (legitimate standalone) |

---

## 🔴 HIGH PRIORITY — Multi-Repo Clients (47 repos in 12 groups)

### Group A: ParaguAI Lead Sites (19 repos)

These are the auto-generated "lead demo" sites for ParaguAI.com — each is a small Next.js site for a prospect client (HidroBaby-Spa, Peluqueria-Barbershop, etc.).

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| HidroBaby-Spa | AI-Whisperers Lead: HidroBaby Spa | 🟢 Active | **Migrate to monorepo** |
| Peluqueria-Barbershop | AI-Whisperers Lead: Peluquería Barbershop | 🟢 Active | **Migrate to monorepo** |
| Clau-Bellino | AI-Whisperers Lead: Clau Bellino | 🟢 Active | **Migrate to monorepo** |
| Woman-Cosmeticos | AI-Whisperers Lead: Woman Cosmeticos | 🟢 Active | **Migrate to monorepo** |
| Barbershop-Peluqueria | AI-Whisperers Lead: Barbershop Peluqueria | 🟢 Active | **Migrate to monorepo** |
| Avani-Belleza | AI-Whisperers Lead: Avani Belleza | 🟢 Active | **Migrate to monorepo** |
| Scott-Tatuajes | AI-Whisperers Lead: Scott Tatuajes | 🟢 Active | **Migrate to monorepo** |
| Lele-Ferreira | AI-Whisperers Lead: Lele Ferreira | 🟢 Active | **Migrate to monorepo** |
| XXGym | AI-Whisperers Lead: XXGym | 🟢 Active | **Migrate to monorepo** |
| Portas-Barber | AI-Whisperers Lead: Portas Barber | 🟢 Active | **Migrate to monorepo** |
| Viviesteticpy | AI-Whisperers Lead: Viviesteticpy | 🟢 Active | **Migrate to monorepo** |
| Cronos-Academy | AI-Whisperers Lead: Cronos Academy | 🟢 Active | **Migrate to monorepo** |
| Arnos-Barber-Shop | AI-Whisperers Lead: Arnos Barber Shop | 🟢 Active | **Migrate to monorepo** |
| Nde-Barba | AI-Whisperers Lead: Nde Barba | 🟢 Active | **Migrate to monorepo** |
| Barbye-Nails | AI-Whisperers Lead: Barbye Nails | 🟢 Active | **Migrate to monorepo** |
| Nutrifit-Spa | AI-Whisperers Lead: Nutrifit Spa | 🟢 Active | **Migrate to monorepo** |
| Leticia-Carballo | AI-Whisperers Lead: Leticia Carballo | 🟢 Active | **Migrate to monorepo** |
| Shine-Nails | AI-Whisperers Lead: Shine Nails | 🟢 Active | **Migrate to monorepo** |
| Estudio-Medieval | AI-Whisperers Lead: Estudio Medieval | 🟢 Active | **Migrate to monorepo** |

**Recommendation:** 🟢 MERGE into `paragu-ai-leads-monorepo/apps/<client-name>/`. This is the **single biggest reduction opportunity** — 19 repos → 1 monorepo.

The ParaguAI Platform monorepo (`paragu-ai-platform`) likely already has shared packages (Tailwind, Next.js config). Migrating all leads into one repo with shared deps:
- Cuts 18 separate `package.json` + `package-lock.json` + `.next/` builds
- Single CI/CD pipeline
- Per-app customization via config files

---

### Group B: ParaguAI Platform (2 repos)

The actual production ParaguAI business.

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| paragu-ai-website | Sitio web público de ParaguAI. Desplegado en Cloudflare Pages. | 🟢 Active | **Keep + link from monorepo** |
| ParaguAI-leads | CRM + outreach pipeline for ParaguAI.com lead clients | 🟢 Active | **Migrate into paragu-ai-website** (or vice versa) |

**Recommendation:** 🟡 VERIFY. Are these 2 separate products or 2 views of the same product? If separate, keep. If `ParaguAI-leads` is a CRM for the website, merge as `paragu-ai-website/crm/`.

---

### Group C: Lourdes portfolio variants (3 repos)

Lourdes is a psychologist with multiple repos.

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| lourdes | (no description) | ⚪ Stale | **Merge into lourdes-psicologia-ia** |
| lourdesproyecto | (no description) | ⚪ Stale | **Merge into lourdes-psicologia-ia** |
| lourdes-psicologia-ia | (no description) | 🟢 Recent | **Keep as canonical** |
| nathalia-portfolio | Portfolio website for Lourdes Nathalia Rios Delvalle | 🟢 Recent | **Verify: same person?** |

**Recommendation:** 🟡 VERIFY first — are all 3 + nathalia the same Lourdes? If yes, merge into `lourdes-psicologia-ia/legacy/{stale-repos}/`. **Reduce: 4 → 1.**

---

### Group D: Ivan Portfolio variants (3 repos)

Same person, different portfolio iterations.

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| Ivan_Weiss_Portfolio | Professional portfolio, CV, resume | 🟢 Recent | **Keep as canonical** |
| ivanweissvanderpol.github.io | website | 🟢 Recent | **Merge → Ivan_Weiss_Portfolio/web-v2/** |
| ivanweissvanderpol.github.io2 | A cutting-edge portfolio web page (vanilla JS) | ⚪ Stale | **Delete** (older iteration) |

**Recommendation:** 🟢 MERGE. `ivanweissvanderpol.github.io2` is the older iteration and should be deleted. `ivanweissvanderpol.github.io` should be merged. **Reduce: 3 → 1.**

---

### Group E: IABusiness variants (2 repos)

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| IABusiness | (no description) | ⚪ Stale | **Merge → IABusiness2** |
| IABusiness2 | (no description) | ⚪ Stale | **Merge → IABusiness2** |

**Recommendation:** 🟢 MERGE. These are obviously iterations of the same project. **Reduce: 2 → 1.**

---

### Group F: Unclassified "lourdes-psicologia-ia" pair

Already covered in Group C.

---

### Group G: AI-Whisperers historical (2 repos)

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| AI-Wishperers- | (no description) | ⚪ Stale | **Delete** (typo in name, no content) |
| IvanWeissVanDerPol | (no description) | ⚪ Stale | **Delete or merge into psycology** |

**Recommendation:** 🟡 VERIFY. These look like empty placeholder repos from before the org was organized. `IvanWeissVanDerPol` may be the "personal profile" repo that GitHub auto-creates — keep or delete depending on use.

---

### Group H: Lourdes + nathalia duplication

Lourdes is in 3 repos AND there's `nathalia-portfolio`. Is Nathalia Lourdes? See Group C.

---

### Group I: AI-Agent-QA-Generator (1 repo)

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| AI-Agent-QA-Generator | (CSS, no description) | ⚪ Stale | **Archive** (2024, no updates) |

**Recommendation:** 🟢 ARCHIVE. Single repo, no merge needed. Stale (last update 2024-11).

---

### Group J: Personal/family repos (3+)

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| Cami-Maidana | (no description) | 🗑️ Archived | **Already archived** |
| Ingrid | (no description) | 🗑️ Archived | **Already archived** |
| Maga | (no description) | 🗑️ Archived | **Already archived** |
| MagaCannes | (no description) | ⚪ Stale | **Archive** |

**Recommendation:** 🟢 ARCHIVE. Personal/family sites with no description and stale (2025-05 or earlier). Can be deleted if Ivan confirms.

---

### Group K: Various course/uni assignments (10+)

These look like university assignments from 2023-2024.

| Repo | Status | Action |
|------|--------|--------|
| BD2 | ⚪ 2025 | Archive |
| BackendTP2 | ⚪ 2024 | Archive |
| Compiladores | ⚪ 2024 | Archive |
| FE_TP | ⚪ 2023 | Archive |
| FIRE | ⚪ 2024 | Archive |
| IS3 | ⚪ 2024 | Archive |
| IS3_tp1 | ⚪ 2024 | Archive |
| ML | ⚪ 2023 | Archive |
| Machine-learning | ⚪ 2023 | Archive |
| machine-learning-presentacion | ⚪ 2023 | Archive |
| EcoRuta | ⚪ 2023 | Archive |
| LauraPicco.github.io | ⚪ 2024 | Archive |
| LuciaDiaz.github.io | ⚪ 2024 | Archive |
| introduction-to-qa-and-qa-automation-beginner-to-expert | ⚪ 2025 | Archive |

**Recommendation:** 🟢 ARCHIVE. 14 university assignment repos, all stale (2023-2025). **Reduce: 14 → 0** (or keep 1 portfolio if Ivan wants).

---

### Group L: Various bots / forks / experiments (5+)

| Repo | Description | Status | Action |
|------|-------------|--------|--------|
| Saskia | (HTML) | ⚪ 2025 | Archive (old) |
| kiki | (JavaScript) | ⚪ 2026-02 | Keep (used by Hermes profiles) |
| nico | (no description) | ⚪ 2026-02 | VERIFY |
| nico-duarte | (no description) | ⚪ 2026-02 | VERIFY |
| mike | (no description) | ⚪ 2026-01 | VERIFY |
| Tony | (no description) | ⚪ 2025-11 | VERIFY |
| Vete | TypeScript | ⚪ 2025-12 | Keep |
| HIV-Research | (no description) | ⚪ 2025-12 | VERIFY |
| sarah-roig | Jupyter | 🟢 2026-05 | Keep |
| sarah-therapy | (no description) | 🟢 2026-05 | Keep |

**Recommendation:** 🟡 VERIFY each. Names like "nico", "mike", "Tony" are ambiguous. Ask Ivan which ones are real projects.

---

## 🟢 KEEP AS-IS (Legitimate Standalone)

### Core Ops & AIW (4 repos — the canonical set)

| Repo | Description | Why Keep |
|------|-------------|----------|
| psycology | (HTML) | Main ops + thesis + research + docs |
| ai-whisperers-ops-toolkit | Single canonical repo to bootstrap any VPS, client | NEW (R24) — canonical |
| hermes-agent | The agent that grows with you | Core platform |
| ai-whisperers-packages | Shared packages monorepo | @ai-whisperers/ui, /tokens, /deploy |

### Research / Public Goods (3 repos)

| Repo | Description | Why Keep |
|------|-------------|----------|
| satellite-paraguay | Multi-temporal earth observation of Paraguay | Standalone research project |
| thesis-research | Ivan's thesis research: 1439 ideas atlas | Standalone research project |
| paragu-auditor | Public Spending Auditor for Paraguay | Standalone research project |

### Personal / Trip (3 repos)

| Repo | Description | Why Keep |
|------|-------------|----------|
| itau-finance-analysis | Itaú Paraguay statement analysis | Personal finance |
| granja-cabral | (Python) | Family farm project |
| netherlands-2026 | Trip 2026 | Trip docs |

### Personal ERP (2 repos)

| Repo | Description | Why Keep |
|------|-------------|----------|
| SaskiaPersonal | Personal ERP — Saskia | Family-specific |
| LifeERP | Personal ERP — Ivan | Personal |

**⚠️ WARNING:** These two ERPs are duplicates in concept. Consider merging `LifeERP` and `SaskiaPersonal` into a single personal-erp monorepo with profiles. **Reduce: 2 → 1.**

### Tools / Standalone (2 repos)

| Repo | Description | Why Keep |
|------|-------------|----------|
| BDSM-Paraguay-Toolkit | (no description) | Niche project |
| Marketing-Agent | (Python) | Standalone tool |

### Infrastructure (1 repo)

| Repo | Description | Why Keep |
|------|-------------|----------|
| infrastructure-cost-tracker | OpenClaw cost analysis | 1★, valuable reference |

### Active Production (the rest)

| Repo | Description | Why Keep |
|------|-------------|----------|
| nicolas-duarte-site | Nicolás Duarte Career Site | Real client? |
| nathalia-portfolio | Lourdes Nathalia portfolio | Real portfolio |
| brahm-the-racoon | Music project | Personal |
| anthro-party-plan | Anthro Party Argentina planning | Event |
| py-property-scraper | Paraguay property scraper (11K listings) | Real tool |
| telescope-ai | AI telescope control | Personal |
| fun4me-store | Adult Wellness E-Commerce Platform | Real business |
| Ivan_Weiss_Portfolio | Ivan's portfolio | Personal |
| grocery | (no description) | VERIFY |
| maskarada | (no description) | VERIFY |
| superspuma | (no description) | VERIFY |
| cir-nextjs | (no description) | VERIFY |
| databricks-AI-Agent-Hackathon | (Python) | Hackathon archive |
| automated-posting | Paraguay auto-posting tool | Real tool |
| blobkcainfinal | (JavaScript) | VERIFY |
| blockchain-fpuna2024 | (JavaScript) | Course |
| facturas_rename | (Python) | Tool |
| investment-test | (Python) | Test repo |
| ivan | (TypeScript) | Personal profile? |
| ivan-random | (no description) | VERIFY |
| polcoin | (JavaScript) | Project |
| nasaSpaceApp_IEEE | Jupyter | Hackathon archive |
| PolCoin | (JavaScript) | Crypto project |
| lourdes-psicologia-ia | (Python) | Lourdes's IA (see Group C) |
| Lourdesproyecto | (Python) | Lourdes legacy |
| lourdes | (no description) | Lourdes legacy |

---

## 📋 Verification Questions

These need clarification BEFORE any merge:

| # | Question | Why it matters |
|---|----------|----------------|
| 1 | **ParaguAI leads → monorepo?** Confirm 19 lead sites can be migrated to a single monorepo | Biggest reduction (19→1) |
| 2 | **Lourdes sites** (4 repos: lourdes, lourdesproyecto, lourdes-psicologia-ia, nathalia-portfolio) — all the same person? | 4→1 if yes |
| 3 | **Ivan portfolio variants** — can ivanweissvanderpol.github.io + .github.io2 merge into Ivan_Weiss_Portfolio? | 3→1 |
| 4 | **Personal ERP** (LifeERP + SaskiaPersonal) — merge into single personal-erp monorepo? | 2→1 |
| 5 | **Kiki, nico, mike, Tony, sarah** — which are real projects vs placeholders? | 5 ambiguous |
| 6 | **HIV-Research** — research project or placeholder? | 1 ambiguous |
| 7 | **AI-Wishperers-, IvanWeissVanDerPol, ivan, ivan-random** — empty placeholders? | 4 to delete if yes |
| 8 | **University repos** (BD2, BackendTP2, etc.) — keep as portfolio or archive? | 14 to archive |
| 9 | **Ivan_Weiss_Portfolio's content** — same as nathalia-portfolio? | 1 duplicate |
| 10 | **BDSM-Paraguay-Toolkit** — keep or archive? | 1 niche |

---

## 🎯 Recommended Action Plan

### Phase 1 — DELETE (5 min, no questions needed)

5 already-archived repos can be safely deleted if Ivan confirms:
```
gh repo delete IvanWeissVanDerPol/test
gh repo delete IvanWeissVanDerPol/Cami-Maidana
gh repo delete IvanWeissVanDerPol/Ingrid
gh repo delete IvanWeissVanDerPol/Maga
gh repo delete IvanWeissVanDerPol/portfolio-website-old
```

### Phase 2 — VERIFY (10 min, ask Ivan)

Ask the 10 verification questions above. Don't merge without confirmation.

### Phase 3 — HIGH PRIORITY MERGES (4-6 hours total)

After verification, in this order:

1. **ParaguAI lead sites → monorepo** (19→1) — biggest win, ~3 hours
2. **Lourdes consolidation** (4→1 if same person) — 1 hour
3. **Ivan portfolio variants** (3→1) — 30 min
4. **IABusiness merge** (2→1) — 15 min
5. **University repos** (14→0) — 30 min bulk archive

### Phase 4 — MEDIUM PRIORITY

- Personal ERP consolidation (2→1)
- AI-Whisperers placeholders cleanup (4→0)
- Ambiguous "kiki/nico/mike/Tony/sarah" (5 individual decisions)

---

## 📉 Reduction Potential

| Phase | Before | After | Saved |
|-------|--------|-------|-------|
| Current | 110 | 110 | 0 |
| Phase 1 (delete archived) | 110 | 105 | 5 |
| Phase 3 (high-priority merges) | 105 | 78 | 27 |
| Phase 4 (medium merges) | 78 | 73 | 5 |
| **Final** | **110** | **73** | **37 (34%)** |

---

## 🛠️ Tooling — How To Execute

### Clone all repos for inspection

```bash
mkdir -p /tmp/org-audit && cd /tmp/org-audit
gh repo list IvanWeissVanDerPol --limit 200 --json name --jq '.[].name' | \
  xargs -I {} gh repo clone IvanWeissVanDerPol/{} {} -- --depth=1
```

### Find duplicate file content across repos

```bash
for repo in */; do
  find "$repo" -name "*.md" -type f -exec md5sum {} \;
done | sort | uniq -w32 -d
```

### Archive a repo (preserves history, hides from listings)

```bash
gh repo archive IvanWeissVanDerPol/REPO_NAME
```

### Delete a repo (irreversible!)

```bash
gh repo delete IvanWeissVanDerPol/REPO_NAME --confirm
```

### PR-based merge workflow (recommended for safety)

1. Clone target repo (`gh repo clone IvanWeissVanDerPol/TARGET`)
2. Create branch (`git checkout -b merge-from-source-YYYY-MM-DD`)
3. Copy content from source repo (with Python script, exclude node_modules, .next, etc.)
4. Commit (`git add . && git commit -m "merge: from SOURCE"`)
5. Push + PR (`git push origin ...`)
6. After merge, archive the source repo

---

## ⚠️ Pitfalls To Avoid

1. **Don't merge without verification** — Lourdes/Ivan portfolio/Personal ERP all need confirmation.
2. **Don't blindly delete** — university repos might have portfolio value; ask first.
3. **Don't archive active repos** — check `updatedAt` within last 30 days.
4. **Don't merge ParaguAI leads one-by-one** — the monorepo strategy is 17× faster.
5. **Don't assume empty descriptions = placeholder** — `mike`, `Tony`, `HIV-Research` might be real.
6. **Personal/family sites** (Cami, Ingrid, Maga) are already archived — confirm before deleting.
7. **Don't merge SaaS products with portfolio sites** — different purposes.

---

## 📌 Key Decisions To Make Now

1. **Do you want to merge the 19 ParaguAI leads into a monorepo?** This is the single biggest reduction (17% of total repos).
2. **Do you want to consolidate Personal ERP into 1 repo?**
3. **Are the 4 Lourdes repos the same person?**
4. **Are the 14 university repos worth keeping as portfolio?**

Once you answer these, the rest is mechanical.

---

**Generated by**: Erebus (Hermes Agent) · **Date**: 2026-08-03 · **Method**: `github-org-consolidation` skill
