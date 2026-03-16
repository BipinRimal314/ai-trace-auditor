"""Tests for auto-format detection and file ingestion."""

from pathlib import Path

from ai_trace_auditor.ingest.detect import detect_format, ingest_file


def test_detect_otel_format(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    assert detect_format(data) == "otel"


def test_detect_langfuse_format(langfuse_trace_path: Path) -> None:
    import json

    data = json.loads(langfuse_trace_path.read_text())
    assert detect_format(data) == "langfuse"


def test_ingest_otel_file(otel_trace_path: Path) -> None:
    traces = ingest_file(otel_trace_path)
    assert len(traces) == 1
    assert traces[0].source_format == "otel"


def test_ingest_langfuse_file(langfuse_trace_path: Path) -> None:
    traces = ingest_file(langfuse_trace_path)
    assert len(traces) == 1
    assert traces[0].source_format == "langfuse"


def test_ingest_raw_api_file(raw_api_path: Path) -> None:
    traces = ingest_file(raw_api_path)
    assert len(traces) == 3  # One trace per JSONL line
    assert traces[0].source_format == "raw_api"


def test_ingest_with_format_hint(otel_trace_path: Path) -> None:
    traces = ingest_file(otel_trace_path, format_hint="otel")
    assert len(traces) == 1
