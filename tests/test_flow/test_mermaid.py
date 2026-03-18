"""Tests for Mermaid diagram generation."""

from pathlib import Path

from ai_trace_auditor.flow.detector import detect_flows
from ai_trace_auditor.flow.mermaid import generate_mermaid
from ai_trace_auditor.scanner.scan import scan_codebase

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


class TestMermaidGeneration:
    def _get_flow_result(self):
        code_scan = scan_codebase(FIXTURES)
        return detect_flows(FIXTURES, code_scan)

    def test_generates_valid_mermaid(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert mermaid.startswith("graph LR")

    def test_contains_user_and_app_nodes(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "USER((User))" in mermaid
        assert "APP[Application]" in mermaid

    def test_contains_ai_provider_nodes(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "Anthropic_API" in mermaid
        assert "OpenAI_API" in mermaid

    def test_contains_vector_db_nodes_as_cylinders(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        # Cylinders use [( )] syntax
        assert "Pinecone" in mermaid
        assert "ChromaDB" in mermaid

    def test_contains_flow_edges(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "APP -->" in mermaid
        assert "prompts" in mermaid

    def test_contains_bidirectional_flows_for_inference(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "responses" in mermaid

    def test_contains_style_classes(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "classDef controller" in mermaid
        assert "classDef processor" in mermaid

    def test_applies_gdpr_classes(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "class Anthropic_API processor" in mermaid
        assert "class ChromaDB controller" in mermaid

    def test_user_input_flow(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "USER -->|user input| APP" in mermaid

    def test_pii_annotation(self):
        result = self._get_flow_result()
        mermaid = generate_mermaid(result)
        assert "PII likely" in mermaid
