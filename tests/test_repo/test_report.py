"""Tests for combining trace audit + doc checklist into RepoAuditReport."""

from pathlib import Path
from unittest.mock import MagicMock

from ai_trace_auditor.repo.models import DocCheck, DocCheckResult
from ai_trace_auditor.repo.report import combine_repo_report


def _make_doc_result(status: str) -> DocCheckResult:
    check = DocCheck(
        id="id",
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
    return DocCheckResult(check=check, status=status, evidence="x", matched_path=None)


def test_no_traces_produces_doc_only_report():
    docs = [_make_doc_result("present"), _make_doc_result("absent")]

    report = combine_repo_report(
        repo_url="https://github.com/x/y",
        trace_artifacts=[],
        trace_report=None,
        doc_results=docs,
    )

    assert report.repo_url == "https://github.com/x/y"
    assert report.trace_artifacts_found == 0
    assert report.trace_report is None
    assert len(report.doc_results) == 2


def test_with_traces_attaches_gap_report():
    trace_report = MagicMock()
    artifacts = [MagicMock(), MagicMock()]
    docs = [_make_doc_result("present")]

    report = combine_repo_report(
        repo_url="https://github.com/x/y",
        trace_artifacts=artifacts,
        trace_report=trace_report,
        doc_results=docs,
    )

    assert report.trace_artifacts_found == 2
    assert report.trace_report is trace_report
