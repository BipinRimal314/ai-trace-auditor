"""Tests for repo module exception hierarchy."""

import pytest

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoError,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)


def test_all_errors_inherit_from_repo_error():
    assert issubclass(InvalidRepoURL, RepoError)
    assert issubclass(RepoNotFound, RepoError)
    assert issubclass(PrivateRepo, RepoError)
    assert issubclass(RepoTooLarge, RepoError)
    assert issubclass(RepoFetchTimeout, RepoError)


def test_repo_too_large_carries_byte_count():
    err = RepoTooLarge(actual_bytes=100_000_000, limit_bytes=52_428_800)
    assert err.actual_bytes == 100_000_000
    assert err.limit_bytes == 52_428_800
    assert "100000000" in str(err) or "100 MB" in str(err) or "100,000,000" in str(err)


def test_repo_fetch_timeout_carries_seconds():
    err = RepoFetchTimeout(seconds=30)
    assert err.seconds == 30
    assert "30" in str(err)


def test_repo_error_can_be_raised_and_caught():
    with pytest.raises(RepoError):
        raise InvalidRepoURL("not a github url")
