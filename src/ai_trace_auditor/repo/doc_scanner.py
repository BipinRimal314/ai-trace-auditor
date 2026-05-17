"""Evaluate governance-doc detectors against a cloned repository."""

from __future__ import annotations

import re
from pathlib import Path

from ai_trace_auditor.repo.models import DocCheck, DocCheckResult

_KEY_LINE_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]", re.MULTILINE
)


def _normalize(s: str) -> str:
    return s.lower().rstrip("/")


def _detect_file_presence(repo_path: Path, patterns: list[str]) -> Path | None:
    """Return the first matching path, or None.

    Patterns are exact relative paths (case-insensitive), not globs.
    A trailing ``/`` requires a directory; otherwise a file.
    When multiple patterns could match, pattern-list order decides
    (the earlier the pattern, the higher its priority).
    """
    target_priority: dict[str, int] = {}
    target_expects_dir: dict[str, bool] = {}
    for i, p in enumerate(patterns):
        n = _normalize(p)
        if n not in target_priority:
            target_priority[n] = i
            target_expects_dir[n] = p.endswith("/")

    candidates: list[tuple[int, Path, bool]] = []
    for path in repo_path.rglob("*"):
        rel = _normalize(str(path.relative_to(repo_path)))
        if rel in target_priority:
            candidates.append(
                (target_priority[rel], path, target_expects_dir[rel])
            )

    candidates.sort(key=lambda t: t[0])
    for _, path, expect_dir in candidates:
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
    """Return (matched_file_path, contained_a_phrase) deterministically.

    When multiple file_patterns could match, pattern-list order decides.
    Returns (None, False) if no pattern matched any file.
    """
    target_priority: dict[str, int] = {}
    for i, p in enumerate(file_patterns):
        n = _normalize(p)
        if n not in target_priority:
            target_priority[n] = i
    phrases_lower = [p.lower() for p in phrases]

    candidates: list[tuple[int, Path]] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        rel = _normalize(str(path.relative_to(repo_path)))
        if rel in target_priority:
            candidates.append((target_priority[rel], path))

    candidates.sort(key=lambda t: t[0])
    for _, path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            return path, False
        for phrase in phrases_lower:
            if phrase in text:
                return path, True
        return path, False

    return None, False


def _detect_config_key(
    repo_path: Path,
    filenames: list[str],
    keys: list[str],
) -> tuple[Path | None, str | None]:
    """Return (matched_file_path, matched_key_name) deterministically."""
    target_priority: dict[str, int] = {}
    for i, f in enumerate(filenames):
        n = _normalize(f)
        if n not in target_priority:
            target_priority[n] = i
    keys_lower = {k.lower() for k in keys}

    candidates: list[tuple[int, Path]] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        rel = _normalize(str(path.relative_to(repo_path)))
        if rel in target_priority:
            candidates.append((target_priority[rel], path))

    candidates.sort(key=lambda t: t[0])
    for _, path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return path, None
        for match in _KEY_LINE_RE.finditer(text):
            key = match.group("key").lower()
            if key in keys_lower:
                return path, match.group("key")
        return path, None

    return None, None


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

    if check.detector_kind == "config_key":
        filenames = check.detector_config.get("filenames", [])
        keys = check.detector_config.get("keys", [])
        matched, matched_key = _detect_config_key(repo_path, filenames, keys)
        if matched is not None and matched_key is not None:
            rel = matched.relative_to(repo_path)
            return DocCheckResult(
                check=check,
                status="present",
                evidence=check.evidence_when_present.format(
                    path=str(rel), key=matched_key
                ),
                matched_path=matched,
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
