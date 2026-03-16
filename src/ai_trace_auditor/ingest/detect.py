"""Auto-detect trace format and ingest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_trace_auditor.ingest.claude_code import ClaudeCodeIngestor
from ai_trace_auditor.ingest.langfuse import LangfuseIngestor
from ai_trace_auditor.ingest.otel import OTelIngestor
from ai_trace_auditor.ingest.raw_api import RawAPIIngestor
from ai_trace_auditor.models.trace import NormalizedTrace

INGESTORS = [OTelIngestor(), LangfuseIngestor(), ClaudeCodeIngestor(), RawAPIIngestor()]


def detect_format(data: dict[str, Any] | list[Any]) -> str:
    """Detect the trace format of parsed JSON data."""
    for ingestor in INGESTORS:
        if ingestor.can_parse(data):
            return ingestor.__class__.__name__.replace("Ingestor", "").lower()
    return "unknown"


def parse_data(
    data: dict[str, Any] | list[Any], format_hint: str = "auto"
) -> list[NormalizedTrace]:
    """Parse trace data using the specified or auto-detected format."""
    if format_hint != "auto":
        format_map = {
            "otel": OTelIngestor,
            "langfuse": LangfuseIngestor,
            "claude_code": ClaudeCodeIngestor,
            "raw": RawAPIIngestor,
        }
        ingestor_cls = format_map.get(format_hint)
        if ingestor_cls is None:
            raise ValueError(f"Unknown format: {format_hint}. Use: {', '.join(format_map)}")
        return ingestor_cls().parse(data)

    for ingestor in INGESTORS:
        if ingestor.can_parse(data):
            return ingestor.parse(data)

    raise ValueError(
        "Could not detect trace format. Supported: OTel OTLP JSON, Langfuse export, Claude Code, raw API JSONL. "
        "Use --format to specify explicitly."
    )


def _load_file(path: Path) -> dict[str, Any] | list[Any]:
    """Load a JSON or JSONL file."""
    text = path.read_text(encoding="utf-8")

    # Try JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try JSONL (one JSON object per line)
    entries: list[Any] = []
    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON at line {line_num}: {e}") from e

    if entries:
        return entries

    raise ValueError(f"Could not parse {path} as JSON or JSONL")


def ingest_file(path: Path, format_hint: str = "auto") -> list[NormalizedTrace]:
    """Load and parse a trace file.

    Args:
        path: Path to a JSON or JSONL trace file.
        format_hint: "auto", "otel", "langfuse", or "raw".

    Returns:
        List of normalized traces.
    """
    data = _load_file(path)
    return parse_data(data, format_hint)


def ingest_directory(directory: Path, format_hint: str = "auto") -> list[NormalizedTrace]:
    """Load and parse all trace files in a directory.

    Searches for .json and .jsonl files.
    """
    traces: list[NormalizedTrace] = []
    for ext in ("*.json", "*.jsonl"):
        for path in sorted(directory.glob(ext)):
            traces.extend(ingest_file(path, format_hint))
    return traces
