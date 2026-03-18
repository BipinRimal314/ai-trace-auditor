"""Tests for the Annex IV document assembler."""

from datetime import datetime, timezone

from ai_trace_auditor.docs.assembler import generate_annex_iv
from ai_trace_auditor.models.docs import AnnexIVDocument, CodeScanResult, AIImport
from ai_trace_auditor.models.gap import GapReport, GapSummary


def _minimal_scan() -> CodeScanResult:
    return CodeScanResult(scanned_dir="/test", file_count=5, scan_duration_ms=50)


def _scan_with_ai() -> CodeScanResult:
    return CodeScanResult(
        scanned_dir="/test/project",
        file_count=10,
        scan_duration_ms=80,
        ai_imports=[
            AIImport(library="anthropic", module_path="anthropic", file_path="app.py", line_number=1),
        ],
    )


def _mock_gap_report() -> GapReport:
    return GapReport(
        generated_at=datetime.now(timezone.utc),
        trace_source="traces.json",
        trace_count=3,
        span_count=50,
        regulations_checked=["EU AI Act"],
        overall_score=0.75,
        requirement_results=[],
        summary=GapSummary(
            satisfied=6, partial=2, missing=2, not_applicable=1, top_gaps=[],
        ),
    )


class TestGenerateAnnexIV:
    def test_generates_exactly_9_sections(self):
        doc = generate_annex_iv(_minimal_scan())
        assert len(doc.sections) == 9

    def test_sections_numbered_1_through_9(self):
        doc = generate_annex_iv(_minimal_scan())
        numbers = [s.section_number for s in doc.sections]
        assert numbers == [1, 2, 3, 4, 5, 6, 7, 8, 9]

    def test_returns_annex_iv_document(self):
        doc = generate_annex_iv(_minimal_scan())
        assert isinstance(doc, AnnexIVDocument)

    def test_source_dir_matches_scan(self):
        doc = generate_annex_iv(_minimal_scan())
        assert doc.source_dir == "/test"

    def test_has_generated_timestamp(self):
        doc = generate_annex_iv(_minimal_scan())
        assert doc.generated_at is not None
        assert doc.generated_at.tzinfo is not None

    def test_trace_enriched_false_without_gap_report(self):
        doc = generate_annex_iv(_minimal_scan())
        assert doc.trace_enriched is False

    def test_trace_enriched_true_with_gap_report(self):
        doc = generate_annex_iv(_minimal_scan(), _mock_gap_report())
        assert doc.trace_enriched is True

    def test_completion_pct_with_empty_scan(self):
        doc = generate_annex_iv(_minimal_scan())
        # Empty scan: most sections are manual
        assert doc.completion_pct < 100

    def test_completion_pct_with_ai_scan(self):
        doc = generate_annex_iv(_scan_with_ai())
        # AI imports populate sections 1, 2, 5
        assert doc.completion_pct > 0

    def test_sections_7_and_8_always_manual(self):
        doc = generate_annex_iv(_scan_with_ai(), _mock_gap_report())
        section_7 = doc.sections[6]
        section_8 = doc.sections[7]
        assert not section_7.auto_populated
        assert not section_8.auto_populated
        assert section_7.confidence == "manual"
        assert section_8.confidence == "manual"

    def test_sections_3_6_9_enriched_with_traces(self):
        doc = generate_annex_iv(_scan_with_ai(), _mock_gap_report())
        section_3 = doc.sections[2]
        section_6 = doc.sections[5]
        section_9 = doc.sections[8]
        assert section_3.auto_populated is True
        assert section_6.auto_populated is True
        assert section_9.auto_populated is True
