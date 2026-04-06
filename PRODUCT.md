# AI Trace Auditor

Open-source CLI that audits LLM traces against regulatory compliance requirements. Sits in the gap between observability tools (Langfuse, Arize, OTel) and GRC platforms (OneTrust, Vanta): the former collect traces, the latter manage policies, but nothing translates traces into compliance evidence.

## The Problem

EU AI Act Article 12 requires automatic event recording and traceability for high-risk AI systems. August 2026 deadline. NIST AI RMF mandates provenance documentation. Companies have traces from their LLM observability stack but no automated way to answer: "Do our traces satisfy the regulatory requirements?"

67% of AI teams discover quality regressions from user complaints despite having tracing infrastructure. The gap isn't data collection; it's interpretation.

## What It Does

```
[OTel / Langfuse / Raw API traces]
    -> ai-trace-auditor
        -> Compliance gap analysis (what you log vs. what regulations require)
        -> Structured audit reports (Markdown / JSON)
        -> CI exit codes (pass/fail for pipeline gates)
        -> Actionable recommendations (what to add to your traces)
```

## Competitive Position

| Existing Tool | What It Does | What We Do Differently |
|---|---|---|
| Langfuse / Arize | Collect and visualize traces | Interpret traces against regulations |
| Credo AI ($41M) | Enterprise AI governance platform | Free, open-source, runs locally |
| @systima/comply | Static code analysis for AI framework usage | Analyze actual runtime trace data |
| OneTrust / Vanta | GRC policy management | Ingest AI-specific traces, not generic policy docs |

**Why providers won't build this:** Anthropic, OpenAI, and Google ship usage APIs. They have no incentive to build regulatory interpretation on top: it's outside their core product, requires legal/compliance expertise, and creates liability.

**Why observability tools won't build this:** Langfuse/Arize sell dashboards to engineers. Compliance evidence packs for regulators is a different buyer (legal, compliance), different product, different sales motion.

## Architecture

```
ai-trace-auditor/
├── src/ai_trace_auditor/
│   ├── cli.py              # Typer CLI: audit, ingest, requirements commands
│   ├── config.py            # .aitrace.toml config loading
│   ├── ingest/              # Trace ingestion (OTel, Langfuse, raw JSONL)
│   │   ├── base.py          # TraceIngestor protocol
│   │   ├── otel.py          # OpenTelemetry OTLP JSON parser
│   │   ├── langfuse.py      # Langfuse export parser
│   │   ├── raw_api.py       # Raw API log (JSONL) parser
│   │   └── detect.py        # Auto-format detection
│   ├── models/              # Pydantic v2 data models
│   │   ├── trace.py         # NormalizedTrace, NormalizedSpan
│   │   ├── requirement.py   # Requirement, EvidenceField
│   │   ├── evidence.py      # EvidenceRecord
│   │   └── gap.py           # GapReport, RequirementResult, GapDetail
│   ├── regulations/         # Regulatory requirement definitions
│   │   └── registry.py      # Load YAML, query requirements
│   ├── analysis/            # Gap analysis engine
│   │   ├── engine.py        # ComplianceAnalyzer orchestrator
│   │   ├── field_mapper.py  # Resolve field paths against traces
│   │   └── scorer.py        # Coverage scoring
│   └── reports/             # Report generation
│       ├── markdown.py      # Markdown compliance report
│       ├── json_report.py   # JSON structured output
│       └── templates/       # Jinja2 templates
├── requirements/            # YAML regulatory requirement definitions
│   ├── eu_ai_act/
│   │   ├── article_12.yaml  # Article 12: Record-Keeping
│   │   └── article_19.yaml  # Article 19: Log Retention
│   └── nist_ai_rmf/
│       ├── govern.yaml
│       ├── map.yaml
│       ├── measure.yaml
│       └── manage.yaml
└── tests/
    ├── fixtures/            # Sample trace files for testing
    ├── test_ingest/
    ├── test_analysis/
    └── test_reports/
```

## Tech Stack

| Dependency | Purpose |
|---|---|
| Python >=3.11 | Runtime |
| pydantic >=2.0 | Data models, validation, JSON serialization |
| typer >=0.12 | CLI framework |
| rich >=13.0 | Terminal output (tables, progress) |
| jinja2 >=3.1 | Report templates |
| pyyaml >=6.0 | Regulatory requirement definitions |

