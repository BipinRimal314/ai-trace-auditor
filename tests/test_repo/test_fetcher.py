"""Tests for repo fetcher.

Uses subprocess mocking so tests never hit the network. The fetcher's
contract: clone shallowly into a tmpdir, enforce size + timeout caps,
strip .git, raise typed errors. The contract is what we test, not the
exact subprocess flags.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)
from ai_trace_auditor.repo.fetcher import clone_repo, parse_github_url


def test_parse_github_url_accepts_https():
    assert parse_github_url("https://github.com/owner/repo") == ("owner", "repo")
    assert parse_github_url("https://github.com/owner/repo.git") == ("owner", "repo")
    assert parse_github_url("https://github.com/owner/repo/") == ("owner", "repo")


def test_parse_github_url_rejects_non_github():
    with pytest.raises(InvalidRepoURL):
        parse_github_url("https://gitlab.com/owner/repo")


def test_parse_github_url_rejects_malformed():
    with pytest.raises(InvalidRepoURL):
        parse_github_url("not a url at all")


def test_parse_github_url_rejects_missing_repo():
    with pytest.raises(InvalidRepoURL):
        parse_github_url("https://github.com/owner")


def _make_repo_contents(target: Path, file_count: int = 2, byte_size: int = 100) -> None:
    """Helper: populate a directory as if `git clone` had written to it."""
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir(exist_ok=True)
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    for i in range(file_count):
        (target / f"file_{i}.txt").write_text("x" * byte_size)


def test_clone_happy_path(tmp_path: Path):
    """Successful clone returns a populated path with .git stripped."""

    def fake_run(cmd, *args, **kwargs):
        target = Path(cmd[-1])
        _make_repo_contents(target)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        result_path = clone_repo(
            "https://github.com/owner/repo",
            max_bytes=10_000,
            timeout_seconds=30,
            tmpdir_root=tmp_path,
        )

    assert result_path.is_dir()
    assert not (result_path / ".git").exists()
    assert (result_path / "file_0.txt").exists()

    shutil.rmtree(result_path)


def test_clone_raises_repo_not_found_on_128():
    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 128, "", "fatal: repository 'https://github.com/x/y' not found"
        )

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(RepoNotFound):
            clone_repo(
                "https://github.com/x/y",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )


def test_clone_raises_private_repo_on_auth_required():
    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 128, "", "fatal: Authentication failed"
        )

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(PrivateRepo):
            clone_repo(
                "https://github.com/x/y",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )


def test_clone_raises_timeout():
    def fake_run(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 30))

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(RepoFetchTimeout):
            clone_repo(
                "https://github.com/owner/repo",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )


def test_clone_raises_too_large_when_repo_exceeds_cap(tmp_path: Path):
    def fake_run(cmd, *args, **kwargs):
        target = Path(cmd[-1])
        _make_repo_contents(target, file_count=3, byte_size=600)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(RepoTooLarge):
            clone_repo(
                "https://github.com/owner/repo",
                max_bytes=1_500,
                timeout_seconds=30,
                tmpdir_root=tmp_path,
            )

    leftovers = list(tmp_path.glob("aitrace-repo-*"))
    assert leftovers == []


def test_clone_invalid_url_never_invokes_subprocess():
    mock_run = MagicMock()
    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", mock_run):
        with pytest.raises(InvalidRepoURL):
            clone_repo(
                "https://gitlab.com/x/y",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )
    mock_run.assert_not_called()
