# AI Trace Auditor

Audit LLM traces against regulatory compliance requirements. Open-source CLI that sits between your observability stack (Langfuse, Arize, OTel) and regulatory frameworks (EU AI Act, NIST AI RMF).

Your observability tools collect traces. Your GRC platform manages policies. **Nothing translates traces into compliance evidence.** This tool does.

## Install

```bash
pip install ai-trace-auditor
```

Or from source:

```bash
git clone https://github.com/BipinRimal314/ai-trace-auditor.git
cd ai-trace-auditor
pip install -e .
```

## Quick Start

```bash
# Audit traces against all regulations
aitrace audit traces.json

# Audit against a specific regulation
aitrace audit traces.json -r "EU AI Act" -o report.md

# Inspect what requirements exist
aitrace requirements --show EU-AIA-12.1

# Just ingest and summarize traces
aitrace ingest traces.json --summary
```

## What It Checks

**EU AI Act Article 12 (Record-Keeping):**
- Event timestamps, operation identification
- Risk situation logging (errors, failure modes)
- Model version tracking for post-market monitoring
- Resource consumption (tokens, latency)
- Content recording (opt-in)
- Tool/function call audit trails
- Trace linkage for multi-step operations

**NIST AI RMF:**
- Production monitoring (MEASURE 2.4)
- Transparency documentation (MEASURE 2.8)
- Model explainability (MEASURE 2.9)
- Risk tracking (MEASURE 3.1)
- Post-deployment monitoring (MANAGE 4.1)
- Incident communication (MANAGE 4.3)

## Supported Trace Formats

| Format | Source |
|--------|--------|
| OTel OTLP JSON | OpenTelemetry GenAI semantic conventions |
| Langfuse JSON | Langfuse trace exports |
| Raw JSONL | Any provider's API logs |

Auto-detected. Use `--format` to override.

## Example Output

```
Overall Compliance Score: 72.3%

| Status    | Count |
|-----------|-------|
| Satisfied |     6 |
| Partial   |     4 |
| Missing   |     3 |

Top gaps:
  1. Not logging: Error classification when operations fail
  2. Incomplete: Input prompts/messages (0% coverage)
  3. Not logging: Tools/functions available to the AI model
```

## CI Integration

Exit code 0 = all satisfied, 1 = gaps found:

```bash
aitrace audit traces.json -r "EU AI Act" || echo "Compliance gaps detected"
```

## Disclaimer

This tool provides automated compliance assessments based on its interpretation of regulatory requirements. It is **not legal advice**. Consult qualified legal counsel for compliance decisions.

## License

Apache 2.0
