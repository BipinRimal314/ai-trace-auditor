"""Unified compliance runner — orchestrates audit, docs, and flow in one pass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.docs.assembler import generate_annex_iv
from ai_trace_auditor.flow.detector import detect_flows
from ai_trace_auditor.flow.mermaid import generate_mermaid
from ai_trace_auditor.flow.ropa import generate_ropa
from ai_trace_auditor.ingest.detect import ingest_directory, ingest_file
from ai_trace_auditor.models.docs import AnnexIVDocument, CodeScanResult
from ai_trace_auditor.models.flow import FlowDiagram, FlowScanResult, RoPAReport
from ai_trace_auditor.models.gap import GapReport
from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.scanner.scan import scan_codebase


@dataclass
class CompliancePackage:
    """Complete EU AI Act compliance package from a single run."""

    generated_at: datetime
    source_dir: str

    # Code scan (shared by docs + flow)
    code_scan: CodeScanResult

    # Article 12 — Record-keeping
    gap_report: GapReport | None = None

    # Article 11 — Technical documentation
    annex_iv: AnnexIVDocument | None = None

    # Data flow mapping (supports Article 13 documentation + GDPR Article 30)
    flow_scan: FlowScanResult | None = None
    flow_diagram: FlowDiagram | None = None
    ropa: RoPAReport | None = None

    # Summary
    articles_covered: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def compliance_score(self) -> float | None:
        if self.gap_report is not None:
            return self.gap_report.overall_score
        return None

    @property
    def docs_completion_pct(self) -> float:
        if self.annex_iv is not None:
            return self.annex_iv.completion_pct
        return 0.0

    @property
    def service_count(self) -> int:
        if self.flow_scan is not None:
            return len(self.flow_scan.external_services)
        return 0

    @property
    def flow_count(self) -> int:
        if self.flow_scan is not None:
            return len(self.flow_scan.data_flows)
        return 0


def run_full_compliance(
    codebase_dir: Path,
    trace_path: Path | None = None,
    trace_format: str = "auto",
    risk_level: str = "high_risk",
    custom_requirements: list[str] | None = None,
) -> CompliancePackage:
    """Run the full EU AI Act compliance suite in one pass.

    1. Scan codebase (shared between docs + flow)
    2. If traces provided: run Article 12 audit
    3. Generate Article 11 Annex IV documentation
    4. Map data flows (supports Article 13 evidence + GDPR Article 30 RoPA)
    5. Flag Article 50 obligations when user-facing endpoints detected

    Note on Article 13 vs 50:
    - Article 13: provider must document system for deployers (documentation obligation)
    - Article 50: deployer must disclose AI to end users (UI/UX obligation)
    This tool provides supporting evidence for Article 13 but cannot satisfy it alone.
    Article 50 compliance requires UI changes that are outside this tool's scope.

    Returns a CompliancePackage with all results.
    """
    now = datetime.now(timezone.utc)
    articles: list[str] = []
    warnings: list[str] = []

    # Step 1: Code scan (shared)
    code_scan = scan_codebase(codebase_dir)

    if not code_scan.has_ai_usage:
        warnings.append(
            "No AI framework usage detected. "
            "The scanner checks Python and JS/TS files for known AI SDKs."
        )

    # Scope classification warning (from PR review feedback: deployers
    # must not self-classify as non-high-risk without legal review)
    warnings.append(
        "Risk classification: This tool audits technical compliance but cannot "
        "determine whether your system is high-risk under Annex III. "
        "Risk classification depends on use case, not technology. "
        "Do not self-classify without legal review."
    )

    # Step 2: Article 12 — Trace audit (if traces provided)
    gap_report = None
    if trace_path is not None:
        traces = (
            ingest_directory(trace_path, trace_format)
            if trace_path.is_dir()
            else ingest_file(trace_path, trace_format)
        )
        if traces:
            extra_dirs = [Path(p) for p in (custom_requirements or [])]
            registry = RequirementRegistry()
            registry.load(extra_dirs=extra_dirs or None)
            analyzer = ComplianceAnalyzer(registry)
            gap_report = analyzer.analyze(
                traces=traces,
                risk_level=risk_level,
                trace_source=str(trace_path),
            )
            articles.append("Article 12 (Record-Keeping)")
        else:
            warnings.append("Trace path provided but no traces found.")

    # Step 3: Article 11 — Technical documentation
    annex_iv = generate_annex_iv(code_scan, gap_report)
    articles.append("Article 11 (Technical Documentation)")

    # Step 4: Data flow mapping (supports Article 13 + Article 50 + GDPR Article 30)
    # Note: Article 13 = provider→deployer documentation (this tool provides
    # supporting evidence, not the documentation itself).
    # Article 50 = deployer→user disclosure (cannot be automated by this tool,
    # but flagged as a reminder when user-facing endpoints are detected).
    flow_scan = detect_flows(codebase_dir, code_scan)
    mermaid_src = generate_mermaid(flow_scan)
    ropa = generate_ropa(flow_scan)

    flow_diagram = FlowDiagram(
        mermaid=mermaid_src,
        services=flow_scan.external_services,
        flows=flow_scan.data_flows,
        generated_at=now,
        source_dir=str(codebase_dir),
        trace_enriched=gap_report is not None,
    )
    articles.append("Article 13 (Transparency — provider→deployer documentation)")
    articles.append("GDPR Article 30 (RoPA)")

    # Article 50 reminder when user-facing AI is detected
    if code_scan.ai_endpoints:
        articles.append("Article 50 (Transparency — deployer→user disclosure)")
        warnings.append(
            "Article 50: User-facing AI endpoints detected. Deployers must "
            "inform end users that they are interacting with an AI system, "
            "unless this is obvious from the circumstances and context of use "
            "(e.g., a platform whose sole purpose is AI interaction). "
            "For embedded AI features within non-AI products, explicit disclosure is required. "
            "This is a UI/UX obligation that cannot be satisfied by logging alone."
        )

    # Flag cross-border transfers requiring safeguards
    transfer_providers = [
        f.destination for f in flow_scan.data_flows
        if f.requires_transfer_safeguards
    ]
    if transfer_providers:
        warnings.append(
            f"Cross-border transfers detected to non-EEA providers: "
            f"{', '.join(transfer_providers)}. "
            f"Each requires Standard Contractual Clauses (SCCs) or equivalent "
            f"safeguards under GDPR Chapter V. Review each provider's transfer "
            f"mechanism individually."
        )

    return CompliancePackage(
        generated_at=now,
        source_dir=str(codebase_dir),
        code_scan=code_scan,
        gap_report=gap_report,
        annex_iv=annex_iv,
        flow_scan=flow_scan,
        flow_diagram=flow_diagram,
        ropa=ropa,
        articles_covered=articles,
        warnings=warnings,
    )
