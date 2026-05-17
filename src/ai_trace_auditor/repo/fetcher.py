"""Repository fetcher: shallow clone with size + timeout caps."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)

_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) for a valid public GitHub repo URL."""
    match = _GITHUB_URL_RE.match(url.strip())
    if not match:
        raise InvalidRepoURL(
            f"Not a valid GitHub repo URL: {url!r}. "
            "Expected https://github.com/owner/repo."
        )
    return match.group("owner"), match.group("repo")


def _directory_size_bytes(path: Path) -> int:
    """Recursive size of files in a directory."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _classify_clone_failure(returncode: int, stderr: str) -> Exception:
    text = stderr.lower()
    if "not found" in text or "could not read from remote" in text:
        return RepoNotFound(stderr.strip())
    if "authentication failed" in text or "permission denied" in text:
        return PrivateRepo(stderr.strip())
    return RepoNotFound(stderr.strip() or f"git clone failed (exit {returncode})")


def clone_repo(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
    tmpdir_root: Path,
) -> Path:
    """Shallow-clone ``url`` under ``tmpdir_root``, enforce caps, strip .git.

    Returns the path to the cloned working tree. Caller owns cleanup.

    Raises one of: InvalidRepoURL, RepoNotFound, PrivateRepo, RepoTooLarge,
    RepoFetchTimeout.
    """
    parse_github_url(url)  # raises InvalidRepoURL if bad

    tmpdir_root.mkdir(parents=True, exist_ok=True)
    target = tmpdir_root / f"aitrace-repo-{uuid.uuid4().hex}"

    cmd = ["git", "clone", "--depth=1", "--single-branch", url, str(target)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise RepoFetchTimeout(seconds=timeout_seconds) from exc

    if result.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise _classify_clone_failure(result.returncode, result.stderr)

    try:
        size = _directory_size_bytes(target)
        if size > max_bytes:
            raise RepoTooLarge(actual_bytes=size, limit_bytes=max_bytes)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise

    git_dir = target / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, ignore_errors=True)

    return target
