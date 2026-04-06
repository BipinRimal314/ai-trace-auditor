# AI Trace Auditor — Product Map

**Goal:** Sell the product outright for $30K-$50K.
**Deadline pressure:** EU AI Act enforcement August 2, 2026 (4 months). Product value peaks before that date.
**Buyer profile:** Observability companies (Langfuse, Arize, Helicone), GRC platforms (Vanta, Drata, Sprinto), AI governance startups (Credo AI, Holistic AI, ModelOp).

---

## What's Built

| Component | Status | Details |
|---|---|---|
| CLI (v0.14.0) | Done | `aitrace audit`, `docs`, `flow`, `comply`, `insights`, `health`, `predict` |
| EU AI Act coverage | Done | Articles 11, 12, 13, 25 + Annex IV |
| NIST AI RMF coverage | Done | GOVERN, MAP, MEASURE, MANAGE subcategories |
| GDPR coverage | Done | Article 30 RoPA, data flow mapping |
| Multi-agent DAG auditing | Done | LangGraph, CrewAI, AutoGen, ADK. Per-agent penalty propagation |
| Trace ingestion | Done | OTel, Langfuse, raw JSONL, auto-detect |
| Report generation | Done | Markdown, JSON. Jinja2 templates |
| Regulatory YAML format | Done | Extensible requirement definitions |
| Tests | Done | 301 passing |
| PyPI | Partial | v0.13.0 published. v0.14.0 local only |
| GitHub repo | Done | Public, BipinRimal314/ai-trace-auditor |
| GitHub Action | Done | action.yml exists, not on Marketplace |
| OSS outreach | Done | PRs to Dify (merged), Haystack, CrewAI, LiteLLM, n8n |
| License | Done | Apache 2.0 |

## What's Needed for Sale

### Tier 1: Must Have (blocks outreach)

- [x] **Fix 5 compliance bugs** found from PR testing
  - [x] GDPR entity language — already fixed in prior session
  - [x] Article 13 vs Article 50 conflation — templates separated (2026-04-06)
  - [x] Retention period — already fixed in code, PRODUCT.md updated (2026-04-06)
  - [x] No risk classification / scope check — already implemented (Section 0 + linter rule CG-003)
  - [x] Unverifiable percentage claims — already fixed, all % qualified as "auto-populated sections"
- [x] **Publish v0.14.0 to PyPI** — uploaded 2026-04-06, live at pypi.org/project/ai-trace-auditor/0.14.0/
- [x] **README rewrite** — buyer-facing, leads with deadline + business problem (2026-04-06)
- [x] **Product brief** — PRODUCT-BRIEF.md created (2026-04-06)
- [ ] **Acquire.com listing**

### Tier 2: Strengthens Pitch (parallel with outreach)

- [ ] **Buyer list** — 10-15 companies with specific contacts and personalized angles
- [ ] **Outreach emails** — templates per buyer type (observability, GRC, governance)
- [ ] **Demo script** — 2-minute terminal walkthrough a buyer can run after `pip install`
- [ ] **GitHub Action on Marketplace** — action.yml exists, needs release tag + listing

### Tier 3: Nice to Have

- [ ] **Landing page** (GitHub Pages) — one-page site with deadline urgency
- [ ] **GitHub stars** — any organic growth helps credibility
- [ ] **Demo video** — recorded walkthrough for async sharing

## Competitive Position

No open-source tool audits AI systems against EU AI Act from code + traces. Closest competitors:
- Credo AI ($41M raised) — enterprise, sales-driven, not code-level
- OneTrust / Vanta — GRC, not AI-specific
- Holistic AI — consulting-heavy, no CLI
- Langfuse / Arize — observability, no compliance interpretation

**The competition is consultants ($30K-$500K/engagement), not software.**

## Sale Assets

What the buyer gets:
1. GitHub repo (full history, 301 tests, CI)
2. PyPI package + brand
3. action.yml (GitHub Action)
4. Regulatory YAML requirement definitions (extensible format)
5. Existing OSS relationships (Dify merge, 4 other PRs)
6. ROADMAP.md with clear next phases
7. Apache 2.0 — buyer can close-source future development

## Asking Price

$30K-$50K. Justification:
- 4-6 months senior engineer time to replicate (~$50K-$75K at $150K/year)
- Domain expertise in EU AI Act compliance built into the requirement mappings
- August 2026 deadline creates urgency — time-to-market value
- Existing OSS market positioning
