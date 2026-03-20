"""Tests for Annex IV section builders."""

from datetime import datetime, timezone

import pytest

from ai_trace_auditor.docs.sections import (
    MANUAL,
    build_section_1,
    build_section_2,
    build_section_3,
    build_section_4,
    build_section_5,
    build_section_6,
    build_section_7,
    build_section_8,
    build_section_9,
)
from ai_trace_auditor.models.docs import (
    AIEndpoint,
    AIImport,
    CodeScanResult,
    EvalScriptRef,
    ModelReference,
    VectorDBUsage,
)
from ai_trace_auditor.models.gap import GapReport, GapSummary


def _empty_scan() -> CodeScanResult:
    return CodeScanResult(scanned_dir="/test", file_count=0, scan_duration_ms=0)


def _rich_scan() -> CodeScanResult:
    return CodeScanResult(
        scanned_dir="/test/project",
        file_count=15,
        scan_duration_ms=100,
        ai_imports=[
            AIImport(library="anthropic", module_path="anthropic", file_path="app.py", line_number=1),
            AIImport(library="openai", module_path="openai", file_path="app.py", line_number=2),
        ],
        model_references=[
            ModelReference(model_id="claude-3-opus-20240229", file_path="app.py", line_number=10, context='MODEL = "claude-3-opus-20240229"'),
            ModelReference(model_id="gpt-4o", file_path="chat.py", line_number=5, context='model="gpt-4o"'),
        ],
        vector_dbs=[
            VectorDBUsage(db_name="pinecone", module_path="pinecone", file_path="rag.py", line_number=3),
        ],
        eval_scripts=[
            EvalScriptRef(file_path="test_eval.py", metrics_detected=["accuracy_score", "f1_score"]),
        ],
        ai_endpoints=[
            AIEndpoint(framework="fastapi", route="/api/chat", file_path="app.py", line_number=20),
        ],
    )


def _mock_gap_report() -> GapReport:
    return GapReport(
        generated_at=datetime.now(timezone.utc),
        trace_source="test_traces.json",
        trace_count=5,
        span_count=100,
        regulations_checked=["EU AI Act"],
        overall_score=0.82,
        requirement_results=[],
        summary=GapSummary(
            satisfied=8,
            partial=3,
            missing=1,
            not_applicable=0,
            top_gaps=["Not logging: Temperature parameter"],
        ),
    )


class TestSection1:
    def test_empty_scan_has_manual_flags(self):
        section = build_section_1(_empty_scan())
        assert MANUAL in section.content
        assert not section.auto_populated
        assert section.confidence == "manual"

    def test_rich_scan_auto_populates(self):
        section = build_section_1(_rich_scan())
        assert section.auto_populated is True
        assert section.confidence == "medium"

    def test_shows_providers(self):
        section = build_section_1(_rich_scan())
        assert "anthropic" in section.content
        assert "openai" in section.content

    def test_shows_models(self):
        section = build_section_1(_rich_scan())
        assert "claude-3-opus-20240229" in section.content
        assert "gpt-4o" in section.content

    def test_shows_vector_dbs(self):
        section = build_section_1(_rich_scan())
        assert "pinecone" in section.content

    def test_shows_endpoints(self):
        section = build_section_1(_rich_scan())
        assert "/api/chat" in section.content

    def test_always_includes_manual_sections(self):
        section = build_section_1(_rich_scan())
        assert "Intended Purpose" in section.content
        assert MANUAL in section.content

    def test_section_number(self):
        section = build_section_1(_empty_scan())
        assert section.section_number == 1


class TestSection2:
    def test_shows_software_components(self):
        section = build_section_2(_rich_scan())
        assert "anthropic" in section.content
        assert "openai" in section.content
        assert section.auto_populated is True

    def test_shows_model_table(self):
        section = build_section_2(_rich_scan())
        assert "claude-3-opus-20240229" in section.content
        assert "app.py" in section.content

    def test_empty_scan_is_manual(self):
        section = build_section_2(_empty_scan())
        assert not section.auto_populated


class TestSection3:
    def test_without_traces_is_manual(self):
        section = build_section_3(_rich_scan())
        assert "Human Oversight" in section.content

    def test_with_traces_shows_compliance(self):
        section = build_section_3(_rich_scan(), _mock_gap_report())
        assert section.auto_populated is True
        assert "Requirements satisfied" in section.content
        assert "Temperature" in section.content

    def test_shows_deployment_configs(self):
        from ai_trace_auditor.models.docs import DeploymentConfig
        scan = _rich_scan()
        scan.deployment_configs = [
            DeploymentConfig(config_type="dockerfile", file_path="Dockerfile", contains_ai_deps=True),
        ]
        section = build_section_3(scan)
        assert "dockerfile" in section.content


class TestSection4:
    def test_shows_eval_metrics(self):
        section = build_section_4(_rich_scan())
        assert "accuracy_score" in section.content
        assert "f1_score" in section.content
        assert section.auto_populated is True

    def test_empty_scan_is_manual(self):
        section = build_section_4(_empty_scan())
        assert not section.auto_populated


class TestSection5:
    def test_shows_risk_surfaces(self):
        section = build_section_5(_rich_scan())
        assert "Third-party API dependency" in section.content
        assert section.auto_populated is True

    def test_shows_vector_db_risk(self):
        section = build_section_5(_rich_scan())
        assert "Vector databases" in section.content or "Data persistence" in section.content

    def test_empty_scan_is_manual(self):
        section = build_section_5(_empty_scan())
        assert not section.auto_populated


class TestSection6:
    def test_without_traces_is_manual(self):
        section = build_section_6(_rich_scan())
        assert not section.auto_populated

    def test_with_traces_shows_data(self):
        section = build_section_6(_rich_scan(), _mock_gap_report())
        assert section.auto_populated is True
        assert "100" in section.content  # span_count


class TestSection7:
    def test_always_manual(self):
        section = build_section_7(_rich_scan())
        assert not section.auto_populated
        assert section.confidence == "manual"
        assert "ISO/IEC 42001" in section.content


class TestSection8:
    def test_always_manual(self):
        section = build_section_8(_rich_scan())
        assert not section.auto_populated
        assert section.confidence == "manual"
        assert "Provider name" in section.content


class TestSection9:
    def test_without_traces_is_manual(self):
        section = build_section_9(_rich_scan())
        assert not section.auto_populated

    def test_with_traces_shows_monitoring(self):
        section = build_section_9(_rich_scan(), _mock_gap_report())
        assert section.auto_populated is True
        assert "Requirements satisfied" in section.content

    def test_retention_guidance(self):
        section = build_section_9(_rich_scan())
        assert "10 years" in section.content
        assert "Article 18" in section.content
        assert "Article 26(6)" in section.content
