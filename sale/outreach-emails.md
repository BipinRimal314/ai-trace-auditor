# Outreach Email Templates

## How to Use

1. Pick the template matching the buyer category
2. Replace [BRACKETED] placeholders with company-specific details
3. Send from bipinrimal314@gmail.com
4. Subject lines are designed to get opened, not to sell — the email body does that
5. Follow up once after 5 days if no reply. Don't follow up more than twice.

---

## Template 1: Observability Companies (Langfuse/ClickHouse, Arize, Datadog)

**Subject:** Your customers' traces + EU AI Act = compliance evidence (open-source tool)

**Body:**

Hi [NAME],

EU AI Act enforcement starts August 2, 2026. Every company deploying high-risk AI in the EU needs compliance evidence from their system traces.

I built AI Trace Auditor, an open-source CLI that turns LLM traces (OTel, Langfuse, raw JSONL) into EU AI Act compliance reports. It covers Articles 11, 12, 13, and 25, including multi-agent DAG auditing. 301 tests, Apache 2.0, published on PyPI with 14 versions.

[COMPANY] already collects the traces. This tool interprets them against regulations. It's a new product feature for [COMPANY], not a new product.

I'm looking to sell the project outright: full source code, PyPI package, GitHub repo, regulatory YAML definitions, and 30 days of integration support. No ongoing obligation on my end.

Worth a 15-minute call to see if this fits [COMPANY]'s roadmap?

Demo: pip install ai-trace-auditor && aitrace audit --help
GitHub: github.com/BipinRimal314/ai-trace-auditor
Product brief attached.

Bipin Rimal

---

## Template 2: GRC / Compliance Platforms (Vanta, Drata, Sprinto, Secureframe)

**Subject:** EU AI Act compliance — the next regulation your customers will ask about

**Body:**

Hi [NAME],

Quick question: when [COMPANY]'s customers ask about EU AI Act compliance (August 2026 deadline), what's the answer today?

SOC2, ISO 27001, HIPAA — [COMPANY] handles those. But the EU AI Act requires AI-specific evidence that generic GRC tools can't produce: trace-level audit reports, Annex IV technical documentation generated from code, data flow mapping with GDPR role classification, and multi-agent accountability checks.

I built an open-source tool that does exactly this. AI Trace Auditor (v0.14.0, 301 tests, Apache 2.0) audits AI system traces against EU AI Act Articles 11, 12, 13, and 25, plus NIST AI RMF and GDPR Article 30. It generates compliance evidence packs that auditors can review.

I'm selling the project outright: source code, PyPI package, GitHub repo, extensible regulatory YAML format, and integration support. The YAML format means adding new regulations (like ISO 42001 or the upcoming NIST AI 600-1) is adding YAML files, not writing code.

For [COMPANY], this could mean EU AI Act coverage alongside your existing frameworks. For your customers, it means one platform for all their compliance needs.

15-minute call to discuss?

GitHub: github.com/BipinRimal314/ai-trace-auditor
Product brief attached.

Bipin Rimal

---

## Template 3: AI Governance Startups (Credo AI, Holistic AI, ModelOp)

**Subject:** Open-source EU AI Act compliance tool — acquisition opportunity

**Body:**

Hi [NAME],

I built AI Trace Auditor, the only open-source tool that audits AI systems against EU AI Act from code and traces. 14 published versions on PyPI, 301 tests, Apache 2.0. It covers Articles 11, 12, 13, and 25, including multi-agent DAG auditing with per-agent penalty propagation.

[COMPANY] does AI governance at [THEIR LEVEL — "the policy level" for Credo, "the consulting level" for Holistic, "the lifecycle level" for ModelOp]. This tool works at the code level: ingest traces, map them to regulatory requirements, output compliance evidence. Together, that's complete coverage from boardroom to codebase.

What [COMPANY] gets:
- GitHub repo with full commit history and 301 tests
- PyPI package (ai-trace-auditor) with 14 versions
- Extensible regulatory YAML requirement definitions
- Multi-agent compliance auditing (no competitor has this)
- Existing OSS traction (compliance guide merged by Dify, PRs in 4 other major frameworks)
- 30 days of integration support

I'm looking for a buyer who can take this to market faster than I can alone. The August 2026 deadline creates urgency that benefits both of us.

Interested in a quick call?

GitHub: github.com/BipinRimal314/ai-trace-auditor

Bipin Rimal

---

## Personalization Notes

### ClickHouse/Langfuse (Marc Klingen)
- Mention: "Langfuse traces are already a supported ingestion format in the tool"
- Mention: "2,000+ Langfuse customers = 2,000 potential compliance feature users"

### Vanta (Christina Cacioppo)
- Mention: your 2026 AI security positioning
- Mention: "Your platform already tracks SOC2 controls continuously. This does the same for EU AI Act."

### Sprinto (Girish Redekar)
- Mention: "Your Autonomous Trust Platform launched last month. This is another autonomous check to add."
- Mention: "3,000 customers across 75 countries ��� many in EU jurisdiction"

### Arize (Jason Lopatecki / Aparna Dhinakaran)
- Send to Aparna (CPO) — she decides product direction
- Mention: "Different buyer (compliance officer) but same data. New revenue stream from existing infrastructure."

### Drata (Adam Markowitz)
- Mention competitive angle: "Vanta is already positioning around AI compliance for 2026"

### Credo AI (Navrina Singh)
- Mention her TIME AI Leaders recognition
- Mention: "Your governance platform + this code-level tool = complete EU AI Act coverage"

### Holistic AI (Adriano/Emre)
- Mention their UCL background and the research angle
- Mention: "White-label this for consulting engagements. Scale beyond one-to-one."

### ModelOp (Dave Trier)
- Mention their 2026 AI Governance Benchmark Report
- Mention: "Your benchmark report shows agentic AI surging. This tool audits multi-agent systems."
