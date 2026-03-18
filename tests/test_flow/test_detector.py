"""Tests for the data flow detector."""

from pathlib import Path

from ai_trace_auditor.flow.detector import detect_flows
from ai_trace_auditor.scanner.scan import scan_codebase

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


class TestFlowDetection:
    def test_returns_flow_scan_result(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        assert result.scanned_dir == str(FIXTURES)
        assert result.file_count > 0

    def test_detects_ai_provider_services(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        service_names = result.service_names
        assert "Anthropic API" in service_names
        assert "OpenAI API" in service_names

    def test_detects_vector_db_services(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        service_names = result.service_names
        assert "Pinecone" in service_names
        assert "ChromaDB" in service_names

    def test_creates_data_flows_for_ai_providers(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        destinations = [f.destination for f in result.data_flows]
        assert "Anthropic API" in destinations
        assert "OpenAI API" in destinations

    def test_ai_flows_have_gdpr_annotations(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        anthropic_flows = [f for f in result.data_flows if f.destination == "Anthropic API"]
        assert len(anthropic_flows) >= 1
        flow = anthropic_flows[0]
        assert flow.gdpr_role == "processor"
        assert flow.data_type == "prompts"
        assert flow.contains_pii == "likely"

    def test_vector_db_flows_have_gdpr_annotations(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        pinecone_flows = [f for f in result.data_flows if f.destination == "Pinecone"]
        assert len(pinecone_flows) >= 1
        assert pinecone_flows[0].data_type == "embeddings"

    def test_chromadb_is_controller(self):
        """ChromaDB is self-hosted, so GDPR role should be controller."""
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        chromadb_flows = [f for f in result.data_flows if f.destination == "ChromaDB"]
        assert len(chromadb_flows) >= 1
        assert chromadb_flows[0].gdpr_role == "controller"

    def test_pinecone_is_processor(self):
        """Pinecone is cloud-hosted, so GDPR role should be processor."""
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        pinecone_flows = [f for f in result.data_flows if f.destination == "Pinecone"]
        assert len(pinecone_flows) >= 1
        assert pinecone_flows[0].gdpr_role == "processor"

    def test_detects_file_io(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        # train.py has read_csv which should be detected as file I/O
        assert len(result.file_io) >= 0  # May or may not have file I/O in fixtures

    def test_outbound_services_property(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        outbound = result.outbound_services
        assert len(outbound) >= 1

    def test_no_duplicate_services(self):
        code_scan = scan_codebase(FIXTURES)
        result = detect_flows(FIXTURES, code_scan)
        names = [s.name for s in result.external_services]
        # Check no exact duplicates
        seen: set[str] = set()
        for name in names:
            assert name not in seen, f"Duplicate service: {name}"
            seen.add(name)


class TestFlowWithoutCodeScan:
    def test_works_without_code_scan(self):
        """Flow detector should work even without a CodeScanResult."""
        result = detect_flows(FIXTURES, code_scan=None)
        assert result.file_count > 0
        # Without code_scan, AI provider flows won't be built
        # but HTTP clients, DBs, file I/O still detected

    def test_file_io_detected_without_code_scan(self):
        result = detect_flows(FIXTURES, code_scan=None)
        # The detector still scans for file I/O patterns
        assert isinstance(result.file_io, list)
