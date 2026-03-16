# EkLine Integration Spec

## What EkLine Gets

A compliance evidence layer for AI-generated documentation. Customers in regulated industries (finance, healthcare, government) can export a report proving their AI doc pipeline satisfies EU AI Act Article 12 and NIST AI RMF traceability requirements.

## Integration Architecture

```
EkLine AI Pipeline (Docs Reviewer / Docs Agent)
    |
    v
Trace Export (EkLine's internal format → ai-trace-auditor)
    |
    v
ComplianceAnalyzer (library API, not CLI)
    |
    v
Compliance Report (HTML dashboard / PDF export)
```

## What Bipin Builds

### 1. EkLine Trace Ingestor

EkLine's AI operations (doc review, doc generation, style enforcement) produce trace data. Need to understand the exact format. Questions for CTO:

- Where does EkLine log AI operations? (Database? Log files? API response cache?)
- What fields are captured per AI call? (Model, tokens, input doc, output suggestions, timestamps?)
- Does EkLine use any existing observability tool? (OTel, Datadog, custom?)
- What metadata exists? (User ID, workspace, document ID, PR number?)

Once the format is known, write an `EkLineIngestor` class (same pattern as `ClaudeCodeIngestor`).

### 2. Library API (already works)

```python
from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.regulations.registry import RequirementRegistry

# Load requirements
registry = RequirementRegistry()
registry.load()

# Analyze traces
analyzer = ComplianceAnalyzer(registry)
report = analyzer.analyze(
    traces=normalized_traces,
    regulations=["EU AI Act"],
    trace_source="ekline-workspace-123",
)

# Access results programmatically
print(report.overall_score)  # 0.0-1.0
print(report.summary.satisfied)  # count
for result in report.requirement_results:
    if result.status != "satisfied":
        print(f"{result.requirement.id}: {result.gaps[0].recommendation}")
```

No changes needed. The CLI is a thin wrapper around this API.

### 3. HTML Report Template

Add a Jinja2 HTML template alongside the existing Markdown one. Suitable for embedding in EkLine's dashboard or exporting as a standalone page. Includes:

- Overall compliance score (visual gauge)
- Per-requirement status cards (green/yellow/red)
- Evidence tables with sample values
- Gap recommendations
- Timestamp and trace source metadata
- EkLine branding option

### 4. Documentation-Specific Requirements

Add YAML requirements specific to AI-generated documentation:

```yaml
regulation: "AI Documentation Best Practices"
requirements:
  - id: "DOC-001"
    title: "Source document traceability"
    description: "AI-generated documentation must trace back to the source files, API specs, or existing docs that influenced the output."
    evidence_fields:
      - field_path: "spans[].input_messages"
        description: "Source documents provided as context"
        required: true
        check_type: "non_empty"

  - id: "DOC-002"
    title: "Human review attribution"
    description: "AI-generated content must record whether a human reviewed and approved the output."
    evidence_fields:
      - field_path: "spans[].evaluations"
        description: "Human review scores or approval status"
        required: true
        check_type: "non_empty"

  - id: "DOC-003"
    title: "Version correlation"
    description: "AI operations must correlate with the document version and the model version that produced the output."
    evidence_fields:
      - field_path: "spans[].model_used"
        required: true
        check_type: "non_null"
      - field_path: "metadata.document_version"
        required: true
        check_type: "non_null"
```

## Pricing Angle

- **Free tier**: Basic compliance score (pass/fail) in EkLine dashboard
- **Standard ($50/user/mo, existing)**: Full compliance report export (Markdown)
- **Enterprise**: PDF reports, trend analysis, custom requirement definitions, audit log retention

## Timeline

1. **Week 1**: Get trace format from CTO, write EkLineIngestor, test against real data
2. **Week 2**: HTML report template, documentation-specific requirements YAML
3. **Week 3**: Integration into EkLine's backend (API endpoint or scheduled job)
4. **Week 4**: Customer-facing UI (compliance tab in dashboard)

## What the CTO Needs to Provide

- [ ] Sample trace data from EkLine's AI operations (anonymized)
- [ ] Database schema or log format for AI call records
- [ ] Decision: embed in existing dashboard or standalone page?
- [ ] Decision: which pricing tier gets compliance reports?
- [ ] Access to EkLine's staging environment for integration testing
