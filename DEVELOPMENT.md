---
title: Development Plan — AI Trace Auditor
branch: develop/product-hiring-edge
focus: Product + demo surface for AI governance hiring; ship usable defaults
status: implemented (v0.18.0) — Phase 0, 1a, checks pack, and diff shipped 2026-07-09; demo video + intake questionnaire remain
updated: 2026-07-09
related:
  - README.md
  - ROADMAP.md
  - PRODUCT.md
  - PRODUCT-BRIEF.md
  - HOW-IT-WORKS.md
---

# DEVELOPMENT.md — How We Develop This Further

**Project:** [ai-trace-auditor](https://github.com/BipinRimal314/ai-trace-auditor)  
**Branch:** `develop/product-hiring-edge`  
**Role in the portfolio:** Flagship **AI governance product** artifact (Lane 2 — GRC/observability companies, compliance engineering roles)

This plan is complementary to the research plan in `threat-to-governance-pipeline`. That repo answers *can we detect coordinated agent misuse?* This repo answers *can we turn regulations into machine-checkable evidence from code and traces?*

Existing `ROADMAP.md` already lists product phases. This document prioritizes for the **next 90 days of job search + portfolio edge**, not every possible enterprise feature.

---

## 1. North star

> Make Trace Auditor the project a hiring manager can **install in 60 seconds, run on a public repo or sample traces, and understand the compliance gap** — without reading a research paper.

### Current strengths (do not rewrite)

| Asset | Why it matters |
|---|---|
| Dify merge (186 lines into 100K+ star repo) | External validation |
| PyPI package + 301 tests | Real shipping bar |
| Deterministic checks, primary-text citations | Differentiator vs LLM-hallucinated compliance |
| Multi-agent DAG auditing (Art 25) | Rare OSS capability |
| CLI + MCP + GitHub Action | Multiple adoption surfaces |
| Codebase scan → Annex IV docs | “Trace → evidence” thesis |

### Current weaknesses (fix these)

| Gap | Impact |
|---|---|
| “Zero users” (per ROADMAP) | Need demo loop, not more silent features |
| Default dump of all requirements | Overwhelming; needs intake / profiles |
| Coverage ≠ compliance confusion | Already partially fixed (renames); keep sharpening |
| Marketing assets > product loop | Many `.txt` outreach drafts; less “one golden path” |
| Research sibling not linked | Missed story: detection gaps → documentation obligations |

### What “done” looks like for this cycle

1. **Golden path:** one command + one sample → readable report in under 2 minutes  
2. **Public demo artifact:** 2-minute video or GIF + sample report committed in-repo  
3. **Intake or profile mode:** user sees *applicable* requirements, not everything  
4. **Machine-readable check pack:** public JSON/YAML of checks with article citations (portfolio + product)  
5. **README that leads with hireable proof** (Dify, tests, install, sample output)

---

## 2. Positioning for development decisions

When choosing features, score them:

| Score high if… | Score low if… |
|---|---|
| Makes first-run experience better | Only helps enterprise multi-tenant edge cases |
| Produces a screenshot/demo for applications | Invisible internal refactor with no user-visible win |
| Strengthens “deterministic + cited” claim | Adds LLM dependency that can invent legal text |
| Aligns with EU AI Act urgency (Art 50: Dec 2026, high-risk: Dec 2027) | Generic “AI quality” dashboarding (Langfuse already owns this) |
| Supports multi-agent / value chain story | Rehashes financial-doc linter territory (`redline`/`comply`) |

**Hard rule:** no LLM that *decides* compliance. LLMs may only help *summarize* human-readable output if clearly labeled non-authoritative. Legal claims stay rule-based.

---

## 3. Architecture (where to work)

Current layout (high level):

```
src/ai_trace_auditor/
  cli.py              # Typer entry: audit, scan, docs, flow, audit-repo
  ingest/             # Trace format loaders (OTel, Langfuse, Claude Code, JSONL)
  scanner/            # Codebase AST / pattern scan for SDKs, models, vector DBs
  regulations/        # Requirement packs
  verification/       # Check evaluation
  reports/            # Markdown / JSON output
  docs/               # Annex IV generation
  flow/               # Data-flow / GDPR role mapping
  repo/               # audit-repo GitHub URL path
  profiles/           # (extend) requirement profiles
  intake/             # (extend) "what applies to me?"
  analysis/           # Multi-agent / insights
  mcp_server.py
  web/                # Dashboard if present
```

### Proposed additions this cycle

```
src/ai_trace_auditor/
  profiles/
    chatbot.yaml
    agent.yaml
    rag-pipeline.yaml
    high-risk-annex-iii.yaml
  export/
    checks_pack.py          # export machine-readable check registry
examples/
  golden_path/
    sample_traces.json
    expected_report.md
    README.md               # copy-paste tutorial
spec/
  checks-pack-v1.json       # public portable artifact
docs/
  DEMO.md                   # script for 2-min video
  HIRING-PACKET.md          # one-pager for applications
```

---

## 4. Phased plan

### Phase 0 — Golden path (3–5 days)  ← do first

Goal: a stranger (or hiring manager) succeeds without Slack access to you.

- [ ] `examples/golden_path/` with committed sample traces + sample codebase stub (or point at a tiny fixture under `tests/fixtures`)
- [ ] README “60-second demo” block at the top:

```bash
pip install ai-trace-auditor
aitrace audit examples/golden_path/sample_traces.json -o /tmp/report.md
# or
aitrace scan examples/golden_path/sample_project/ --traces examples/golden_path/sample_traces.json
```

- [ ] Fix any first-run friction (missing files, unclear errors, wrong default regulation flags)
- [ ] Commit a **checked-in sample report** so GitHub readers see output without running
- [ ] Trim README: move long competitive essays below the fold; lead with install → run → sample

**Exit criteria:** Fresh clone, `pip install -e .`, one command, readable report. Time yourself.

### Phase 1 — Applicability (1–2 weeks)

Goal: stop dumping every requirement on every user. Aligns with ROADMAP “What applies to me?” and requirement profiles.

**1a. Profiles (ship first — simpler than chat intake)**

```bash
aitrace audit traces.json --profile agent
aitrace audit traces.json --profile chatbot
aitrace audit traces.json --profile rag-pipeline
aitrace scan ./app --profile high-risk
```

Each profile = filtered requirement set + default severity emphasis.

**1b. Intake questionnaire (CLI flags or interactive)**

- Provider or deployer?
- High-risk Annex III? (if no → Art 50 + GDPR-focused path)
- Multi-agent?
- Processes personal data?

Output: chosen profile + short “why these requirements apply” preamble in the report.

**Exit criteria:** Default path uses a sensible profile; `--all-requirements` still available for power users.

### Phase 2 — Public checks pack + demo media (1 week, parallel)

Goal: portable artifact for portfolio and product trust.

- [ ] Export full check registry to `spec/checks-pack-v1.json` (or YAML):

```json
{
  "id": "EU-AIA-ART12-TEMPERATURE",
  "framework": "EU AI Act",
  "article": "12",
  "clause": "...",
  "check_type": "deterministic",
  "severity": "mandatory",
  "applies_to": ["provider", "high-risk"],
  "what_we_look_for": "temperature logged on generation spans"
}
```

- [ ] Document how many checks map to primary legal text (`verified_against_primary`)
- [ ] Record **2-minute demo** (script in `docs/DEMO.md`): install → audit sample → show gap table → show Annex IV partial fill
- [ ] Optional: GIF in README (no need for polished marketing site)

**Exit criteria:** Checks pack + demo script + sample report linked from README.

### Phase 3 — Trace-path depth (2–3 weeks)

Goal: own the “observability → compliance” gap more than “static code scan.”

Prioritize in order:

1. **Better Langfuse / OTel coverage** — field mapping completeness, clear “missing field” recommendations
2. **Delta reports** — `aitrace diff report-v1.json report-v2.json` (ROADMAP Phase 2) so teams see progress
3. **CI narrative** — GitHub Action example workflow that fails on “mandatory missing” only (not noise)
4. **Multi-agent demo fixture** — one committed multi-agent trace set showing Art 25 DAG output (unique differentiator)

Defer:

- Full SaaS multi-tenant billing
- Every GRC export format under the sun
- Replacing Credo AI enterprise workflows

**Exit criteria:** Diff command works; multi-agent fixture produces a screenshot-worthy DAG section.

### Phase 4 — Distribution & credibility (ongoing, light touch)

- [ ] One more **upstream PR** to a popular AI framework docs (pattern that worked for Dify) — only if it ships real compliance guidance, not spam
- [ ] Keep PyPI version bumps small and changelog-clear
- [ ] `docs/HIRING-PACKET.md`: half-page for applications (“what it is, Dify proof, install, sample numbers”)
- [ ] Link sibling research: “Behavioral monitoring has a multi-agent coordination ceiling; Trace Auditor documents record-keeping obligations that assume monitoring exists.”

---

## 5. Explicit non-goals (this cycle)

| Non-goal | Why |
|---|---|
| Rebuild as hosted compliance SaaS | Distracts from OSS hireable proof |
| Merge with `redline`/`comply` financial linters | Different buyer and domain |
| LLM-as-judge for legal satisfaction | Destroys the deterministic trust claim |
| Boiling the ocean of ISO 42001 every clause | Prefer depth on Art 11/12/13/25 + clear tiers |
| Feature parity with Credo AI | Different product class |

---

## 6. Relationship to threat-to-governance-pipeline

| | `ai-trace-auditor` | `threat-to-governance-pipeline` |
|---|---|---|
| Primary question | Do our *artifacts* satisfy regulatory evidence needs? | Can our *detectors* see coordinated misuse? |
| Primary audience | Product / compliance / platform engineers | Safety researchers / fellowships |
| Time allocation (recommended) | **30%** of build time | **70%** of build time |

**Shared story for applications:**

> I research where agent monitoring fails (coordination / HYDRA), and I ship open-source tooling that turns EU AI Act record-keeping and documentation duties into something engineers can run on real traces and codebases.

Optional future integration (not Phase 0–2):

- Import multi-agent coordination *risk flags* as a “governance gap” note in reports (“single-entity monitoring only; multi-account correlation not present”)
- Keep research models out of the default CLI so Trace Auditor stays zero-ML-dependency for core checks

---

## 7. Quality bar

- **Tests:** no merge without tests for new profiles/checks; keep suite green (301+ baseline)
- **Citations:** every new requirement needs primary-text pointer or explicit `best_practice` tier
- **Language:** never claim “X% compliant with the law” — use “trace field coverage,” “structural evidence,” “documentation completeness” (already partially fixed in v0.16)
- **Performance:** local runs on sample fixtures < 30s; `audit-repo` stays capped (existing 50MB / 30s discipline)

### Acceptance tests for the golden path

```
1. pip install -e ".[dev]" succeeds on clean venv
2. aitrace --help lists audit, scan, docs, flow, audit-repo
3. aitrace audit examples/golden_path/sample_traces.json exits 0 and writes report
4. Report contains at least one Satisfied and one Missing/Partial with article citation
5. pytest passes
```

---

## 8. First concrete PR sequence

1. **docs:** this `DEVELOPMENT.md` + README golden-path section (this branch)
2. **chore:** `examples/golden_path/` fixtures + checked-in sample report
3. **feat:** `--profile` filtering (agent / chatbot / rag / high-risk)
4. **feat:** export `spec/checks-pack-v1.json`
5. **feat:** `aitrace diff` for two JSON reports
6. **docs:** DEMO.md script + HIRING-PACKET.md
7. **feat:** multi-agent fixture under examples + DAG in sample report

---

## 9. Hiring / portfolio use (how to talk about this work)

**Lead with:**

1. Dify PR merged (external validation)  
2. `pip install ai-trace-auditor` + sample report  
3. Deterministic checks with clause citations (not LLM legal advice)  
4. Multi-agent Art 25 path  

**Second beat:**

- Self-honesty pattern from Redline audits (if relevant) + Trace Auditor coverage renames  
- EU AI Act timeline (Art 50 transparency: Dec 2, 2026; Annex III high-risk: Dec 2, 2027 per the Digital Omnibus) as urgency, not fearmongering  

**Avoid:**

- Claiming users you don’t have  
- Claiming full legal compliance  
- Leading with personal app craft (Drift, Cryptoku) in the same breath as this tool  

---

## 10. Timeboxed 30-day slice (if capacity is limited)

| Week | Deliverable |
|---|---|
| 1 | Golden path + sample report + README top rewrite |
| 2 | `--profile` for agent + high-risk |
| 3 | checks-pack JSON export |
| 4 | Demo video/GIF + multi-agent fixture **or** `aitrace diff` |

Stop after week 4 and use the artifacts in applications. Further ROADMAP items (severity weighting, intake chatbot, more frameworks) only after interviews demand them.

---

## Bottom line

**Develop the first-run product loop and the public, citable check pack** — not a sprawling enterprise GRC platform. Trace Auditor already has the hard parts (parsers, regulations, tests, Dify proof). The edge for hiring is making that work **immediately legible** to someone who will spend five minutes on your GitHub before the phone screen.
