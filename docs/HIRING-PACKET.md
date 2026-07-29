# AI Trace Auditor — One-Pager

**What it is:** Open-source CLI that turns AI system traces and codebases into
EU AI Act compliance evidence — deterministic checks with article citations,
no LLM in the decision loop. `pip install ai-trace-auditor`.

**Repo:** https://github.com/BipinRimal314/ai-trace-auditor · Apache 2.0 · PyPI (17 releases)

## Proof points

- **Merged upstream into Dify** (100K+ star LLM platform): the tool scanned
  Dify's 8,275-file codebase and generated the EU AI Act compliance guide its
  maintainers merged ([langgenius/dify#33838](https://github.com/langgenius/dify/pull/33838)).
  Compliance-guide PRs also submitted to LiteLLM, n8n, Haystack, and CrewAI.
- **424 passing tests**, including adversarial fixtures that reject fabricated
  legal quotes. 41 of 72 checks are validated **verbatim against the pinned
  official EU AI Act text in CI** — the tool structurally cannot invent law.
- **Multi-agent compliance auditing no other OSS tool does:** reconstructs
  agent DAGs from spans, propagates per-agent compliance scores bottom-up,
  and checks EU AI Act Article 25 value-chain accountability.
- **Full pipeline:** ingest (OTel GenAI / Langfuse / Claude Code / raw JSONL)
  → 72-check registry (EU AI Act, NIST AI RMF, ISO 42001, SOC 2, trace
  quality) → Markdown/JSON/PDF evidence packs → GitHub Action that fails CI
  on regressions (`aitrace diff`).

## Why it matters now

EU AI Act Article 50 transparency obligations apply **December 2, 2026**;
Annex III high-risk obligations follow **December 2, 2027** (Digital Omnibus).
Compliance evidence infrastructure takes 12–18 months to build. Observability
tools (Langfuse, Arize, LangSmith) collect traces; GRC platforms (Vanta,
OneTrust) manage policies; nothing in between translates runtime behavior
into auditor-ready evidence. That translation layer is this tool.

## What it demonstrates about me

- I ship production-quality Python (typed Pydantic v2 models, 424 tests,
  CI-gated primary-source verification, PyPI + GitHub Action + MCP server
  distribution).
- I do the domain work: the requirement registry encodes article-level
  readings of the EU AI Act, NIST AI RMF, ISO 42001, and SOC 2 — and marks
  each check's legal basis (`direct` / `structural` / `product_inference`)
  so engineering claims never outrun legal ones.
- I find distribution paths: the Dify merge came from running the tool on
  their codebase and contributing the output upstream.

## Try it (60 seconds)

```bash
pip install ai-trace-auditor
git clone https://github.com/BipinRimal314/ai-trace-auditor
aitrace audit ai-trace-auditor/examples/golden_path/sample_traces.json -o report.md --show-dag
```

Or just read the [committed sample report](../examples/golden_path/sample_report.md)
and the [public checks pack](../spec/checks-pack-v1.json).
