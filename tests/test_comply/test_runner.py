"""Tests for the unified compliance runner."""

from pathlib import Path

import pytest

from ai_trace_auditor.comply.runner import CompliancePackage, run_full_compliance

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_CODEBASE = FIXTURES / "sample_codebase"


class TestRunFullCompliance:
    def test_returns_compliance_package(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert isinstance(pkg, CompliancePackage)

    def test_has_generated_timestamp(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.generated_at is not None
        assert pkg.generated_at.tzinfo is not None

    def test_source_dir_matches(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.source_dir == str(SAMPLE_CODEBASE)

    def test_code_scan_populated(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.code_scan is not None
        assert pkg.code_scan.file_count > 0
        assert pkg.code_scan.has_ai_usage is True

    def test_annex_iv_generated(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.annex_iv is not None
        assert len(pkg.annex_iv.sections) == 9

    def test_flow_scan_populated(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.flow_scan is not None
        assert len(pkg.flow_scan.external_services) > 0

    def test_flow_diagram_generated(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.flow_diagram is not None
        assert pkg.flow_diagram.mermaid.startswith("graph LR")

    def test_ropa_generated(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.ropa is not None
        assert len(pkg.ropa.entries) > 0

    def test_articles_covered_without_traces(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert "Article 11 (Technical Documentation)" in pkg.articles_covered
        assert "Article 13 (Transparency)" in pkg.articles_covered
        assert "GDPR Article 30 (RoPA)" in pkg.articles_covered
        # No Article 12 without traces
        assert "Article 12 (Record-Keeping)" not in pkg.articles_covered

    def test_no_gap_report_without_traces(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.gap_report is None

    def test_compliance_score_none_without_traces(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.compliance_score is None

    def test_docs_completion_pct(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.docs_completion_pct > 0
        assert pkg.docs_completion_pct <= 100

    def test_service_count(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.service_count > 0

    def test_flow_count(self):
        pkg = run_full_compliance(SAMPLE_CODEBASE)
        assert pkg.flow_count > 0


class TestComplianceWithTraces:
    def test_article_12_with_otel_traces(self):
        trace_path = FIXTURES / "otel_chat_trace.json"
        if not trace_path.exists():
            pytest.skip("OTel trace fixture not available")
        pkg = run_full_compliance(SAMPLE_CODEBASE, trace_path=trace_path)
        assert pkg.gap_report is not None
        assert "Article 12 (Record-Keeping)" in pkg.articles_covered
        assert pkg.compliance_score is not None

    def test_annex_iv_enriched_with_traces(self):
        trace_path = FIXTURES / "otel_chat_trace.json"
        if not trace_path.exists():
            pytest.skip("OTel trace fixture not available")
        pkg = run_full_compliance(SAMPLE_CODEBASE, trace_path=trace_path)
        assert pkg.annex_iv.trace_enriched is True


class TestComplianceEdgeCases:
    def test_empty_codebase(self, tmp_path: Path):
        """Running on an empty directory should not crash."""
        pkg = run_full_compliance(tmp_path)
        assert pkg.code_scan.file_count == 0
        assert not pkg.code_scan.has_ai_usage
        assert len(pkg.warnings) > 0

    def test_no_ai_usage_produces_warning(self, tmp_path: Path):
        # Create a non-AI Python file
        (tmp_path / "hello.py").write_text("print('hello')")
        pkg = run_full_compliance(tmp_path)
        assert any("No AI framework usage" in w for w in pkg.warnings)
