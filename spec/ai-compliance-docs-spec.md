# AI Compliance Documentation Spec

**Version:** Draft v0.1.0
**Date:** 2026-03-23
**Author:** Bipin Rimal
**License:** CC-BY-4.0
**Tool:** [ai-trace-auditor](https://github.com/BipinRimal314/ai-trace-auditor)

> A machine-checkable specification for validating whether AI system documentation meets EU AI Act requirements for high-risk systems. Defines 38 checks across 6 categories, each with explicit pass/warn/fail criteria.

## Why This Spec Exists

The EU AI Act requires technical documentation (Article 11), automatic logging (Article 12), transparency information (Article 13), and processing records (GDPR Article 30) for high-risk AI systems by August 2, 2026. The regulation defines *what* must be documented but not *how to verify completeness*. No harmonised standard from CEN/CENELEC JTC 21 has been published yet.

This specification fills the gap: a set of concrete, automatable checks that determine whether an AI system's documentation package is complete, internally consistent, and traceable to code artifacts.

The spec is regulation-first, not tool-first. Each check maps to a specific article, paragraph, and subparagraph. The accompanying CLI (`aitrace`) implements these checks, but any tool can validate against this spec.

## Scope

This spec covers documentation requirements for **high-risk AI systems** classified under Annex III of the EU AI Act. It does not cover:

- General-purpose AI model obligations (Chapter V)
- Prohibited AI practices (Article 5)
- Low-risk AI system transparency obligations (Article 50)
- Quality management system requirements (Article 17)
- Conformity assessment procedures (Article 43)

## Terminology

- **Provider**: The entity that develops or commissions the AI system and places it on the market.
- **Deployer**: The entity that uses the AI system under its authority.
- **Documentation package**: The complete set of documents produced by a compliance check.
- **Evidence field**: A specific data point whose presence or absence can be verified in traces or code.
- **Check**: A single, atomic validation with a defined ID, inputs, and pass/warn/fail criteria.

## Severity Levels

Each check has a severity:

- **mandatory**: Required by the regulation. Failure means non-compliance.
- **recommended**: Not explicitly required but strongly implied by the regulation or necessary for practical compliance. Absence creates risk.
- **informational**: Useful for completeness but not required.

## Check Results

Each check produces one of four results:

- **pass**: The requirement is satisfied.
- **warn**: The requirement is partially satisfied or satisfied in a non-standard way.
- **fail**: The requirement is not satisfied.
- **skip**: The check is not applicable (e.g., no biometric data processing).

---

## Category 1: Technical Documentation Completeness (Article 11 / Annex IV)

These checks validate whether the generated Annex IV documentation contains all required sections and whether auto-populated fields are substantive (not placeholder-only).

### ACS-11.1 — Annex IV Section Presence

All 9 Annex IV sections must be present in the documentation.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.1` |
| **Article** | Article 11(1), Annex IV |
| **Severity** | mandatory |
| **Input** | Generated Annex IV document (Markdown or structured output) |
| **Pass** | All 9 sections present with at least one non-placeholder paragraph each |
| **Warn** | All 9 sections present but some contain only `[MANUAL INPUT REQUIRED]` placeholders |
| **Fail** | One or more sections missing entirely |

Required sections:
1. General system description
2. Development elements and process
3. Monitoring, functioning, and control
4. Performance metrics
5. Risk management system
6. Lifecycle changes
7. Standards applied
8. EU declaration of conformity
9. Post-market monitoring

### ACS-11.2 — System Description Populated

Section 1 must contain a substantive system description derived from code analysis, not generic placeholders.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.2` |
| **Article** | Annex IV, Section 1 |
| **Severity** | mandatory |
| **Input** | Section 1 of Annex IV document + code scan results |
| **Pass** | Section contains: intended purpose, provider name, system version, at least one detected AI SDK or model reference |
| **Warn** | Section present but all content is placeholder text |
| **Fail** | Section missing or empty |

### ACS-11.3 — AI Components Detected

Section 2 must identify specific AI components (SDKs, models, vector databases) found in the codebase.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.3` |
| **Article** | Annex IV, Section 2 |
| **Severity** | mandatory |
| **Input** | Code scan results (AI imports, model references, vector DB usage) |
| **Pass** | At least one AI SDK, model, or vector database detected and documented |
| **Warn** | AI components detected but fewer than expected for the codebase size |
| **Fail** | No AI components detected in a codebase that contains AI-related code |

### ACS-11.4 — Data Requirements Documented

Section 2 must include data requirements: training data descriptions, input specifications, or data governance measures.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.4` |
| **Article** | Annex IV, Section 2 (data requirements) |
| **Severity** | mandatory |
| **Input** | Section 2 of Annex IV document + code scan for data sources |
| **Pass** | Data sources identified (training data references, input schemas, database connections) with descriptions |
| **Warn** | Data section present but contains only placeholders |
| **Fail** | No data documentation and no `[MANUAL INPUT REQUIRED]` marker |

### ACS-11.5 — Testing and Validation Documented

Section 2 must describe testing procedures, metrics, and results.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.5` |
| **Article** | Annex IV, Section 2 (validation and testing) |
| **Severity** | mandatory |
| **Input** | Section 2 + test suite detection (pytest, jest, test directories) |
| **Pass** | Test framework detected, metrics described, and test coverage referenced |
| **Warn** | Test framework detected but no metrics or results documented |
| **Fail** | No testing documentation and no test framework detected |

### ACS-11.6 — Cybersecurity Measures Referenced

Section 2 must address cybersecurity measures (Article 15 cross-reference).

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.6` |
| **Article** | Annex IV, Section 2 (cybersecurity); Article 15 |
| **Severity** | mandatory |
| **Input** | Section 2 of Annex IV document |
| **Pass** | Cybersecurity section present with specific measures described |
| **Warn** | Cybersecurity section present with only generic statements |
| **Fail** | No cybersecurity section |

### ACS-11.7 — Performance Metrics Defined

Section 4 must define specific, measurable performance metrics with acceptable thresholds.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.7` |
| **Article** | Annex IV, Section 4 |
| **Severity** | mandatory |
| **Input** | Section 4 of Annex IV document |
| **Pass** | At least one metric defined with a numeric threshold and measurement methodology |
| **Warn** | Metrics mentioned but no thresholds or methodology |
| **Fail** | No performance metrics section |

### ACS-11.8 — Risk Management Cross-Reference

Section 5 must reference a risk management system per Article 9.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.8` |
| **Article** | Annex IV, Section 5; Article 9 |
| **Severity** | mandatory |
| **Input** | Section 5 of Annex IV document |
| **Pass** | Risk identification, analysis, and residual risk measures documented |
| **Warn** | Risk section present but does not reference Article 9 methodology |
| **Fail** | No risk management section |

### ACS-11.9 — Post-Market Monitoring Plan

Section 9 must describe the post-market monitoring system per Article 72.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.9` |
| **Article** | Annex IV, Section 9; Article 72 |
| **Severity** | mandatory |
| **Input** | Section 9 of Annex IV document |
| **Pass** | Monitoring plan present with review frequency, escalation criteria, and responsible parties |
| **Warn** | Monitoring plan present but lacks specifics |
| **Fail** | No post-market monitoring section |

### ACS-11.10 — Retention Period Stated

Documentation must state the applicable retention period (10 years for providers under Article 18, 6 months minimum for deployer logs under Article 26(5)).

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.10` |
| **Article** | Article 18; Article 26(5) |
| **Severity** | mandatory |
| **Input** | Annex IV document (any section) |
| **Pass** | Retention period explicitly stated with correct Article reference |
| **Warn** | Retention period stated but without Article reference |
| **Fail** | No retention period mentioned |

### ACS-11.11 — Scope Classification Present

Documentation must begin with a risk classification check: which Annex III categories apply and why the system is classified as high-risk.

| Field | Value |
|-------|-------|
| **ID** | `ACS-11.11` |
| **Article** | Article 6; Annex III |
| **Severity** | recommended |
| **Input** | Annex IV document (Section 0 or preamble) |
| **Pass** | Specific Annex III category referenced with justification |
| **Warn** | Generic statement that system is high-risk without category reference |
| **Fail** | No risk classification |

---

## Category 2: Record-Keeping Completeness (Article 12)

These checks validate whether an AI system's traces contain the evidence fields required for automatic event recording.

### ACS-12.1 — Event Timestamps

Every AI operation must have start and end timestamps.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.1` |
| **Article** | Article 12(1) |
| **Severity** | mandatory |
| **Input** | Trace data (any supported format) |
| **Pass** | >= 95% of spans have both `start_time` and `end_time` |
| **Warn** | >= 80% of spans have both timestamps |
| **Fail** | < 80% of spans have both timestamps |

### ACS-12.2 — Operation Identification

Each event must identify the operation type, model, and provider.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.2` |
| **Article** | Article 12(1) |
| **Severity** | mandatory |
| **Input** | Trace data |
| **Pass** | >= 95% of spans have `operation` and `provider`; >= 90% have `model_used` |
| **Warn** | >= 80% coverage on operation and provider |
| **Fail** | < 80% coverage |

### ACS-12.3 — Error and Risk Event Logging

Errors, failures, and abnormal terminations must be captured.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.3` |
| **Article** | Article 12(2) |
| **Severity** | mandatory |
| **Input** | Trace data |
| **Pass** | `error_type` field present on spans where errors occurred; `finish_reasons` populated on >= 90% of spans |
| **Warn** | Error fields present but `finish_reasons` below 90% |
| **Fail** | No error-related fields present in any span |

### ACS-12.4 — Model Version Tracking

The actual model version used (not just requested) must be logged.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.4` |
| **Article** | Article 12(2); Article 72 (post-market monitoring) |
| **Severity** | mandatory |
| **Input** | Trace data |
| **Pass** | `model_used` present on >= 90% of spans |
| **Warn** | Only `model_requested` present (not the actual version from the response) |
| **Fail** | No model version information |

### ACS-12.5 — Trace Linkage

Multi-step operations must maintain parent-child relationships for causal reconstruction.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.5` |
| **Article** | Article 12(1) (traceability) |
| **Severity** | mandatory |
| **Input** | Trace data |
| **Pass** | All spans have `span_id`; multi-step traces have valid `parent_span_id` references |
| **Warn** | `span_id` present but no parent-child relationships in multi-step traces |
| **Fail** | No `span_id` fields |

### ACS-12.6 — Resource Consumption

Token counts and latency should be logged for monitoring and anomaly detection.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.6` |
| **Article** | Article 12(2); Article 26(5) (deployer monitoring) |
| **Severity** | recommended |
| **Input** | Trace data |
| **Pass** | `input_tokens` and `output_tokens` present on >= 80% of spans |
| **Warn** | Token fields present on >= 50% of spans |
| **Fail** | No token usage data |

### ACS-12.7 — Request Parameters

Configuration parameters that influence AI behavior should be recorded for reproducibility.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.7` |
| **Article** | Article 12(2) (behavior explanation) |
| **Severity** | recommended |
| **Input** | Trace data |
| **Pass** | At least one of `temperature`, `max_tokens`, `top_p` present on >= 50% of spans |
| **Warn** | Parameters present on < 50% of spans |
| **Fail** | No request parameters logged |

### ACS-12.8 — Content Recording (Opt-In)

For high-risk systems, input/output content should be recorded for post-hoc review. This check respects privacy: absence is not failure unless the system processes high-risk categories (biometric, employment, law enforcement).

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.8` |
| **Article** | Article 12(3) (biometric); Article 14 (human oversight) |
| **Severity** | informational |
| **Input** | Trace data + risk classification |
| **Pass** | `input_messages` and `output_messages` present on >= 50% of spans |
| **Warn** | Content fields present on < 50% of spans |
| **Skip** | System does not process high-risk categories (content recording not required) |

### ACS-12.9 — Tool and Function Call Logging

When AI systems use tools, the calls must be logged for audit trail completeness.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.9` |
| **Article** | Article 12(1) (complete audit trail) |
| **Severity** | recommended |
| **Input** | Trace data |
| **Pass** | `tool_calls` present on spans where tools were invoked; includes tool name and arguments |
| **Warn** | `tool_calls` present but missing arguments or results |
| **Skip** | No tool usage detected in traces |

### ACS-12.10 — Retention Compliance

Logs must be retained for at least 6 months (deployer) or as specified by the provider.

| Field | Value |
|-------|-------|
| **ID** | `ACS-12.10` |
| **Article** | Article 19(1); Article 26(5) |
| **Severity** | mandatory |
| **Input** | Trace data timestamps + current date |
| **Pass** | Oldest trace is >= 6 months old and still accessible |
| **Warn** | Traces present but oldest is < 6 months (insufficient history to verify) |
| **Fail** | No timestamps present or traces are clearly truncated |

---

## Category 3: Transparency Documentation (Article 13)

These checks validate whether the documentation package includes sufficient information for deployers to interpret and use the system appropriately.

### ACS-13.1 — Provider Identification

Instructions for use must identify the provider and contact details.

| Field | Value |
|-------|-------|
| **ID** | `ACS-13.1` |
| **Article** | Article 13(3)(a) |
| **Severity** | mandatory |
| **Input** | Annex IV document or instructions for use |
| **Pass** | Provider name, contact details, and version number present |
| **Warn** | Provider name present but contact details missing |
| **Fail** | No provider identification |

### ACS-13.2 — Capabilities and Limitations

Documentation must describe what the system can and cannot do, including known failure modes.

| Field | Value |
|-------|-------|
| **ID** | `ACS-13.2` |
| **Article** | Article 13(3)(b) |
| **Severity** | mandatory |
| **Input** | Annex IV document (Sections 1, 3) |
| **Pass** | Both capabilities and limitations described with specific scenarios |
| **Warn** | Capabilities described but limitations are vague or absent |
| **Fail** | No capabilities or limitations section |

### ACS-13.3 — Accuracy and Performance Disclosure

Expected accuracy levels and the conditions under which they were measured must be disclosed.

| Field | Value |
|-------|-------|
| **ID** | `ACS-13.3` |
| **Article** | Article 13(3)(b)(i); Article 15 |
| **Severity** | mandatory |
| **Input** | Annex IV document (Section 4) + trace-derived metrics |
| **Pass** | At least one accuracy metric with numeric value, measurement conditions, and known impact factors |
| **Warn** | Accuracy mentioned qualitatively but no numeric metrics |
| **Fail** | No accuracy information |

### ACS-13.4 — Human Oversight Measures

Documentation must describe what human oversight mechanisms exist and how to use them.

| Field | Value |
|-------|-------|
| **ID** | `ACS-13.4` |
| **Article** | Article 13(3)(d); Article 14 |
| **Severity** | mandatory |
| **Input** | Annex IV document (Section 1, human oversight subsection) |
| **Pass** | Specific oversight mechanisms described (review workflow, override capability, escalation path) |
| **Warn** | Human oversight mentioned but mechanisms are vague |
| **Fail** | No human oversight documentation |

### ACS-13.5 — Output Interpretation Guidance

Deployers must receive guidance on how to interpret system outputs.

| Field | Value |
|-------|-------|
| **ID** | `ACS-13.5` |
| **Article** | Article 13(3)(b)(iv); Article 13(3)(d) |
| **Severity** | mandatory |
| **Input** | Annex IV document or instructions for use |
| **Pass** | Output format described with interpretation guidance (what scores mean, confidence levels, recommended thresholds for action) |
| **Warn** | Output format described but no interpretation guidance |
| **Fail** | No output documentation |

### ACS-13.6 — Log Interpretation Mechanism

Documentation must describe how deployers can collect, store, and interpret logs (Article 12 cross-reference).

| Field | Value |
|-------|-------|
| **ID** | `ACS-13.6` |
| **Article** | Article 13(3)(f) |
| **Severity** | recommended |
| **Input** | Annex IV document or instructions for use |
| **Pass** | Log format, storage requirements, and interpretation guidance provided |
| **Warn** | Log format mentioned but no interpretation guidance |
| **Fail** | No log documentation for deployers |

---

## Category 4: Data Flow and Processing Records (GDPR Article 30)

These checks validate whether the documentation package includes complete records of processing activities for AI systems that handle personal data.

### ACS-30.1 — ROPA Entries Present

A Record of Processing Activities must exist for each external service that processes personal data.

| Field | Value |
|-------|-------|
| **ID** | `ACS-30.1` |
| **Article** | GDPR Article 30(1) |
| **Severity** | mandatory |
| **Input** | Flow analysis output (detected external services) |
| **Pass** | ROPA entry exists for every detected external service with purpose, data categories, and legal basis |
| **Warn** | ROPA entries exist but some are incomplete |
| **Fail** | No ROPA entries for detected external services |

### ACS-30.2 — GDPR Roles Assigned

Each external service must be classified as controller, processor, or joint controller.

| Field | Value |
|-------|-------|
| **ID** | `ACS-30.2` |
| **Article** | GDPR Articles 4(7), 4(8), 26 |
| **Severity** | mandatory |
| **Input** | Flow analysis output |
| **Pass** | Every external service has a GDPR role assignment referencing the organization (not the software) |
| **Warn** | Roles assigned but reference software names instead of organizations |
| **Fail** | No GDPR role assignments |

### ACS-30.3 — Data Flow Diagram

A visual or structured representation of data flows between components must be present.

| Field | Value |
|-------|-------|
| **ID** | `ACS-30.3` |
| **Article** | GDPR Article 30(1); Article 13(3)(b) of AI Act |
| **Severity** | recommended |
| **Input** | Flow analysis output |
| **Pass** | Mermaid diagram or equivalent present showing data flow between system components and external services |
| **Warn** | Textual description of data flows without diagram |
| **Fail** | No data flow documentation |

### ACS-30.4 — Third-Country Transfer Identification

If personal data is sent to services outside the EU/EEA, the transfer must be documented.

| Field | Value |
|-------|-------|
| **ID** | `ACS-30.4` |
| **Article** | GDPR Article 30(1)(e); Articles 44-49 |
| **Severity** | mandatory |
| **Input** | Flow analysis output (detected AI providers, cloud services) |
| **Pass** | Transfer destinations identified with legal basis (adequacy decision, SCCs, or Article 49 derogation) |
| **Warn** | US-based services detected (OpenAI, Anthropic, etc.) but no transfer mechanism documented |
| **Fail** | External services detected with no transfer analysis |

### ACS-30.5 — Retention Periods per Processing Activity

Each ROPA entry must specify how long data is retained.

| Field | Value |
|-------|-------|
| **ID** | `ACS-30.5` |
| **Article** | GDPR Article 30(1)(f) |
| **Severity** | recommended |
| **Input** | ROPA entries |
| **Pass** | Each entry has a specific retention period or erasure policy |
| **Warn** | Some entries have retention periods, others do not |
| **Fail** | No retention periods documented |

---

## Category 5: Internal Consistency

These checks validate that the documentation package is internally consistent: claims in one section do not contradict claims in another.

### ACS-IC.1 — Code-to-Documentation Alignment

AI components detected in code must appear in the Annex IV documentation.

| Field | Value |
|-------|-------|
| **ID** | `ACS-IC.1` |
| **Article** | Article 11(1) (documentation must demonstrate compliance) |
| **Severity** | mandatory |
| **Input** | Code scan results + Annex IV document |
| **Pass** | Every detected AI SDK, model, and vector database appears in the documentation |
| **Warn** | >= 80% of detected components are documented |
| **Fail** | < 80% of detected components appear in documentation |

### ACS-IC.2 — Trace-to-Documentation Alignment

Fields present in traces should be referenced in the logging documentation.

| Field | Value |
|-------|-------|
| **ID** | `ACS-IC.2` |
| **Article** | Article 12; Article 13(3)(f) |
| **Severity** | recommended |
| **Input** | Trace data fields + Annex IV document |
| **Pass** | Log documentation references all field types present in actual traces |
| **Warn** | Some trace fields not mentioned in documentation |
| **Fail** | No correlation between documented logging and actual traces |

### ACS-IC.3 — Flow-to-ROPA Alignment

Every external service detected in the data flow analysis must have a corresponding ROPA entry.

| Field | Value |
|-------|-------|
| **ID** | `ACS-IC.3` |
| **Article** | GDPR Article 30; Article 13(3)(b) of AI Act |
| **Severity** | mandatory |
| **Input** | Flow analysis results + ROPA entries |
| **Pass** | 1:1 mapping between detected external services and ROPA entries |
| **Warn** | Some services detected but no ROPA entry |
| **Fail** | Multiple detected services with no ROPA entries |

---

## Category 6: Documentation Quality

These checks evaluate whether the documentation is practically useful, not just structurally present.

### ACS-DQ.1 — Placeholder Ratio

The ratio of placeholder text (`[MANUAL INPUT REQUIRED]`) to substantive content indicates how much manual work remains.

| Field | Value |
|-------|-------|
| **ID** | `ACS-DQ.1` |
| **Article** | N/A (quality metric) |
| **Severity** | informational |
| **Input** | Generated documentation |
| **Pass** | < 20% of content sections contain only placeholders |
| **Warn** | 20-50% placeholder content |
| **Fail** | > 50% placeholder content |

### ACS-DQ.2 — Unverifiable Claims Absent

Documentation must not contain percentage claims that cannot be traced to code analysis or trace data.

| Field | Value |
|-------|-------|
| **ID** | `ACS-DQ.2` |
| **Article** | Article 11(1) (demonstrate compliance) |
| **Severity** | recommended |
| **Input** | Generated documentation |
| **Pass** | All numeric claims are either auto-populated from scan/trace data or explicitly marked as manual input |
| **Warn** | Some numeric claims without source attribution |
| **Fail** | Multiple unverifiable percentage or coverage claims |

### ACS-DQ.3 — Article References Correct

Legal references in the documentation must cite the correct articles and paragraphs.

| Field | Value |
|-------|-------|
| **ID** | `ACS-DQ.3` |
| **Article** | N/A (accuracy metric) |
| **Severity** | recommended |
| **Input** | Generated documentation |
| **Pass** | All Article/Annex references match the actual regulation text |
| **Warn** | References present but some cite wrong paragraphs |
| **Fail** | Multiple incorrect legal references |

---

## Scoring

### Overall Compliance Score

The overall score is a weighted sum:

```
score = (mandatory_passed / mandatory_total) * 70
      + (recommended_passed / recommended_total) * 25
      + (informational_passed / informational_total) * 5
```

### Score Interpretation

| Score | Interpretation |
|-------|----------------|
| >= 90 | Documentation package likely sufficient for conformity assessment |
| 70-89 | Significant gaps remain; manual review and completion required |
| 50-69 | Skeleton present but substantial work needed |
| < 50 | Documentation fundamentally incomplete |

### Per-Article Scores

Individual scores are computed for each category:

- **Article 11 score**: ACS-11.* checks only
- **Article 12 score**: ACS-12.* checks only
- **Article 13 score**: ACS-13.* checks only
- **GDPR Article 30 score**: ACS-30.* checks only

This allows teams to prioritize: fix the lowest-scoring article first.

---

## Implementation Notes

### For Tool Implementers

1. **Check IDs are stable.** New checks may be added with new IDs; existing IDs will not change semantics.
2. **Severity may be upgraded.** As harmonised standards from CEN/CENELEC JTC 21 are published, some "recommended" checks may become "mandatory."
3. **Thresholds are configurable.** The percentages in pass/warn/fail criteria (e.g., 95%, 80%) are defaults. Implementers should allow override via configuration for organization-specific policies.
4. **Output format.** Implementers should support at minimum Markdown and JSON output. GitHub Actions annotation format (`::error`, `::warning`) is recommended for CI integration.

### For Compliance Officers

1. **This spec does not replace legal advice.** It validates documentation structure and completeness. Whether the content is legally sufficient requires human review by qualified counsel.
2. **Placeholder sections are expected.** Auto-generation can populate code-derived fields; business context (risk assessments, monitoring plans, organizational decisions) requires manual input.
3. **The spec covers documentation, not the system itself.** A passing score means the documentation is complete, not that the AI system is compliant. The documentation is one component of the conformity assessment.

---

## Changelog

### Draft v0.1.0 (2026-03-23)

- Initial specification: 38 checks across 6 categories
- Covers Articles 11, 12, 13 (EU AI Act) and Article 30 (GDPR)
- Scoring model with per-article breakdown
- Aligned with ai-trace-auditor v0.11.0 capabilities
