# AI Trace Auditor

Compliance auditor for AI systems. Audits LLM traces against EU AI Act, NIST AI RMF, ISO 42001, and SOC 2. Every requirement verified against primary legal text with exact clause citations. v0.15.0 on PyPI.

## Critical Rules

### Compliance Verification Gate
Every requirement YAML must satisfy ALL of these before shipping:
1. `legal_text` field citing the exact clause (e.g., "Article 12(2)(a)")
2. `verified_against_primary: true` only after page-by-page comparison with primary source
3. Evidence fields marked as "Implementation guidance" when not prescribed by the source
4. `check_type: "organizational"` for requirements that can't be verified by trace inspection
5. `framework_nature` set correctly: "law" (EU AI Act), "voluntary" (NIST), "certifiable_standard" (ISO), "audit_framework" (SOC 2)
6. `compliance_tier` set: "deterministic" (law prescribes exactly), "structural" (law requires capability), "quality" (best practice), or omitted for organizational

**Background:** v0.14.0 shipped with 60% fabricated EU AI Act requirements. An Open WebUI maintainer caught it. Full audit documented in `docs/requirement-audit-2026-04-06.md`.

### The Abstraction-Fabrication Curve
When generating requirements from regulatory text, LLMs project software engineering knowledge onto legal text. The more abstract the mapping, the higher the fabrication rate:
- Concrete (text patterns): 0% fabrication
- Moderate (structured rules): 10% fabrication
- High (legal → trace field): 60% fabrication

**Rule:** Write the `legal_text` field FIRST. Then ask: does my evidence field actually follow from these exact words? If not, it's implementation guidance, not a legal requirement.

### Tiered Scoring
Audit reports produce three separate scores, not one misleading overall number:
- **Legal Compliance** (Tier 1 — deterministic): Binary pass/fail on law-prescribed checks (Art 12(3) biometric fields, Art 19 retention, Art 50 disclosure)
- **Structural Evidence** (Tier 2): Coverage % for capability-level requirements (Art 12(1) general logging, NIST monitoring)
- **Quality** (Tier 3): Best practice observability scores (token counting, trace linkage, etc.)

Organizational requirements (Art 25, most of Annex IV, ISO 42001 governance) are excluded from scoring and shown as documentation checklists.

## Project Structure

```
requirements/
├── eu_ai_act/          # Verified against PDF (docs/eu-ai-act-full-text.pdf)
│   ├── article_12.yaml # Record-keeping (8 requirements: 4 structural, 4 deterministic)
│   ├── article_19.yaml # Log retention (2 requirements: 1 deterministic, 1 organizational)
│   ├── article_25.yaml # Value chain liability (5 requirements, all organizational)
│   ├── article_50.yaml # Transparency obligations (6 requirements, all deterministic)
│   └── annex_iv.yaml   # Technical documentation (20 requirements: 5 structural, 15 organizational)
├── nist_ai_rmf/        # Verified against NIST AI 100-1 PDF
│   ├── measure.yaml    # MEASURE subcategories (6 requirements, all structural/recommended)
│   └── manage.yaml     # MANAGE subcategories (2 requirements, all structural/recommended)
├── iso_42001/          # NOT verified (paid standard)
│   └── management_system.yaml  # 9 requirements: 3 structural, 6 organizational
├── soc2_ai/            # NOT verified (paid standard)
│   └── trust_services.yaml     # 6 requirements, all structural
└── best_practices/     # NOT regulatory — industry observability recommendations
    └── llm_observability.yaml  # 8 requirements, all quality tier
```

## Development

```bash
cd Projects/ai-trace-auditor
.venv/bin/python -m pytest tests/ -x -q   # 301 tests
.venv/bin/python -m build                  # Build wheel
source .env && .venv/bin/python -m twine upload dist/*  # Publish
```

## Product Roadmap

### Immediate (v0.16.0)
- **"What applies to me?" intake** — questionnaire that filters requirements: provider vs deployer, high-risk vs not, biometric vs not, financial institution vs not. Uses `applies_to` field.
- **Documentation checklist mode** — Annex IV + organizational requirements generate a checklist instead of trace gaps.
- **Fix 5 known bugs** from OSS PR testing (GDPR entity language, Art 13 vs 50 conflation, retention period hardcoding, missing scope check, percentage claims). Documented in ROADMAP.md.

### Near-term (v0.17.0)
- **Severity weighting** — mandatory 3x, recommended 1x, best practice 0.5x
- **Requirement profiles** — `--profile chatbot`, `--profile agent`, `--profile rag-pipeline`
- **Delta reports** — compare two audit reports, show regressions

### Medium-term
- **Redline integration** — Redline lints documents, Trace Auditor lints traces. Combined compliance view.
- **Hosted dashboard** — $99/month single repo, $499/month org.
- **Langfuse/Arize/Datadog integrations** — pull traces from where teams already store them
- **PDF report output** — compliance officers email PDFs to lawyers

### Parked
- Claude Code analytics features (insights, workflow, predict) — different buyer, no deadline urgency. May become separate `aitrace-insights` package.

## Known Issues
- Zero real users. Open WebUI maintainer was only real feedback source.
- ISO 42001 and SOC 2 YAMLs unverified against paid standards.
- "SOC 2 AI Addendum" was renamed — any references in marketing/docs need updating.
- PyPI token was exposed in conversation history on 2026-04-07 — rotate it.

## PyPI
```bash
# Token in .env (gitignored). Rotate after each conversation where it's exposed.
source .env
.venv/bin/python -m twine upload dist/ai_trace_auditor-*
```
