"""Combine trace audit + doc checklist into a RepoAuditReport."""

from __future__ import annotations

from ai_trace_auditor.models.gap import GapReport
from ai_trace_auditor.repo.models import (
    DocCheckResult,
    RepoAuditReport,
    TraceArtifact,
)


def combine_repo_report(
    *,
    repo_url: str,
    trace_artifacts: list[TraceArtifact],
    trace_report: GapReport | None,
    doc_results: list[DocCheckResult],
) -> RepoAuditReport:
    """Assemble a RepoAuditReport from scanner outputs."""
    return RepoAuditReport(
        repo_url=repo_url,
        trace_artifacts_found=len(trace_artifacts),
        trace_report=trace_report,
        doc_results=doc_results,
    )
