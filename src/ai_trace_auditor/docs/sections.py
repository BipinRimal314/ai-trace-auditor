"""Annex IV section builders — one function per section.

Each function takes a CodeScanResult and optional GapReport,
returns an AnnexIVSection with auto-populated content where possible.

Fixes applied (v0.10.1):
- Bug 1: GDPR roles reference organizations, not software
- Bug 2: Article 13 (provider→deployer) vs Article 50 (deployer→user) separated
- Bug 3: No percentage claims for per-article coverage
- Bug 4: Retention distinguishes Article 18 (10yr) from Article 26(6) (6mo)
- Bug 5: Scope check / risk classification included
"""

from __future__ import annotations

from ai_trace_auditor.models.docs import AnnexIVSection, CodeScanResult
from ai_trace_auditor.models.gap import GapReport

MANUAL = "[MANUAL INPUT REQUIRED]"


def build_scope_check(scan: CodeScanResult) -> AnnexIVSection:
    """Section 0: Risk classification and scope check.

    This is prepended to the document to help deployers determine
    if Articles 9-15 even apply to their system.
    """
    parts: list[str] = []

    parts.append("### Is your system in scope?\n")
    parts.append(
        "Articles 9-15 of the EU AI Act (including the technical documentation "
        "requirement in Article 11) apply only to **high-risk AI systems** as "
        "defined in Annex III. Before proceeding with compliance documentation, "
        "determine whether your system falls into one of these categories:\n"
    )
    parts.append("- **Recruitment and HR** — screening CVs, evaluating candidates, allocating tasks")
    parts.append("- **Credit scoring and insurance** — assessing creditworthiness or setting premiums")
    parts.append("- **Law enforcement** — profiling, criminal risk assessment, border control")
    parts.append("- **Critical infrastructure** — managing energy, water, transport, or telecommunications")
    parts.append("- **Education assessment** — grading students, determining admissions")
    parts.append("- **Essential public services** — evaluating eligibility for benefits, housing, emergency services")
    parts.append("")
    parts.append(
        "If your system does not obviously fall into these categories, the "
        "high-risk obligations (Articles 9-15) are less likely to apply. However, "
        "risk classification is context-dependent and can change as your system "
        "evolves. **Do not self-classify without legal review.** You may still "
        "have obligations under:\n"
    )
    parts.append("- **Article 50** — transparency for chatbots and systems interacting directly with users")
    parts.append("- **GDPR** — if processing personal data through AI providers")
    parts.append("")
    parts.append(
        "Consult a qualified legal professional to confirm your system's "
        "classification before relying on this assessment.\n"
    )

    if scan.has_ai_usage:
        parts.append("### Detected AI Components\n")
        parts.append(f"- **AI providers:** {', '.join(scan.providers) or 'none detected'}")
        parts.append(f"- **Models:** {', '.join(scan.models[:10]) or 'none detected'}")
        if len(scan.models) > 10:
            parts.append(f"  *(and {len(scan.models) - 10} more)*")
        parts.append("")

    return AnnexIVSection(
        section_number=0,
        title="Risk Classification and Scope",
        content="\n".join(parts),
        auto_populated=scan.has_ai_usage,
        confidence="medium" if scan.has_ai_usage else "manual",
    )


