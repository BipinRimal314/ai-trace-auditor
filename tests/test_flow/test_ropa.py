"""Tests for GDPR Article 30 RoPA generation."""

from pathlib import Path

from ai_trace_auditor.flow.detector import detect_flows
from ai_trace_auditor.flow.ropa import generate_ropa
from ai_trace_auditor.scanner.scan import scan_codebase

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


class TestRoPAGeneration:
    def _get_flow_result(self):
        code_scan = scan_codebase(FIXTURES)
        return detect_flows(FIXTURES, code_scan)

    def test_generates_ropa_report(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        assert len(ropa.entries) > 0

    def test_ropa_has_timestamp(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        assert ropa.generated_at is not None

    def test_entries_have_processing_activity(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        for entry in ropa.entries:
            assert entry.processing_activity
            assert len(entry.processing_activity) > 10

    def test_entries_have_purpose(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        for entry in ropa.entries:
            assert entry.purpose

    def test_entries_have_data_categories(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        for entry in ropa.entries:
            assert entry.data_categories

    def test_entries_have_recipients(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        recipients = [e.recipients for e in ropa.entries]
        assert any("Anthropic" in r for r in recipients)

    def test_retention_is_manual(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        for entry in ropa.entries:
            assert "MANUAL" in entry.retention

    def test_controller_fields_are_manual(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        assert "MANUAL" in ropa.controller_name
        assert "MANUAL" in ropa.dpo_contact

    def test_inference_activity_description(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        activities = [e.processing_activity for e in ropa.entries]
        assert any("inference" in a.lower() for a in activities)

    def test_no_duplicate_entries(self):
        result = self._get_flow_result()
        ropa = generate_ropa(result)
        activities = [e.processing_activity for e in ropa.entries]
        assert len(activities) == len(set(activities))
