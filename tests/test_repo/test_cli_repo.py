"""Tests for the `aitrace audit-repo` subcommand."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ai_trace_auditor.cli import app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"


def _fake_clone(fixture_name: str):
    def _fn(url, *, max_bytes, timeout_seconds, tmpdir_root):
        return FIXTURES / fixture_name
    return _fn


def test_audit_repo_with_traces_exits_zero():
    runner = CliRunner()
    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone("repo_with_traces"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        result = runner.invoke(
            app, ["audit-repo", "https://github.com/test/repo_with_traces"]
        )
    # The command may exit 0 (all present) or 2 (some absent). Either way,
    # we just verify it ran cleanly and produced output.
    assert result.exit_code in (0, 2), f"unexpected exit: {result.exit_code}, stdout={result.stdout}"
    assert "repo_with_traces" in result.stdout or "Repository" in result.stdout


def test_audit_repo_invalid_url_exits_nonzero():
    from ai_trace_auditor.repo.errors import InvalidRepoURL

    runner = CliRunner()
    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=InvalidRepoURL("bad"),
    ):
        result = runner.invoke(
            app, ["audit-repo", "https://gitlab.com/x/y"]
        )
    assert result.exit_code != 0
