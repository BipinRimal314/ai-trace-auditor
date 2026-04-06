# Product Hunt Launch Copy

**Name:** AI Trace Auditor

**Tagline:** EU AI Act compliance from your terminal

**Description:**

Open-source CLI and GitHub Action that audits AI codebases against EU AI Act Articles 11, 12, 13, 50 and GDPR Article 30.

One command scans your code for AI frameworks, traces for record-keeping gaps, and generates: Annex IV documentation, data flow diagrams, GDPR Records of Processing Activities, and a compliance evidence pack (PDF + checklists) for auditors.

Runs 100% locally. No API keys. No data leaves your machine. Apache 2.0.

**Key Features:**
- Annex IV technical documentation from code scanning alone
- Record-keeping gap analysis against OTel/Langfuse traces
- Multi-agent system auditing (LangGraph, CrewAI, AutoGen)
- Evidence pack export: PDF, Mermaid diagrams, per-requirement checklists
- GitHub Action: compliance check on every PR
- Project config via .aitrace.toml

**Topics:** Developer Tools, Compliance, Open Source, AI, Security

**Links:**
- GitHub: https://github.com/BipinRimal314/ai-trace-auditor
- PyPI: https://pypi.org/project/ai-trace-auditor/
- Landing page: https://bipinrimal314.github.io/ai-trace-auditor/

**Maker Comment:**

I built this because EU AI Act compliance tooling is either enterprise GRC platforms that cost $50K+/year or documentation checklists that go stale the moment your code changes.

AI Trace Auditor reads your actual code and actual traces. It knows which providers you're calling, which data is flowing where, and which Article 12 fields you're logging vs. missing.

Tested on real codebases: Dify merged the compliance guide it generated. LiteLLM, n8n, Haystack, and CrewAI PRs are in review.

The EU AI Act deadline is in flux (August 2026 or December 2027), but compliance infrastructure takes 12-18 months regardless. If you're shipping AI, this gives you a baseline in 60 seconds.

**Screenshots needed:**
1. Terminal: `aitrace comply ./` output showing the compliance table
2. Evidence pack folder structure in Finder/file explorer
3. GitHub Action YAML + PR check passing
4. Data flow Mermaid diagram rendered
5. Gap report showing satisfied/partial/missing requirements