No dependency on any LLM framework. Intentionally framework-agnostic.

## Regulatory Coverage (v0.1)

### EU AI Act

**Article 12 — Record-Keeping** (~15 discrete requirements):
- Art 12(1): Automatic recording capability
- Art 12(2)(a): Risk situation identification events
- Art 12(2)(b): Post-market monitoring data
- Art 12(2)(c): Operational monitoring per Art 26(5)
- Art 12(3): Biometric-specific (period, database, match data, human verifier)
- Art 18/19: Retention (10yr providers / 6mo+ deployers — role-dependent)

**Evidence fields mapped to trace data:**
- `spans[].start_time` / `end_time` — event timestamps
- `spans[].model_used` — model version tracking
- `spans[].input_tokens` / `output_tokens` — resource consumption
- `spans[].error_type` / `error_message` — failure logging
- `spans[].finish_reasons` — completion status
- `spans[].tool_calls` — tool usage recording
- `spans[].input_messages` / `output_messages` — content logging (opt-in)

### NIST AI RMF (~15 subcategories):
- GOVERN 1.1, 1.4, 1.5, 4.2 — governance documentation
- MAP 1.1, 2.2, 2.3 — system purpose and limits
- MEASURE 1.1, 2.1, 2.4, 2.8, 2.9, 3.1 — testing and monitoring
- MANAGE 1.3, 4.1, 4.3 — risk response and incident tracking

## CLI Usage

```bash
# Main command: audit traces against regulations
aitrace audit traces.json
aitrace audit traces.json -r "EU AI Act" -o report.md
aitrace audit ./traces/ -r "NIST AI RMF" --report-format json

# Inspect trace files
aitrace ingest traces.json --summary

# Browse requirements
aitrace requirements list
aitrace requirements list -r "EU AI Act"
aitrace requirements show EU-AIA-12.1
```

Exit codes: 0 = all requirements satisfied, 1 = gaps found. CI-friendly.

## Implementation Phases

### Phase 1: Project Scaffolding + OTel Ingestion
- pyproject.toml, package structure, README, LICENSE
- NormalizedTrace/NormalizedSpan Pydantic models
- OTel OTLP JSON parser (primary format)
- Auto-format detection
- `aitrace ingest` command with summary table

### Phase 2: Regulatory Requirement Mappings
- EU AI Act Article 12 + 19 as structured YAML
- NIST AI RMF traceability subcategories as YAML
- RequirementRegistry loader
- `aitrace requirements` command

### Phase 3: Gap Analysis Engine
- Field path resolver (maps `spans[].model_used` to actual trace data)
- Coverage scoring (per-requirement and overall)
- ComplianceAnalyzer orchestrator
- GapReport data model

### Phase 4: Report Generation
- Jinja2 Markdown templates
- JSON structured output
- MarkdownReporter

### Phase 5: Full CLI + Additional Parsers
- `aitrace audit` command (ties everything together)
- Langfuse JSON export parser
- Raw JSONL parser
- .aitrace.toml config file support

## Design Decisions

1. **Pydantic v2, not dataclasses.** Compliance tool must validate its own data rigorously.
2. **YAML for requirements, not Python.** Compliance officers should be able to read and contribute to requirement definitions.
3. **Field path strings for evidence mapping.** Adding a requirement = adding YAML, not writing Python.
4. **Single normalized trace model.** Analysis engine doesn't know or care about the source format.
5. **Apache 2.0 license.** Enterprise adoption requires permissive licensing with patent grants.

## Known Risks

1. **OTel GenAI conventions are still "Development" status.** Attribute names may change. We pin to a spec version.
2. **Regulatory interpretation is not legal advice.** Prominent disclaimers everywhere.
3. **Content fields (prompts/completions) are opt-in.** Requirements that need content are scored "not_applicable" when content is absent.
4. **Langfuse export format is undocumented.** Parser must handle unknown fields gracefully.

## Roadmap (Post-MVP)

- v0.2: PDF reports, custom requirement YAML, trend analysis, ISO 42001
- v0.3: Arize/LangSmith formats, interactive TUI, OTel Collector integration
- v1.0: GitHub Action, compliance dashboard (HTML), remediation code snippets
