"""OpenTelemetry OTLP JSON trace parser.

Handles two formats:
1. OTLP export: {"resourceSpans": [{"scopeSpans": [{"spans": [...]}]}]}
2. Flat span list: [{"name": "...", "attributes": {...}, ...}]

Extracts gen_ai.* attributes per the OTel GenAI Semantic Conventions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ai_trace_auditor.models.trace import (
    NormalizedSpan,
    NormalizedTrace,
    ToolCall,
)

# OTel timestamps are nanoseconds since epoch
NANOS_PER_SECOND = 1_000_000_000
NANOS_PER_MS = 1_000_000


def _nano_to_datetime(nanos: int | str | None) -> datetime | None:
    if nanos is None:
        return None
    nanos = int(nanos)
    return datetime.fromtimestamp(nanos / NANOS_PER_SECOND, tz=timezone.utc)


def _iso_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a timestamp that could be nanoseconds (int) or ISO string."""
    if value is None:
        return None
    if isinstance(value, int):
        return _nano_to_datetime(value)
    if isinstance(value, str):
        if value.isdigit():
            return _nano_to_datetime(int(value))
        return _iso_to_datetime(value)
    return None


def _attrs_to_dict(attributes: list[dict[str, Any]] | dict[str, Any] | None) -> dict[str, Any]:
    """Convert OTel attribute formats to a flat dict.

    OTel OTLP uses: [{"key": "k", "value": {"stringValue": "v"}}]
    Some exports use: {"key": "value"} directly.
    """
    if attributes is None:
        return {}
    if isinstance(attributes, dict):
        return attributes

    result: dict[str, Any] = {}
    for attr in attributes:
        key = attr.get("key", "")
        value_obj = attr.get("value", {})
        if isinstance(value_obj, dict):
            # OTel value types: stringValue, intValue, doubleValue, boolValue, arrayValue
            for vtype in ("stringValue", "intValue", "doubleValue", "boolValue"):
                if vtype in value_obj:
                    result[key] = value_obj[vtype]
                    break
            if "arrayValue" in value_obj:
                values = value_obj["arrayValue"].get("values", [])
                result[key] = [
                    v.get("stringValue", v.get("intValue", v.get("doubleValue", v)))
                    for v in values
                ]
        else:
            result[key] = value_obj
    return result


