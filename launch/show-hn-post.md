# Show HN Post

**Title:** Show HN: Free EU AI Act compliance checker for AI codebases (CLI + GitHub Action)

**URL:** https://github.com/BipinRimal314/ai-trace-auditor

**Text:**

I built an open-source CLI that scans AI codebases against EU AI Act requirements. One command, five articles.

The EU AI Act's record-keeping and transparency obligations (Articles 11, 12, 13, 50) take effect August 2026. The European Parliament voted to extend to December 2027, but trilogue isn't done. Either way, compliance infrastructure takes 12-18 months to build, and most teams haven't started.

What it does:

- `aitrace comply ./` scans your codebase and generates: Annex IV technical documentation (Art. 11), record-keeping gap analysis against your OTel/Langfuse traces (Art. 12), data flow diagrams with GDPR transfer warnings (Art. 13), and a GDPR Article 30 Records of Processing Activities template.

- `aitrace comply ./ --evidence-pack output/` bundles everything into a folder (PDF, Mermaid diagrams, per-requirement checklist, metadata) that a compliance officer can hand to an auditor.

- Runs as a GitHub Action in CI. Fails the build if compliance gaps appear.

- Detects multi-agent systems (LangGraph, CrewAI, AutoGen) and audits delegation chains for Article 25 accountability.

It's static analysis + trace auditing, not an LLM wrapper. No data leaves your machine. Apache 2.0.

I tested it by submitting compliance guides to LiteLLM, n8n, Dify (merged), Haystack, and CrewAI. Dify shipped it; the others are in review.

Tech: Python, Pydantic v2, Typer, YAML requirement definitions. 288 tests. Trace formats: OTel, Langfuse, Claude Code sessions, raw JSONL.

The existing landscape is observability platforms (Langfuse, Arize) that collect traces but don't map them to regulations, and GRC platforms (Credo AI, OneTrust) that cost $$$$ and don't understand code. This sits in the gap: reads your code, reads your traces, tells you what's missing.

https://github.com/BipinRimal314/ai-trace-auditor
https://pypi.org/project/ai-trace-auditor/
Landing page: https://bipinrimal314.github.io/ai-trace-auditor/