def build_section_1(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 1: General description of the AI system."""
    parts: list[str] = []
    confidence = "manual"
    auto = False

    if scan.providers:
        auto = True
        confidence = "medium"
        parts.append("### AI Providers and SDKs Detected\n")
        for provider in scan.providers:
            count = sum(1 for imp in scan.ai_imports if imp.library == provider)
            parts.append(f"- **{provider}** ({count} import{'s' if count > 1 else ''})")
        parts.append("")

    if scan.models:
        auto = True
        confidence = "medium"
        parts.append("### Model Identifiers\n")
        for model in scan.models:
            parts.append(f"- `{model}`")
        parts.append("")

    if scan.vector_dbs:
        auto = True
        parts.append("### Data Storage (Vector Databases)\n")
        dbs = sorted({vdb.db_name for vdb in scan.vector_dbs})
        for db in dbs:
            parts.append(f"- {db}")
        parts.append("")

    if scan.ai_endpoints:
        auto = True
        parts.append("### AI-Serving API Endpoints\n")
        for ep in scan.ai_endpoints:
            parts.append(f"- `{ep.route}` ({ep.framework}) — {ep.file_path}:{ep.line_number}")
        parts.append("")

    parts.append("### Intended Purpose\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe the intended purpose and use cases of this AI system.*\n")

    parts.append("### Target Users and Deployment Context\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe who will use this system and in what context.*\n")

    parts.append("### Version History\n")
    parts.append(f"{MANUAL}\n")

    return AnnexIVSection(
        section_number=1,
        title="General Description of the AI System",
        content="\n".join(parts),
        auto_populated=auto,
        confidence=confidence,
    )


def build_section_2(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 2: Detailed description of elements and development process."""
    parts: list[str] = []
    confidence = "manual"
    auto = False

    if scan.ai_imports:
        auto = True
        confidence = "medium"
        parts.append("### Software Components (Auto-Detected)\n")
        by_lib: dict[str, list[str]] = {}
        for imp in scan.ai_imports:
            by_lib.setdefault(imp.library, []).append(imp.module_path)
        for lib, modules in sorted(by_lib.items()):
            unique = sorted(set(modules))
            parts.append(f"- **{lib}**: {', '.join(f'`{m}`' for m in unique)}")
        parts.append("")

    if scan.models:
        auto = True
        confidence = "medium"
        parts.append("### Models Used\n")
        parts.append("| Model | Location | Context |")
        parts.append("|-------|----------|---------|")
        for ref in scan.model_references:
            parts.append(f"| `{ref.model_id}` | {ref.file_path}:{ref.line_number} | {ref.context[:60]} |")
        parts.append("")

    if scan.training_data_refs:
        auto = True
        parts.append("### Training / Fine-Tuning Data References\n")
        for td in scan.training_data_refs:
            parts.append(f"- `{td.pattern}` at {td.file_path}:{td.line_number}")
            parts.append(f"  Context: `{td.context}`")
        parts.append("")

    parts.append("### Algorithm Description\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe the algorithms and approaches used, design choices, and rationale.*\n")

    parts.append("### Development Methodology\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe the development process, version control, and quality assurance.*\n")

    return AnnexIVSection(
        section_number=2,
        title="Detailed Description of Elements and Development Process",
        content="\n".join(parts),
        auto_populated=auto,
        confidence=confidence,
    )


def build_section_3(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 3: Monitoring, functioning, and control."""
    parts: list[str] = []
    confidence = "manual"
    auto = False

    if gap_report is not None:
        auto = True
        confidence = "high" if gap_report.overall_score >= 0.8 else "medium"
        parts.append("### Trace Compliance Status\n")
        parts.append(f"- **Requirements satisfied:** {gap_report.summary.satisfied}")
        parts.append(f"- **Partial coverage:** {gap_report.summary.partial}")
        parts.append(f"- **Missing:** {gap_report.summary.missing}")
        parts.append("")

        if gap_report.summary.top_gaps:
            parts.append("### Monitoring Gaps Identified\n")
            for gap in gap_report.summary.top_gaps:
                parts.append(f"- {gap}")
            parts.append("")

    if scan.deployment_configs:
        auto = True
        parts.append("### Deployment Infrastructure\n")
        for dc in scan.deployment_configs:
            ai_flag = " (contains AI dependencies)" if dc.contains_ai_deps else ""
            parts.append(f"- {dc.config_type}: `{dc.file_path}`{ai_flag}")
        parts.append("")

    parts.append("### Human Oversight Measures\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe human-in-the-loop mechanisms, override capabilities, and escalation procedures.*\n")

    parts.append("### Logging and Monitoring\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Document what events are logged, where logs are stored, and monitoring alerts.*\n")

    return AnnexIVSection(
        section_number=3,
        title="Monitoring, Functioning, and Control",
        content="\n".join(parts),
        auto_populated=auto,
        confidence=confidence,
    )


def build_section_4(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 4: Appropriateness of performance metrics."""
    parts: list[str] = []
    confidence = "manual"
    auto = False

    if scan.eval_scripts:
        auto = True
        confidence = "medium"
        parts.append("### Evaluation Scripts Detected\n")
        for es in scan.eval_scripts:
            metrics_str = ", ".join(f"`{m}`" for m in es.metrics_detected)
            parts.append(f"- **{es.file_path}**: {metrics_str}")
        parts.append("")

    parts.append("### Metric Selection Rationale\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Explain why these metrics were chosen and how they relate to the system's intended purpose.*\n")

    parts.append("### Bias and Fairness Metrics\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe any fairness metrics, bias detection, and testing across demographic groups.*\n")

    parts.append("### Performance Thresholds\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Define acceptable performance thresholds and what happens when they are not met.*\n")

    return AnnexIVSection(
        section_number=4,
        title="Appropriateness of Performance Metrics",
        content="\n".join(parts),
        auto_populated=auto,
        confidence=confidence,
    )


def build_section_5(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 5: Risk management system."""
    parts: list[str] = []

    parts.append("### Risk Assessment Methodology\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe the risk assessment methodology used (e.g., FMEA, HAZOP, custom).*\n")

    parts.append("### Identified Risks\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*List identified risks, their likelihood, severity, and mitigation measures.*\n")

    parts.append("### Residual Risks\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe risks that remain after mitigation and their acceptability.*\n")

    if scan.has_ai_usage:
        parts.append("### Known Risk Surfaces (Auto-Detected)\n")
        parts.append("Based on detected AI usage, the following risk surfaces may apply:\n")
        if any(imp.library in ("openai", "anthropic", "google_genai") for imp in scan.ai_imports):
            parts.append("- **Third-party API dependency**: System relies on external AI providers")
        if scan.vector_dbs:
            parts.append("- **Data persistence**: Vector databases store embeddings that may contain PII")
        if scan.ai_endpoints:
            parts.append("- **Public-facing AI**: API endpoints expose AI capabilities to users")
        parts.append("")

    return AnnexIVSection(
        section_number=5,
        title="Risk Management System",
        content="\n".join(parts),
        auto_populated=scan.has_ai_usage,
        confidence="low" if scan.has_ai_usage else "manual",
    )


def build_section_6(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 6: Lifecycle changes."""
    parts: list[str] = []
    auto = False
    confidence = "manual"

    if gap_report is not None and gap_report.trace_count > 0:
        auto = True
        confidence = "low"
        parts.append("### Observed Model Versions (from trace data)\n")
        parts.append(f"- Traces analyzed: {gap_report.trace_count}")
        parts.append(f"- Spans analyzed: {gap_report.span_count}")
        parts.append("")

    parts.append("### Change Management Process\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe how changes to the AI system are managed, tested, and deployed.*\n")

    parts.append("### Version Control Policy\n")
    parts.append(f"{MANUAL}\n")

    parts.append("### Update Validation Process\n")
    parts.append(f"{MANUAL}\n")

    return AnnexIVSection(
        section_number=6,
        title="Lifecycle Changes",
        content="\n".join(parts),
        auto_populated=auto,
        confidence=confidence,
    )


def build_section_7(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 7: Applied harmonised standards."""
    parts: list[str] = []

    parts.append("### Applicable Standards Checklist\n")
    parts.append(f"{MANUAL}\n")
    parts.append("Check all that apply and provide evidence of conformity:\n")
    parts.append("- [ ] ISO/IEC 42001 — AI Management System")
    parts.append("- [ ] ISO/IEC 23894 — AI Risk Management")
    parts.append("- [ ] ISO/IEC 25059 — AI System Quality")
    parts.append("- [ ] ISO/IEC 38507 — Governance of AI")
    parts.append("- [ ] ISO/IEC 22989 — AI Concepts and Terminology")
    parts.append("- [ ] ISO/IEC 23053 — Framework for AI Systems Using ML")
    parts.append("- [ ] Other: ______________________")
    parts.append("")

    return AnnexIVSection(
        section_number=7,
        title="Applied Harmonised Standards",
        content="\n".join(parts),
        auto_populated=False,
        confidence="manual",
    )


def build_section_8(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 8: EU declaration of conformity."""
    parts: list[str] = []

    parts.append("### Declaration of Conformity\n")
    parts.append(f"{MANUAL}\n")
    parts.append("Complete the following fields:\n")
    parts.append("| Field | Value |")
    parts.append("|-------|-------|")
    parts.append("| AI system name | |")
    parts.append("| AI system version | |")
    parts.append("| Provider name | |")
    parts.append("| Provider address | |")
    parts.append("| Authorised representative | |")
    parts.append("| Risk classification | |")
    parts.append("| Notified body (if applicable) | |")
    parts.append("| Date of declaration | |")
    parts.append("| Signatory name and function | |")
    parts.append("")

    return AnnexIVSection(
        section_number=8,
        title="EU Declaration of Conformity",
        content="\n".join(parts),
        auto_populated=False,
        confidence="manual",
    )


def build_section_9(
    scan: CodeScanResult, gap_report: GapReport | None = None
) -> AnnexIVSection:
    """Section 9: Post-market monitoring system."""
    parts: list[str] = []
    auto = False
    confidence = "manual"

    if gap_report is not None:
        auto = True
        confidence = "medium"
        parts.append("### Current Monitoring Coverage (from trace data)\n")
        parts.append(f"- Requirements satisfied: {gap_report.summary.satisfied}")
        parts.append(f"- Gaps found: {gap_report.summary.missing + gap_report.summary.partial}")
        parts.append("")

    parts.append("### Data Retention\n")
    parts.append(
        "The required retention period depends on your role under the Act. "
        "**Article 18** requires providers of high-risk systems to retain logs "
        "and technical documentation for **10 years** after market placement. "
        "**Article 26(6)** requires deployers to retain logs for at least "
        "**6 months**, or longer if appropriate to the intended purpose. "
        "Confirm the applicable period with legal counsel.\n"
    )

    parts.append("### Monitoring Plan\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe how the system will be monitored after deployment.*\n")

    parts.append("### Incident Response Procedures\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe how incidents and failures will be detected, reported, and resolved.*\n")

    parts.append("### Feedback Collection\n")
    parts.append(f"{MANUAL}\n")
    parts.append("*Describe mechanisms for collecting user feedback and reporting issues.*\n")

    return AnnexIVSection(
        section_number=9,
        title="Post-Market Monitoring System",
        content="\n".join(parts),
        auto_populated=auto,
        confidence=confidence,
    )
