# Show HN Post

**Title:** Show HN: Free EU AI Act compliance checker for AI codebases (CLI + GitHub Action)

**URL:** https://github.com/BipinRimal314/ai-trace-auditor

**Text:**

I built an open-source CLI that scans AI codebases against EU AI Act requirements. One command, five articles.

The EU AI Act's transparency obligations (Article 50) take effect December 2, 2026, and high-risk record-keeping obligations (Articles 11, 12, 13) follow on December 2, 2027 under the Digital Omnibus adopted mid-2026. Compliance infrastructure takes 12-18 months to build, and most teams haven't started.

What it does:

- `aitrace scan ./` scans your codebase and generates: Annex IV technical documentation (Art. 11), record-keeping gap analysis against your OTel/Langfuse traces (Art. 12), data flow diagrams with GDPR transfer warnings (Art. 13), and a GDPR Article 30 Records of Processing Activities template.

- `aitrace scan ./ --evidence-pack output/` bundles everything into a folder (PDF, Mermaid diagrams, per-requirement checklist, metadata) that a compliance officer can hand to an auditor.

- Runs as a GitHub Action in CI. Fails the build if compliance gaps appear.

- Detects multi-agent systems (LangGraph, CrewAI, AutoGen) and audits delegation chains for Article 25 accountability.

It's static analysis + trace auditing, not an LLM wrapper. No data leaves your machine. Apache 2.0.

I tested it by submitting compliance guides to LiteLLM, n8n, Dify (merged), Haystack, and CrewAI. Dify shipped it; the others are in review.

Tech: Python, Pydantic v2, Typer, YAML requirement definitions. 288 tests. Trace formats: OTel, Langfuse, Claude Code sessions, raw JSONL.

The existing landscape is observability platforms (Langfuse, Arize) that collect traces but don't map them to regulations, and GRC platforms (Credo AI, OneTrust) that cost $$$$ and don't understand code. This sits in the gap: reads your code, reads your traces, tells you what's missing.

https://github.com/BipinRimal314/ai-trace-auditor
https://pypi.org/project/ai-trace-auditor/
Landing page: https://bipinrimal314.github.io/ai-trace-auditor/
