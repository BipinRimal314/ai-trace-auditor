"""MCP server for AI Trace Auditor.

Exposes core compliance tools as MCP (Model Context Protocol) tools
so AI coding assistants (Claude Code, Cursor, etc.) can call them
directly without shelling out to the CLI.

Usage:
    aitrace-mcp              # stdio transport (default for IDE integration)
    python -m ai_trace_auditor.mcp_server
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "ai-trace-auditor",
    version="0.12.0",
    description=(
        "EU AI Act compliance suite: scan codebases for AI framework usage, "
        "audit traces against regulations, generate Article 11 technical "
        "documentation, map Article 13 data flows, and list requirements."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1: aitrace_comply — full compliance scan
# ---------------------------------------------------------------------------

@mcp.tool()
def aitrace_comply(path: str) -> str:
    """Run full EU AI Act compliance scan on a codebase directory.

    Scans the codebase and generates a complete compliance package covering
    Articles 11 (technical documentation), 13 (data flow transparency),
    and GDPR Article 30 (Record of Processing Activities).

    Args:
        path: Absolute path to the codebase directory to scan.

    Returns:
        Compliance report summary with score, articles covered, key findings,
        and any warnings.
    """
    try:
        codebase_dir = Path(path).resolve()
        if not codebase_dir.exists() or not codebase_dir.is_dir():
            return f"Error: {path} is not a valid directory"

        from ai_trace_auditor.comply.runner import run_full_compliance
        from ai_trace_auditor.reports.comply_report import ComplyReporter

        pkg = run_full_compliance(codebase_dir=codebase_dir)

        # Build a structured summary for the AI assistant
        summary = _build_comply_summary(pkg)

        # Also generate the full markdown report
        reporter = ComplyReporter()
        full_report = reporter.render(pkg)

        return json.dumps({
            "summary": summary,
            "full_report": full_report,
        }, indent=2, default=str)

    except Exception as e:
        return f"Error running compliance scan: {e}\n{traceback.format_exc()}"


def _build_comply_summary(pkg: object) -> dict:
    """Build a structured summary dict from a CompliancePackage."""
    summary: dict = {
        "source_dir": pkg.source_dir,
        "generated_at": pkg.generated_at.isoformat(),
        "articles_covered": pkg.articles_covered,
    }

    # Article 11 docs
    summary["article_11_docs_completion_pct"] = pkg.docs_completion_pct

    # Article 12 audit (only if traces were provided)
    if pkg.gap_report is not None:
        summary["article_12_compliance_score"] = round(pkg.gap_report.overall_score * 100, 1)
        summary["article_12_satisfied"] = pkg.gap_report.summary.satisfied
        summary["article_12_partial"] = pkg.gap_report.summary.partial
        summary["article_12_missing"] = pkg.gap_report.summary.missing
        summary["article_12_top_gaps"] = pkg.gap_report.summary.top_gaps
    else:
        summary["article_12_note"] = "No traces provided. Use aitrace_audit with trace files for Article 12."

    # Article 13 flows
    summary["article_13_services"] = pkg.service_count
    summary["article_13_flows"] = pkg.flow_count

    # GDPR RoPA
    summary["gdpr_ropa_entries"] = len(pkg.ropa.entries) if pkg.ropa else 0

    # Code scan stats
    summary["files_scanned"] = pkg.code_scan.file_count
    summary["ai_providers"] = list(pkg.code_scan.providers)
    summary["models_detected"] = list(pkg.code_scan.models[:5])

    # Warnings
    summary["warnings"] = pkg.warnings

    return summary


# ---------------------------------------------------------------------------
# Tool 2: aitrace_audit — audit traces against regulations
# ---------------------------------------------------------------------------

@mcp.tool()
def aitrace_audit(traces_path: str, regulation: str | None = None) -> str:
    """Audit LLM trace files against regulatory compliance requirements.

    Loads trace files (OpenTelemetry, Langfuse, or raw JSON), checks them
    against EU AI Act and NIST AI RMF requirements, and returns a gap report.

    Args:
        traces_path: Path to a trace file or directory containing trace files.
        regulation: Optional filter to a specific regulation (e.g., "EU AI Act", "NIST AI RMF").

    Returns:
        Gap report with compliance score, requirement results, and top gaps.
    """
    try:
        trace_path = Path(traces_path).resolve()
        if not trace_path.exists():
            return f"Error: {traces_path} does not exist"

        from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
        from ai_trace_auditor.ingest.detect import ingest_directory, ingest_file
        from ai_trace_auditor.regulations.registry import RequirementRegistry
        from ai_trace_auditor.reports.markdown import MarkdownReporter

        # Load traces
        if trace_path.is_dir():
            traces = ingest_directory(trace_path, "auto")
        else:
            traces = ingest_file(trace_path, "auto")

        if not traces:
            return "No traces found at the specified path."

        # Load requirements
        registry = RequirementRegistry()
        registry.load()

        # Parse regulation filter
        regulations = [regulation] if regulation else None

        # Run analysis
        analyzer = ComplianceAnalyzer(registry)
        report = analyzer.analyze(
            traces=traces,
            regulations=regulations,
            risk_level="high_risk",
            trace_source=str(trace_path),
        )

        # Build structured summary
        summary = {
            "trace_source": report.trace_source,
            "trace_count": report.trace_count,
            "span_count": report.span_count,
            "regulations_checked": report.regulations_checked,
            "overall_score": round(report.overall_score * 100, 1),
            "satisfied": report.summary.satisfied,
            "partial": report.summary.partial,
            "missing": report.summary.missing,
            "not_applicable": report.summary.not_applicable,
            "top_gaps": report.summary.top_gaps,
        }

        # Render full markdown report
        renderer = MarkdownReporter()
        full_report = renderer.render(report)

        return json.dumps({
            "summary": summary,
            "full_report": full_report,
        }, indent=2, default=str)

    except Exception as e:
        return f"Error auditing traces: {e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Tool 3: aitrace_docs — generate Article 11 technical documentation
# ---------------------------------------------------------------------------

@mcp.tool()
def aitrace_docs(path: str) -> str:
    """Generate EU AI Act Article 11 / Annex IV technical documentation.

    Scans a codebase for AI framework usage (SDKs, models, vector DBs,
    training data, evaluation scripts, deployment configs, API endpoints)
    and generates a structured Markdown document following Annex IV.

    Args:
        path: Absolute path to the codebase directory to scan.

    Returns:
        Annex IV document with all 9 sections plus a scope check.
    """
    try:
        codebase_dir = Path(path).resolve()
        if not codebase_dir.exists() or not codebase_dir.is_dir():
            return f"Error: {path} is not a valid directory"

        from ai_trace_auditor.docs import generate_annex_iv
        from ai_trace_auditor.reports.docs_report import DocsReporter
        from ai_trace_auditor.scanner import scan_codebase

        # Scan codebase
        scan_result = scan_codebase(codebase_dir)

        # Generate Annex IV document
        doc = generate_annex_iv(scan_result)
        reporter = DocsReporter()
        rendered = reporter.render(doc)

        # Build structured summary
        summary = {
            "source_dir": str(codebase_dir),
            "files_scanned": scan_result.file_count,
            "has_ai_usage": scan_result.has_ai_usage,
            "ai_providers": list(scan_result.providers),
            "models_detected": list(scan_result.models[:5]),
            "completion_pct": doc.completion_pct,
            "section_count": len(doc.sections),
            "trace_enriched": doc.trace_enriched,
        }

        return json.dumps({
            "summary": summary,
            "annex_iv_document": rendered,
        }, indent=2, default=str)

    except Exception as e:
        return f"Error generating documentation: {e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Tool 4: aitrace_flow — data flow analysis
# ---------------------------------------------------------------------------

@mcp.tool()
def aitrace_flow(path: str) -> str:
    """Map AI data flows for EU AI Act Article 13 and GDPR Article 30.

    Scans a codebase for external service connections (AI providers,
    vector DBs, databases, HTTP clients, cloud SDKs), generates a
    Mermaid data flow diagram, and produces a GDPR Article 30 Record
    of Processing Activities (RoPA) template.

    Args:
        path: Absolute path to the codebase directory to scan.

    Returns:
        Mermaid diagram source, external services list, data flows,
        and GDPR RoPA summary.
    """
    try:
        codebase_dir = Path(path).resolve()
        if not codebase_dir.exists() or not codebase_dir.is_dir():
            return f"Error: {path} is not a valid directory"

        from ai_trace_auditor.flow import detect_flows, generate_mermaid, generate_ropa
        from ai_trace_auditor.models.flow import FlowDiagram
        from ai_trace_auditor.reports.flow_report import FlowReporter
        from ai_trace_auditor.scanner import scan_codebase

        # Scan codebase first (needed for AI provider/vector DB detection)
        code_scan = scan_codebase(codebase_dir)

        # Detect flows
        flow_result = detect_flows(codebase_dir, code_scan)

        # Generate Mermaid diagram
        mermaid_src = generate_mermaid(flow_result)

        # Generate RoPA
        ropa = generate_ropa(flow_result)

        # Build full report
        now = datetime.now(timezone.utc)
        diagram = FlowDiagram(
            mermaid=mermaid_src,
            services=flow_result.external_services,
            flows=flow_result.data_flows,
            generated_at=now,
            source_dir=str(codebase_dir),
        )

        reporter = FlowReporter()
        full_report = reporter.render(diagram, ropa)

        # Build structured summary
        services_list = [
            {
                "name": svc.name,
                "category": svc.category,
                "service_type": svc.service_type,
            }
            for svc in flow_result.external_services
        ]

        flows_list = [
            {
                "source": f.source,
                "destination": f.destination,
                "data_type": f.data_type,
                "purpose": f.purpose,
                "gdpr_role": f.gdpr_role,
                "contains_pii": f.contains_pii,
                "requires_transfer_safeguards": f.requires_transfer_safeguards,
            }
            for f in flow_result.data_flows
        ]

        summary = {
            "source_dir": str(codebase_dir),
            "files_scanned": flow_result.file_count,
            "external_services": services_list,
            "data_flows": flows_list,
            "ropa_entries": len(ropa.entries),
            "mermaid_diagram": mermaid_src,
        }

        return json.dumps({
            "summary": summary,
            "full_report": full_report,
        }, indent=2, default=str)

    except Exception as e:
        return f"Error analyzing data flows: {e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Tool 5: aitrace_requirements — list regulatory requirements
# ---------------------------------------------------------------------------

@mcp.tool()
def aitrace_requirements(regulation: str | None = None) -> str:
    """List regulatory requirements from the AI Trace Auditor knowledge base.

    Returns requirements from the EU AI Act and NIST AI RMF with their IDs,
    descriptions, severities, and evidence fields.

    Args:
        regulation: Optional filter by regulation name (e.g., "EU AI Act", "NIST AI RMF").

    Returns:
        List of requirements with IDs, titles, descriptions, and severities.
    """
    try:
        from ai_trace_auditor.regulations.registry import RequirementRegistry

        registry = RequirementRegistry()
        registry.load()

        requirements = registry.get_all()

        if regulation:
            requirements = [r for r in requirements if r.regulation == regulation]

        if not requirements:
            available = registry.regulations
            return json.dumps({
                "error": f"No requirements found for regulation: {regulation}",
                "available_regulations": available,
            }, indent=2)

        result = {
            "total": len(requirements),
            "regulations": list({r.regulation for r in requirements}),
            "requirements": [
                {
                    "id": r.id,
                    "regulation": r.regulation,
                    "article": r.article,
                    "title": r.title,
                    "description": r.description,
                    "severity": r.severity,
                    "evidence_field_count": len(r.evidence_fields),
                    "applies_to": r.applies_to,
                }
                for r in requirements
            ],
        }

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        return f"Error listing requirements: {e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
