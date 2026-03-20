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
    def test_generates_scope_check_plus_9_sections(self):
        doc = generate_annex_iv(_minimal_scan())
        assert len(doc.sections) == 10  # scope check (0) + 9 annex IV sections

    def test_sections_numbered_0_through_9(self):
        doc = generate_annex_iv(_minimal_scan())
        numbers = [s.section_number for s in doc.sections]
        assert numbers == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    def test_scope_check_is_first_section(self):
        doc = generate_annex_iv(_minimal_scan())
        assert doc.sections[0].section_number == 0
        assert "scope" in doc.sections[0].title.lower()

    def test_scope_check_mentions_annex_iii(self):
        doc = generate_annex_iv(_minimal_scan())
        assert "Annex III" in doc.sections[0].content

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
        assert doc.completion_pct < 100

    def test_completion_pct_with_ai_scan(self):
        doc = generate_annex_iv(_scan_with_ai())
        assert doc.completion_pct > 0

    def test_sections_7_and_8_always_manual(self):
        """Sections 7 and 8 (index 7 and 8, since scope check is index 0)."""
        doc = generate_annex_iv(_scan_with_ai(), _mock_gap_report())
        # Find by section number, not index
        section_7 = next(s for s in doc.sections if s.section_number == 7)
        section_8 = next(s for s in doc.sections if s.section_number == 8)
        assert not section_7.auto_populated
        assert not section_8.auto_populated
        assert section_7.confidence == "manual"
        assert section_8.confidence == "manual"

    def test_sections_3_6_9_enriched_with_traces(self):
        doc = generate_annex_iv(_scan_with_ai(), _mock_gap_report())
        section_3 = next(s for s in doc.sections if s.section_number == 3)
        section_6 = next(s for s in doc.sections if s.section_number == 6)
        section_9 = next(s for s in doc.sections if s.section_number == 9)
        assert section_3.auto_populated is True
        assert section_6.auto_populated is True
        assert section_9.auto_populated is True

    def test_retention_guidance_in_section_9(self):
        doc = generate_annex_iv(_minimal_scan())
        section_9 = next(s for s in doc.sections if s.section_number == 9)
        assert "10 years" in section_9.content
        assert "6 months" in section_9.content
        assert "Article 18" in section_9.content
