"""End-to-end repo audit on checked-in fixture repos.

Does not use the fetcher (no real cloning); points trace_finder + scan_docs
at the fixture path directly.
"""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.manifest_loader import load_manifest
from ai_trace_auditor.repo.report import combine_repo_report
from ai_trace_auditor.repo.trace_finder import find_trace_artifacts

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"
MANIFEST = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "ai_trace_auditor"
    / "repo"
    / "manifest.yaml"
)


def _status_counts(results):
    counts = {"present": 0, "absent": 0, "partial": 0}
    for r in results:
        counts[r.status] += 1
    return counts


def test_repo_with_traces_finds_artifacts_and_docs():
    repo = FIXTURES / "repo_with_traces"
    checks = load_manifest(MANIFEST)

    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    assert len(artifacts) >= 1
    assert any(a.shape == "chat_jsonl" for a in artifacts)

    counts = _status_counts(doc_results)
    # README, model card, intended-purpose phrase, retention key — at least 4 present
    assert counts["present"] >= 4


def test_repo_docs_only_finds_no_traces_but_docs():
    repo = FIXTURES / "repo_docs_only"
    checks = load_manifest(MANIFEST)

    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    assert artifacts == []
    counts = _status_counts(doc_results)
    # README + AI policy + code of conduct
    assert counts["present"] >= 3


def test_repo_bare_yields_mostly_absent_with_no_crash():
    repo = FIXTURES / "repo_bare"
    checks = load_manifest(MANIFEST)

    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    assert artifacts == []
    counts = _status_counts(doc_results)
    assert counts["absent"] >= len(checks) - 3  # README counts as present


def test_combine_repo_report_without_traces():
    repo = FIXTURES / "repo_bare"
    checks = load_manifest(MANIFEST)
    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    report = combine_repo_report(
        repo_url="https://github.com/test/bare",
        trace_artifacts=artifacts,
        trace_report=None,
        doc_results=doc_results,
    )

    assert report.trace_artifacts_found == 0
    assert report.trace_report is None
    assert len(report.doc_results) == len(checks)


def test_registry_still_loads_unchanged():
    """Smoke test: existing regulation YAMLs still load."""
    registry = RequirementRegistry()
    registry.load()
    assert registry.count > 0
