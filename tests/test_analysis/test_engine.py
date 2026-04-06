"""Integration tests for the compliance analysis engine."""

from pathlib import Path

from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.ingest.detect import ingest_file
from ai_trace_auditor.regulations.registry import RequirementRegistry


def test_full_audit_otel(otel_trace_path: Path, requirements_dir: Path) -> None:
    """End-to-end: ingest OTel traces, analyze against EU AI Act, get report."""
    traces = ingest_file(otel_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(
        traces=traces,
        regulations=["EU AI Act"],
        trace_source="test",
    )

    assert report.trace_count == 1
    assert report.span_count == 3
    assert "EU AI Act" in report.regulations_checked
    assert len(report.requirement_results) > 0
    assert 0.0 <= report.overall_score <= 1.0

    # Timestamps should be satisfied (all spans have them)
    timestamp_req = next(
        (r for r in report.requirement_results if r.requirement.id == "EU-AIA-12.1"),
        None,
    )
    assert timestamp_req is not None
    assert timestamp_req.status == "satisfied"


def test_full_audit_langfuse(langfuse_trace_path: Path, requirements_dir: Path) -> None:
    """End-to-end with Langfuse traces."""
    traces = ingest_file(langfuse_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(traces=traces, trace_source="test")

    assert report.trace_count == 1
    assert report.span_count == 3
    assert len(report.requirement_results) > 0


def test_audit_all_regulations(otel_trace_path: Path, requirements_dir: Path) -> None:
    """Audit against all loaded regulations."""
    traces = ingest_file(otel_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(traces=traces, trace_source="test")

    # Should check both EU AI Act and NIST
    assert len(report.regulations_checked) >= 2


def test_gap_report_has_recommendations(otel_trace_path: Path, requirements_dir: Path) -> None:
    """Gaps should include actionable recommendations."""
    traces = ingest_file(otel_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(traces=traces, trace_source="test")

    # Find any requirement with gaps
    results_with_gaps = [r for r in report.requirement_results if r.gaps]
    if results_with_gaps:
        gap = results_with_gaps[0].gaps[0]
        assert gap.description
        assert gap.impact
        assert gap.recommendation


def test_summary_counts(otel_trace_path: Path, requirements_dir: Path) -> None:
    """Summary counts should match individual results."""
    traces = ingest_file(otel_trace_path)
    registry = RequirementRegistry()
    registry.load(requirements_dir)

    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(traces=traces, trace_source="test")

    total = (
        report.summary.satisfied
        + report.summary.partial
        + report.summary.missing
        + report.summary.not_applicable
    )
    assert total == len(report.requirement_results)
