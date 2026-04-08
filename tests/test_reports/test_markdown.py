"""Tests for Markdown report generation."""

from pathlib import Path

from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.ingest.detect import ingest_file
from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.reports.markdown import MarkdownReporter


def test_markdown_report_renders(otel_trace_path: Path, requirements_dir: Path) -> None:
    """Report renders without errors and contains expected sections."""
    traces = ingest_file(otel_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    report = ComplianceAnalyzer(registry).analyze(traces=traces, trace_source="test.json")
    md = MarkdownReporter().render(report)

    assert "# AI Trace Compliance Report" in md
    assert "Trace Field Coverage" in md
    assert "Requirement Details" in md
    assert "EU-AIA-" in md
    assert "Methodology" in md


def test_markdown_report_contains_gaps(otel_trace_path: Path, requirements_dir: Path) -> None:
    """Report should list gaps when they exist."""
    traces = ingest_file(otel_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    report = ComplianceAnalyzer(registry).analyze(traces=traces, trace_source="test.json")
    md = MarkdownReporter().render(report)

    # The report should contain gap information if there are any
    if report.summary.missing > 0 or report.summary.partial > 0:
        assert "Gaps:" in md or "Recommendation" in md
