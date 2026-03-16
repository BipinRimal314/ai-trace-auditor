"""Tests for OTel OTLP JSON ingestion."""

from pathlib import Path

from ai_trace_auditor.ingest.otel import OTelIngestor


def test_can_parse_otlp_format(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    ingestor = OTelIngestor()
    assert ingestor.can_parse(data) is True


def test_parse_produces_traces(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    ingestor = OTelIngestor()
    traces = ingestor.parse(data)

    assert len(traces) == 1
    trace = traces[0]
    assert trace.trace_id == "abc123def456789012345678"
    assert trace.source_format == "otel"
    assert trace.span_count == 3


def test_span_attributes_parsed(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    traces = OTelIngestor().parse(data)
    span = traces[0].spans[0]

    assert span.operation == "chat"
    assert span.provider == "openai"
    assert span.model_requested == "gpt-4o"
    assert span.model_used == "gpt-4o-2024-08-06"
    assert span.response_id == "chatcmpl-abc123"
    assert span.temperature == 0.7
    assert span.max_tokens == 1000
    assert span.input_tokens == 150
    assert span.output_tokens == 200
    assert span.finish_reasons == ["stop"]


def test_timestamps_parsed(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    traces = OTelIngestor().parse(data)
    span = traces[0].spans[0]

    assert span.start_time is not None
    assert span.end_time is not None
    assert span.duration_ms is not None
    assert span.duration_ms == 2500.0


def test_tool_call_span(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    traces = OTelIngestor().parse(data)
    tool_span = traces[0].spans[1]

    assert tool_span.operation == "tool_call"
    assert tool_span.parent_span_id == "span001"
    assert tool_span.tool_calls is not None
    assert tool_span.tool_calls[0].name == "web_search"


def test_trace_properties(otel_trace_path: Path) -> None:
    import json

    data = json.loads(otel_trace_path.read_text())
    traces = OTelIngestor().parse(data)
    trace = traces[0]

    assert trace.total_input_tokens == 500  # 150 + 350
    assert trace.total_output_tokens == 380  # 200 + 180
    assert "openai" in trace.providers
    assert trace.earliest_time is not None
    assert trace.latest_time is not None


def test_cannot_parse_non_otel() -> None:
    ingestor = OTelIngestor()
    assert ingestor.can_parse({"observations": []}) is False
    assert ingestor.can_parse({"data": []}) is False
