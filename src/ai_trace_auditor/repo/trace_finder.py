"""Discover trace artifacts inside a cloned repository tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_trace_auditor.repo.models import TraceArtifact

_DEFAULT_MAX_FILE_BYTES = 5_000_000


def _classify_json(doc: Any) -> str | None:
    if isinstance(doc, dict):
        if "resourceSpans" in doc or "scopeSpans" in doc:
            return "otel"
        if "messages" in doc and isinstance(doc["messages"], list):
            return "chat_jsonl"
        if "observations" in doc and ("trace_id" in doc or "id" in doc):
            return "langfuse"
        return None

    if isinstance(doc, list) and doc and isinstance(doc[0], dict):
        first = doc[0]
        if "observations" in first:
            return "langfuse"
        if "resourceSpans" in first:
            return "otel"
        if "messages" in first and isinstance(first.get("messages"), list):
            return "chat_jsonl"

    return None


def _classify_jsonl(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    return None
                return _classify_json(doc)
    except OSError:
        return None
    return None


def _classify_json_file(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return _classify_json(doc)


def find_trace_artifacts(
    repo_path: Path,
    *,
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
) -> list[TraceArtifact]:
    """Walk ``repo_path`` and return discovered trace artifacts."""
    artifacts: list[TraceArtifact] = []

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".json", ".jsonl"):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            continue

        shape = (
            _classify_jsonl(path) if suffix == ".jsonl" else _classify_json_file(path)
        )
        if shape is None:
            continue

        artifacts.append(
            TraceArtifact(path=path, shape=shape, size_bytes=size)
        )

    return artifacts
