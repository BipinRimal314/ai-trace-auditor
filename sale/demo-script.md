# AI Trace Auditor — 2-Minute Demo

Run this yourself after `pip install ai-trace-auditor`. No API keys, no setup, no LLM calls.

## Setup (10 seconds)

```bash
pip install ai-trace-auditor
git clone https://github.com/BipinRimal314/ai-trace-auditor.git
cd ai-trace-auditor
```

## Demo 1: Audit traces against EU AI Act (30 seconds)

```bash
# Audit an OpenTelemetry trace against EU AI Act Article 12
aitrace audit tests/fixtures/otel_chat_trace.json -r "EU AI Act"

# You'll see:
# - Overall compliance score (e.g., 79.3%)
# - Per-requirement pass/fail breakdown
# - Top gaps with actionable recommendations
# - Exit code 0 (pass) or 1 (gaps found) — CI-friendly
```

## Demo 2: Multi-agent compliance (30 seconds)

```bash
# Audit a multi-agent trace — shows DAG reconstruction + per-agent scores
aitrace audit tests/fixtures/otel_multi_agent_trace.json --show-dag

# You'll see:
# - Per-agent compliance scores with penalty propagation
# - Article 25 "value chain accountability" checks
# - Mermaid DAG visualization
# - Upstream agents penalized for downstream failures
```

## Demo 3: Full compliance package from code (30 seconds)

```bash
# Scan a codebase and generate compliance evidence for Articles 11 + 13 + GDPR
aitrace comply tests/fixtures/sample_codebase/ -o /tmp/compliance-report.md

# You'll see:
# - Article 11: Annex IV technical documentation (auto-populated sections)
# - Article 13: Data flow diagram with GDPR role classification
# - GDPR Article 30: Records of Processing Activities
# - Risk classification scope check (Section 0)
# - Warnings about what requires manual review
```

## Demo 4: Browse regulatory requirements (20 seconds)

```bash
# See all requirements the tool checks
aitrace requirements list

# Drill into a specific one
aitrace requirements show EU-AIA-12.1
```

## Key Points to Highlight for Buyers

1. **Zero LLM dependency** — pure Python, runs offline, no API keys
2. **301 passing tests** — production-quality, not a prototype
3. **CI exit codes** — 0/1 pass/fail, drops into any pipeline
4. **Extensible via YAML** — adding a new regulation = adding a YAML file
5. **Multi-agent auditing** — nobody else does this
6. **Evidence packs** — zip-ready folders for auditors
