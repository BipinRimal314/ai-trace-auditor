"""Raw API log (JSONL) parser.

Handles simple JSON-lines format where each line is a request/response pair:
{"timestamp": "...", "provider": "openai", "model": "gpt-4", "request": {...}, "response": {...}}
"""

from __future__ import annotations

import uuid
from typing import Any

from ai_trace_auditor.ingest.otel import _iso_to_datetime, _safe_float, _safe_int
from ai_trace_auditor.models.trace import NormalizedSpan, NormalizedTrace


def _parse_log_entry(entry: dict[str, Any]) -> NormalizedSpan:
    """Parse a single API log entry into a NormalizedSpan."""
    response = entry.get("response", {})
    request = entry.get("request", {})
    usage = entry.get("tokens", response.get("usage", {}))

    # Try to extract model from multiple locations
    model = entry.get("model") or request.get("model") or response.get("model")
    provider = entry.get("provider")

    # Parse error
    error_type = None
    error_message = None
    error = entry.get("error") or response.get("error")
    if error:
        if isinstance(error, dict):
            error_type = error.get("type", "api_error")
            error_message = error.get("message", str(error))
        else:
            error_type = "api_error"
            error_message = str(error)

    # Parse finish reason
    finish_reasons = None
    choices = response.get("choices", [])
    if choices:
        reasons = [c.get("finish_reason") for c in choices if c.get("finish_reason")]
        if reasons:
            finish_reasons = reasons

    return NormalizedSpan(
        span_id=entry.get("id") or response.get("id") or uuid.uuid4().hex[:16],
        operation=entry.get("operation", "chat"),
        provider=provider,
        model_requested=request.get("model") or model,
        model_used=response.get("model") or model,
        start_time=_iso_to_datetime(entry.get("timestamp")),
        end_time=_iso_to_datetime(entry.get("end_timestamp")),
        duration_ms=_safe_float(entry.get("latency_ms") or entry.get("duration_ms")),
        input_tokens=_safe_int(usage.get("input", usage.get("prompt_tokens"))),
        output_tokens=_safe_int(usage.get("output", usage.get("completion_tokens"))),
        total_tokens=_safe_int(usage.get("total", usage.get("total_tokens"))),
        temperature=_safe_float(request.get("temperature")),
        max_tokens=_safe_int(request.get("max_tokens")),
        response_id=response.get("id"),
        finish_reasons=finish_reasons,
        input_messages=request.get("messages"),
        error_type=error_type,
        error_message=error_message,
        raw_attributes=entry,
    )


class RawAPIIngestor:
    """Parses raw API log entries (list of request/response dicts)."""

    def can_parse(self, data: dict[str, Any] | list[Any]) -> bool:
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            return isinstance(first, dict) and (
                "request" in first or "response" in first or "provider" in first
            )
        return False

    def parse(self, data: dict[str, Any] | list[Any]) -> list[NormalizedTrace]:
        if isinstance(data, dict):
            entries = [data]
        elif isinstance(data, list):
            entries = [e for e in data if isinstance(e, dict)]
        else:
            return []

        # Each log entry becomes its own trace (no grouping info available)
        return [
            NormalizedTrace(
                trace_id=entry.get("trace_id") or uuid.uuid4().hex[:16],
                spans=[_parse_log_entry(entry)],
                source_format="raw_api",
            )
            for entry in entries
        ]
