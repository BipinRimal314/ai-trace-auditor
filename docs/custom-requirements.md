# Custom Requirement Packs

AI Trace Auditor ships with EU AI Act and NIST AI RMF requirements. You can add your own.

## Quick Start

1. Create a YAML file following the schema below
2. Validate it: `aitrace validate-requirements ./my-requirements/`
3. Use it: add to `.aitrace.toml`

```toml
custom_requirements = ["./my-requirements/"]
```

## YAML Schema

```yaml
regulation: "Your Regulation Name"
article: "Section or Article"
title: "Human-readable title"
status: "beta"  # optional: "beta" shows a warning when loaded

requirements:
  - id: "UNIQUE-ID-1"
    title: "Short requirement title"
    description: >
      Detailed description of what this requirement means
      and how it applies to AI systems.
    severity: "mandatory"  # mandatory | recommended | best_practice
    applies_to: ["all"]    # all | high_risk | limited_risk | multi_agent_only
    evidence_fields:
      - field_path: "spans[].start_time"
        description: "What this field proves"
        required: true
        check_type: "non_null"  # non_null | non_empty | present | retention
```

## Available Field Paths

These are the normalized trace fields the auditor checks:

| Field Path | Description |
|---|---|
| `spans[].start_time` | Operation start timestamp |
| `spans[].end_time` | Operation end timestamp |
| `spans[].operation` | Operation type (chat, embeddings, etc.) |
| `spans[].provider` | AI provider name |
| `spans[].model_used` | Actual model that ran |
| `spans[].model_requested` | Model requested (may differ from actual) |
| `spans[].input_tokens` | Input token count |
| `spans[].output_tokens` | Output token count |
| `spans[].latency_ms` | Response latency in milliseconds |
| `spans[].error_type` | Error classification |
| `spans[].error_message` | Error details |
| `spans[].finish_reasons` | Completion status |
| `spans[].trace_id` | Unique trace identifier |
| `spans[].tool_calls` | Tool/function invocations |
| `spans[].agent_id` | Agent identifier (multi-agent) |
| `spans[].delegation_path` | Delegation chain (multi-agent) |

## Check Types

| Check | Passes When |
|---|---|
| `non_null` | Field exists and is not null |
| `non_empty` | Field exists and is not empty string/list |
| `present` | Field exists in at least some spans |
| `retention` | Field has retention period metadata |

## Shipped Packs

| Pack | Directory | Status | Requirements |
|---|---|---|---|
| EU AI Act | `requirements/eu_ai_act/` | Stable | Articles 12, 19, 25 |
| NIST AI RMF | `requirements/nist_ai_rmf/` | Stable | Govern, Measure, Manage |
| ISO 42001 | `requirements/iso_42001/` | Beta | Clauses 4-10 |
| SOC 2 AI | `requirements/soc2_ai/` | Beta | Trust Services Criteria |

## Validating

```bash
# Validate a single file
aitrace validate-requirements ./my-policy.yaml

# Validate a directory
aitrace validate-requirements ./internal-policies/
```

The validator checks: required fields (id, title, description), evidence field structure, and severity values.
