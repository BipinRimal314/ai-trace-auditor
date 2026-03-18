"""Tests for the Annex IV Markdown report renderer."""

from pathlib import Path
from datetime import datetime, timezone

from ai_trace_auditor.docs.assembler import generate_annex_iv
from ai_trace_auditor.models.docs import AIImport, CodeScanResult, ModelReference
from ai_trace_auditor.models.gap import GapReport, GapSummary
from ai_trace_auditor.reports.docs_report import DocsReporter
from ai_trace_auditor.scanner.scan import scan_codebase

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


def _full_scan() -> CodeScanResult:
    return scan_codebase(FIXTURES)


class TestDocsReporter:
    def test_renders_without_error(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        reporter = DocsReporter()
        md = reporter.render(doc)
        assert isinstance(md, str)
        assert len(md) > 100

    def test_contains_annex_iv_header(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        assert "Annex IV" in md

    def test_contains_all_9_section_headers(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        for i in range(1, 10):
            assert f"## Section {i}:" in md

    def test_contains_manual_flags(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        assert "[MANUAL INPUT REQUIRED]" in md

    def test_contains_detected_providers(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        assert "anthropic" in md
        assert "openai" in md

    def test_contains_detected_models(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        assert "claude-3-opus-20240229" in md

    def test_contains_completeness_table(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        assert "Documentation Completeness" in md
        assert "Auto" in md

    def test_contains_next_steps(self):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        md = DocsReporter().render(doc)
        assert "Next Steps" in md

    def test_write_creates_file(self, tmp_path: Path):
        scan = _full_scan()
        doc = generate_annex_iv(scan)
        reporter = DocsReporter()
        output = tmp_path / "annex_iv.md"
        reporter.write(doc, output)
        assert output.exists()
        content = output.read_text()
        assert "Annex IV" in content

    def test_enriched_doc_shows_compliance(self):
        scan = _full_scan()
        gap_report = GapReport(
            generated_at=datetime.now(timezone.utc),
            trace_source="test.json",
            trace_count=2,
            span_count=40,
            regulations_checked=["EU AI Act"],
            overall_score=0.85,
            requirement_results=[],
            summary=GapSummary(
                satisfied=7, partial=2, missing=1, not_applicable=0,
                top_gaps=["Missing: error classification"],
            ),
        )
        doc = generate_annex_iv(scan, gap_report)
        md = DocsReporter().render(doc)
        assert "85.0%" in md
        assert "error classification" in md
