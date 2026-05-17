"""Evaluate governance-doc detectors against a cloned repository."""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.repo.models import DocCheck, DocCheckResult


def _normalize(s: str) -> str:
    return s.lower().rstrip("/")


def _detect_file_presence(repo_path: Path, patterns: list[str]) -> Path | None:
    """Return the first matching path, or None.

    A pattern with a trailing ``/`` matches a directory; otherwise matches a file.
    Match is case-insensitive on the relative path from ``repo_path``.
    """
    targets = {_normalize(p): p.endswith("/") for p in patterns}

    for path in repo_path.rglob("*"):
        rel = _normalize(str(path.relative_to(repo_path)))
        for target, expect_dir in targets.items():
            if rel == target:
                if expect_dir and path.is_dir():
                    return path
                if not expect_dir and path.is_file():
                    return path
    return None


def _evaluate(check: DocCheck, repo_path: Path) -> DocCheckResult:
    if check.detector_kind == "file_presence":
        patterns = check.detector_config.get("patterns", [])
        matched = _detect_file_presence(repo_path, patterns)
        if matched is not None:
            rel = matched.relative_to(repo_path)
            evidence = check.evidence_when_present.format(path=str(rel))
            return DocCheckResult(
                check=check, status="present", evidence=evidence, matched_path=matched
            )
        return DocCheckResult(
            check=check,
            status="absent",
            evidence=check.evidence_when_absent,
            matched_path=None,
        )

    raise NotImplementedError(f"Detector kind not yet supported: {check.detector_kind}")


def scan_docs(repo_path: Path, checks: list[DocCheck]) -> list[DocCheckResult]:
    """Evaluate every check against the repo and return the results in order."""
    return [_evaluate(c, repo_path) for c in checks]
