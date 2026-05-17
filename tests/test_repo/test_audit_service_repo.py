"""Tests for the web orchestrator that combines fetcher + finder + scanner + audit."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.web.audit_service import audit_repo

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"


def _fake_clone_returning(fixture_name: str):
    """Build a clone_repo replacement that returns a path to a checked-in fixture."""

    def _fake(url, *, max_bytes, timeout_seconds, tmpdir_root):
        return FIXTURES / fixture_name

    return _fake


def test_audit_repo_with_traces_and_docs(tmp_path: Path):
    registry = RequirementRegistry()
    registry.load()

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone_returning("repo_with_traces"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        report = audit_repo(
            repo_url="https://github.com/test/repo_with_traces",
            registry=registry,
            tmpdir_root=tmp_path,
        )

    assert report.repo_url == "https://github.com/test/repo_with_traces"
    assert report.trace_artifacts_found >= 1
    assert any(r.status == "present" for r in report.doc_results)


def test_audit_repo_docs_only_skips_trace_audit(tmp_path: Path):
    registry = RequirementRegistry()
    registry.load()

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone_returning("repo_docs_only"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        report = audit_repo(
            repo_url="https://github.com/test/repo_docs_only",
            registry=registry,
            tmpdir_root=tmp_path,
        )

    assert report.trace_artifacts_found == 0
    assert report.trace_report is None
    assert len(report.doc_results) > 0


def test_audit_repo_cleans_up_on_exception(tmp_path: Path):
    """If clone fails before producing a directory, no cleanup is attempted."""
    from ai_trace_auditor.repo.errors import RepoNotFound

    cleanup_calls = []

    def fake_clone(*args, **kwargs):
        raise RepoNotFound("404 from github")

    def fake_cleanup(path):
        cleanup_calls.append(path)

    registry = RequirementRegistry()
    registry.load()

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo", side_effect=fake_clone
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir",
        side_effect=fake_cleanup,
    ):
        try:
            audit_repo(
                repo_url="https://github.com/x/y",
                registry=registry,
                tmpdir_root=tmp_path,
            )
        except RepoNotFound:
            pass
    assert cleanup_calls == []
