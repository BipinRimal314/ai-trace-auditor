"""Typed exceptions for repository ingestion."""

from __future__ import annotations


class RepoError(Exception):
    """Base class for all repo-ingestion errors."""


class InvalidRepoURL(RepoError):
    """URL is not a recognized GitHub repository URL."""


class RepoNotFound(RepoError):
    """Repository does not exist or is not publicly accessible."""


class PrivateRepo(RepoError):
    """Repository exists but is private."""


class RepoTooLarge(RepoError):
    """Repository exceeds the configured size cap."""

    def __init__(self, actual_bytes: int, limit_bytes: int) -> None:
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"Repository size {actual_bytes:,} bytes exceeds limit "
            f"of {limit_bytes:,} bytes."
        )


class RepoFetchTimeout(RepoError):
    """Clone exceeded the configured timeout."""

    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        super().__init__(f"Clone exceeded {seconds} seconds.")
