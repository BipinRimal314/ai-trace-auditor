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


def _detect_content_contains(
    repo_path: Path,
    file_patterns: list[str],
    phrases: list[str],
) -> tuple[Path | None, bool]:
    """Return (matched_file_path, contained_a_phrase).

    Walks the repo once and finds the first file whose relative path matches
    any of ``file_patterns`` (case-insensitive). Returns the file's path and
    whether any phrase from ``phrases`` was present in its contents.
    Returns (None, False) if no file matched.
    """
    file_targets = {_normalize(p) for p in file_patterns}
    phrases_lower = [p.lower() for p in phrases]

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        rel = _normalize(str(path.relative_to(repo_path)))
        if rel not in file_targets:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            return path, False
        for phrase in phrases_lower:
            if phrase in text:
                return path, True
        return path, False

    return None, False


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

    if check.detector_kind == "content_contains":
        file_patterns = check.detector_config.get("file_patterns", [])
        phrases = check.detector_config.get("phrases", [])
        matched, has_phrase = _detect_content_contains(
            repo_path, file_patterns, phrases
        )
        if matched is None:
            return DocCheckResult(
                check=check,
                status="absent",
                evidence=check.evidence_when_absent,
                matched_path=None,
            )
        rel = matched.relative_to(repo_path)
        if has_phrase:
            return DocCheckResult(
                check=check,
                status="present",
                evidence=check.evidence_when_present.format(path=str(rel)),
                matched_path=matched,
            )
        return DocCheckResult(
            check=check,
            status="partial",
            evidence=(
                f"File {rel} exists but contains no required phrase. "
                f"{check.evidence_when_absent}"
            ),
            matched_path=matched,
        )

    raise NotImplementedError(f"Detector kind not yet supported: {check.detector_kind}")


def scan_docs(repo_path: Path, checks: list[DocCheck]) -> list[DocCheckResult]:
    """Evaluate every check against the repo and return the results in order."""
    return [_evaluate(c, repo_path) for c in checks]
