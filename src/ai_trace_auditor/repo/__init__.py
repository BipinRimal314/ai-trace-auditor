"""Repository ingestion: fetch + scan + combine."""

from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoError,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)
from ai_trace_auditor.repo.fetcher import clone_repo, parse_github_url
from ai_trace_auditor.repo.manifest_loader import load_manifest
from ai_trace_auditor.repo.models import (
    DocCheck,
    DocCheckResult,
    RepoAuditReport,
    TraceArtifact,
)
from ai_trace_auditor.repo.report import combine_repo_report
from ai_trace_auditor.repo.trace_finder import find_trace_artifacts

__all__ = [
    "DocCheck",
    "DocCheckResult",
    "InvalidRepoURL",
    "PrivateRepo",
    "RepoAuditReport",
    "RepoError",
    "RepoFetchTimeout",
    "RepoNotFound",
    "RepoTooLarge",
    "TraceArtifact",
    "clone_repo",
    "combine_repo_report",
    "find_trace_artifacts",
    "load_manifest",
    "parse_github_url",
    "scan_docs",
]