def _extract_events(events: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Extract gen_ai content from span events."""
    if not events:
        return {}

    result: dict[str, Any] = {}
    for event in events:
        event_attrs = _attrs_to_dict(event.get("attributes", {}))
        # Merge gen_ai event attributes into result
        for key, value in event_attrs.items():
            if key.startswith("gen_ai."):
                result[key] = value
    return result


def _detect_framework(attrs: dict[str, Any]) -> str | None:
    """Detect the agent framework from span attributes."""
    for key in attrs:
        if "langgraph" in key.lower() or "langchain" in key.lower():
            return "langgraph"
        if "crewai" in key.lower():
            return "crewai"
        if "autogen" in key.lower():
            return "autogen"
        if "google.adk" in key.lower():
            return "adk"
    # Check explicit framework attribute
    framework = attrs.get("gen_ai.agent.framework")
    if framework:
        return str(framework).lower()
    # Arize/OpenInference graph attributes suggest LangGraph
    if "graph.node.id" in attrs:
        return "langgraph"
    return None


def _classify_span_kind(attrs: dict[str, Any]) -> str | None:
    """Classify the span kind from operation and attributes."""
    op = str(attrs.get("gen_ai.operation.name", "")).lower()

    if op in ("chat", "text_completion", "embeddings"):
        return "llm_generation"
    if op == "tool_call" or attrs.get("gen_ai.tool.name"):
        return "tool_call"
    if attrs.get("gen_ai.agent.id") or op == "agent":
        return "agent_handoff"

    # Memory operations
    for key in attrs:
        k = key.lower()
        if "memory" in k and "read" in k:
            return "memory_read"
        if "memory" in k and "write" in k:
            return "memory_write"

    return None


def _parse_tool_calls(attrs: dict[str, Any]) -> list[ToolCall] | None:
    """Parse tool call information from attributes."""
    tool_name = attrs.get("gen_ai.tool.name")
    tool_call_id = attrs.get("gen_ai.tool.call.id")

    if not tool_name and not tool_call_id:
        return None

    return [
        ToolCall(
            id=tool_call_id,
            name=tool_name or "unknown",
            type=attrs.get("gen_ai.tool.type"),
        )
    ]


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_messages(value: Any) -> list[dict[str, Any]] | None:
    """Parse message arrays that may contain JSON strings or dicts."""
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            try:
                import json

                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    result.append(parsed)
            except (json.JSONDecodeError, ValueError):
                result.append({"content": item})
    return result if result else None


def _parse_span(span: dict[str, Any]) -> NormalizedSpan:
    """Parse a single OTel span into a NormalizedSpan."""
    attrs = _attrs_to_dict(span.get("attributes", {}))
    event_attrs = _extract_events(span.get("events", []))

    # Merge event attributes (content is typically in events, not span attributes)
    all_attrs = {**attrs, **event_attrs}

    start_time = _parse_timestamp(span.get("startTimeUnixNano") or span.get("start_time"))
    end_time = _parse_timestamp(span.get("endTimeUnixNano") or span.get("end_time"))

    duration_ms = None
    if start_time and end_time:
        duration_ms = (end_time - start_time).total_seconds() * 1000

    # Parse finish reasons (can be string or list)
    finish_reasons = all_attrs.get("gen_ai.response.finish_reasons")
    if isinstance(finish_reasons, str):
        finish_reasons = [finish_reasons]

    # Parse stop sequences
    stop_sequences = all_attrs.get("gen_ai.request.stop_sequences")
    if isinstance(stop_sequences, str):
        stop_sequences = [stop_sequences]

    # Parse messages (OTel stores these as JSON strings inside arrays)
    input_messages = _parse_messages(all_attrs.get("gen_ai.input.messages"))
    output_messages = _parse_messages(all_attrs.get("gen_ai.output.messages"))
    system_instructions = _parse_messages(all_attrs.get("gen_ai.system_instructions"))

    # Error info from OTel status
    status = span.get("status", {})
    error_type = None
    error_message = None
    if status.get("code") == 2 or status.get("statusCode") == "ERROR":
        error_type = "otel_error"
        error_message = status.get("message", "Unknown error")
    # Also check span attributes for error info
    if attrs.get("error.type"):
        error_type = str(attrs["error.type"])
        error_message = str(attrs.get("error.message", attrs.get("exception.message", "")))

    return NormalizedSpan(
        span_id=span.get("spanId") or span.get("span_id") or uuid.uuid4().hex[:16],
        parent_span_id=span.get("parentSpanId") or span.get("parent_span_id") or None,
        operation=all_attrs.get("gen_ai.operation.name", "unknown"),
        provider=all_attrs.get("gen_ai.provider.name") or all_attrs.get("gen_ai.system"),
        model_requested=all_attrs.get("gen_ai.request.model"),
        model_used=all_attrs.get("gen_ai.response.model"),
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
        input_tokens=_safe_int(all_attrs.get("gen_ai.usage.input_tokens")),
        output_tokens=_safe_int(all_attrs.get("gen_ai.usage.output_tokens")),
        total_tokens=_safe_int(all_attrs.get("gen_ai.usage.total_tokens")),
        temperature=_safe_float(all_attrs.get("gen_ai.request.temperature")),
        top_p=_safe_float(all_attrs.get("gen_ai.request.top_p")),
        max_tokens=_safe_int(all_attrs.get("gen_ai.request.max_tokens")),
        seed=_safe_int(all_attrs.get("gen_ai.request.seed")),
        stop_sequences=stop_sequences,
        frequency_penalty=_safe_float(all_attrs.get("gen_ai.request.frequency_penalty")),
        presence_penalty=_safe_float(all_attrs.get("gen_ai.request.presence_penalty")),
        response_id=all_attrs.get("gen_ai.response.id"),
        finish_reasons=finish_reasons,
        input_messages=input_messages if isinstance(input_messages, list) else None,
        output_messages=output_messages if isinstance(output_messages, list) else None,
        system_instructions=system_instructions if isinstance(system_instructions, list) else None,
        tool_calls=_parse_tool_calls(all_attrs),
        error_type=error_type,
        error_message=error_message,
        raw_attributes=all_attrs,
        # Multi-agent identity
        agent_id=all_attrs.get("gen_ai.agent.id") or all_attrs.get("graph.node.id"),
        agent_name=all_attrs.get("gen_ai.agent.name"),
        agent_framework=_detect_framework(all_attrs),
        span_kind=_classify_span_kind(all_attrs),
        tool_name=all_attrs.get("gen_ai.tool.name"),
        mcp_server_uri=all_attrs.get("gen_ai.mcp.server_uri") or all_attrs.get("mcp.server.uri"),
    )


class OTelIngestor:
    """Parses OpenTelemetry OTLP JSON exports into NormalizedTraces."""

    def can_parse(self, data: dict[str, Any] | list[Any]) -> bool:
        if isinstance(data, dict):
            return "resourceSpans" in data
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            return isinstance(first, dict) and (
                "attributes" in first
                and any(
                    isinstance(a, dict) and str(a.get("key", "")).startswith("gen_ai.")
                    for a in (first.get("attributes") or [])
                    if isinstance(a, dict)
                )
                or isinstance(first.get("attributes"), dict)
                and any(k.startswith("gen_ai.") for k in first["attributes"])
            )
        return False

    def parse(self, data: dict[str, Any] | list[Any]) -> list[NormalizedTrace]:
        raw_spans = self._extract_spans(data)
        if not raw_spans:
            return []

        # Extract session_id from resource attributes
        session_id = self._extract_session_id(data)

        # Group spans by trace_id
        traces_by_id: dict[str, list[dict[str, Any]]] = {}
        for span in raw_spans:
            trace_id = span.get("traceId") or span.get("trace_id") or "unknown"
            # Handle OTel context wrapper
            if isinstance(trace_id, dict):
                trace_id = trace_id.get("trace_id", "unknown")
            traces_by_id.setdefault(str(trace_id), []).append(span)

        return [
            NormalizedTrace(
                trace_id=trace_id,
                spans=[_parse_span(s) for s in spans],
                source_format="otel",
                session_id=session_id,
            )
            for trace_id, spans in traces_by_id.items()
        ]

    def _extract_spans(self, data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        """Extract raw span dicts from either OTLP or flat format."""
        if isinstance(data, list):
            return data

        spans: list[dict[str, Any]] = []
        for resource_span in data.get("resourceSpans", []):
            for scope_span in resource_span.get("scopeSpans", []):
                spans.extend(scope_span.get("spans", []))
        return spans

    def _extract_session_id(self, data: dict[str, Any] | list[Any]) -> str | None:
        """Extract session.id from resource-level attributes."""
        if not isinstance(data, dict):
            return None
        for resource_span in data.get("resourceSpans", []):
            resource = resource_span.get("resource", {})
            attrs = _attrs_to_dict(resource.get("attributes", {}))
            session_id = attrs.get("session.id")
            if session_id:
                return str(session_id)
        return None
