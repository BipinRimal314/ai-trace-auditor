"""Tests for repo module dataclass models."""

from pathlib import Path

import pytest

from ai_trace_auditor.repo.models import (
    DocCheck,
    DocCheckResult,
    RepoAuditReport,
    TraceArtifact,
)


def test_trace_artifact_carries_path_and_shape():
    art = TraceArtifact(
        path=Path("/tmp/r/traces.jsonl"),
        shape="otel",
        size_bytes=2048,
    )
    assert art.path.name == "traces.jsonl"
    assert art.shape == "otel"
    assert art.size_bytes == 2048


def test_trace_artifact_rejects_unknown_shape():
    with pytest.raises(ValueError):
        TraceArtifact(path=Path("x"), shape="bogus", size_bytes=1)


def test_doc_check_requires_compliance_gate_fields():
    check = DocCheck(
        id="annex_iv_2b_model_card",
        legal_text="Annex IV(2)(b): a description of the elements of the AI system...",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Annex IV",
        detector_kind="file_presence",
        detector_config={"patterns": ["MODEL_CARD.md", "model_card.md"]},
        evidence_when_present="Model card found at {path}.",
        evidence_when_absent="No model card found.",
    )
    assert check.id == "annex_iv_2b_model_card"
    assert check.verified_against_primary is True


def test_doc_check_result_status_values():
    check = DocCheck(
        id="x",
        legal_text="x",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Annex IV",
        detector_kind="file_presence",
        detector_config={"patterns": ["X"]},
        evidence_when_present="p",
        evidence_when_absent="a",
    )
    for status in ("present", "absent", "partial"):
        result = DocCheckResult(check=check, status=status, evidence="x", matched_path=None)
        assert result.status == status

    with pytest.raises(ValueError):
        DocCheckResult(check=check, status="bogus", evidence="x", matched_path=None)


def test_repo_audit_report_assembles():
    report = RepoAuditReport(
        repo_url="https://github.com/x/y",
        trace_artifacts_found=0,
        trace_report=None,
        doc_results=[],
    )
    assert report.repo_url == "https://github.com/x/y"
    assert report.trace_report is None
    assert report.doc_results == []
