"""Langfuse JSON export parser.

Handles Langfuse trace exports with observations (GENERATION, SPAN, EVENT types).
"""

from __future__ import annotations

from typing import Any

from ai_trace_auditor.ingest.otel import _iso_to_datetime, _safe_float, _safe_int
from ai_trace_auditor.models.trace import (
    Evaluation,
    NormalizedSpan,
    NormalizedTrace,
    ToolCall,
)


def _parse_observation(obs: dict[str, Any]) -> NormalizedSpan:
    """Parse a Langfuse observation into a NormalizedSpan."""
    obs_type = obs.get("type", "SPAN").upper()

    # Map Langfuse type to operation
    operation = "unknown"
    if obs_type == "GENERATION":
        operation = "chat"
    elif obs_type == "SPAN":
        operation = "agent"
    elif obs_type == "EVENT":
        operation = "event"

    # Parse model name to extract provider
    model_name = obs.get("providedModelName") or obs.get("model")
    provider = None
    if model_name:
        lower = model_name.lower()
        if "gpt" in lower or "o1" in lower or "o3" in lower:
            provider = "openai"
        elif "claude" in lower:
            provider = "anthropic"
        elif "gemini" in lower:
            provider = "google"

    # Parse tool calls from output if present
    tool_calls = None
    output = obs.get("output")
    if isinstance(output, dict) and "tool_calls" in output:
        tool_calls = [
            ToolCall(
                id=tc.get("id"),
                name=tc.get("function", {}).get("name", tc.get("name", "unknown")),
                type="function",
                arguments=tc.get("function", {}).get("arguments"),
            )
            for tc in output["tool_calls"]
        ]

    # Parse evaluations/scores
    evaluations = None
    scores = obs.get("scores")
    if scores and isinstance(scores, list):
        evaluations = [
            Evaluation(
                name=s.get("name", "unnamed"),
                score_value=_safe_float(s.get("value")),
                score_label=s.get("label"),
                explanation=s.get("comment"),
            )
            for s in scores
        ]

    start = _iso_to_datetime(obs.get("startTime"))
    end = _iso_to_datetime(obs.get("endTime") or obs.get("completionStartTime"))
    duration_ms = None
    if obs.get("latency") is not None:
        duration_ms = float(obs["latency"]) * 1000
    elif start and end:
        duration_ms = (end - start).total_seconds() * 1000

    # Multi-agent identity from metadata
    meta = obs.get("metadata") or {}
    agent_id = meta.get("agent_id")
    agent_name = meta.get("agent_name") or (obs.get("name") if obs_type == "SPAN" else None)
    agent_framework = meta.get("framework")

    # Span kind from Langfuse type
    span_kind = None
    if obs_type == "GENERATION":
        span_kind = "llm_generation"
    elif obs_type == "SPAN":
        name_lower = (obs.get("name") or "").lower()
        if any(kw in name_lower for kw in ("handoff", "delegate", "route")):
            span_kind = "agent_handoff"

    return NormalizedSpan(
        span_id=obs.get("id", "unknown"),
        parent_span_id=obs.get("parentObservationId"),
        operation=operation,
        provider=provider,
        model_requested=model_name,
        model_used=obs.get("internalModel") or model_name,
        start_time=start,
        end_time=end,
        duration_ms=duration_ms,
        input_tokens=_safe_int(obs.get("inputTokens") or obs.get("promptTokens")),
        output_tokens=_safe_int(obs.get("outputTokens") or obs.get("completionTokens")),
        total_tokens=_safe_int(obs.get("totalTokens")),
        input_cost=_safe_float(obs.get("inputCost")),
        output_cost=_safe_float(obs.get("outputCost")),
        total_cost=_safe_float(obs.get("totalCost")),
        input_messages=[obs["input"]] if obs.get("input") else None,
        output_messages=[obs["output"]] if obs.get("output") else None,
        tool_calls=tool_calls,
        evaluations=evaluations,
        error_type="error" if obs.get("level") == "ERROR" else None,
        error_message=obs.get("statusMessage"),
        raw_attributes={
            k: v
            for k, v in obs.items()
            if k
            not in {
                "id",
                "traceId",
                "type",
                "startTime",
                "endTime",
                "input",
                "output",
                "inputTokens",
                "outputTokens",
                "totalTokens",
            }
        },
        agent_id=agent_id,
        agent_name=agent_name,
        agent_framework=agent_framework,
        span_kind=span_kind,
    )


class LangfuseIngestor:
    """Parses Langfuse JSON exports into NormalizedTraces."""

    def can_parse(self, data: dict[str, Any] | list[Any]) -> bool:
        if isinstance(data, dict):
            return "observations" in data or (
                "id" in data and "traceId" not in data and "spans" not in data
            )
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            return isinstance(first, dict) and "observations" in first
        return False

    def parse(self, data: dict[str, Any] | list[Any]) -> list[NormalizedTrace]:
        traces_raw: list[dict[str, Any]] = []

        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                traces_raw = data["data"]
            else:
                traces_raw = [data]
        elif isinstance(data, list):
            traces_raw = data

        results: list[NormalizedTrace] = []
        for trace_data in traces_raw:
            observations = trace_data.get("observations", [])
            if not observations:
                continue

            spans = [_parse_observation(obs) for obs in observations]
            trace_id = trace_data.get("id") or trace_data.get("traceId") or "unknown"

            metadata: dict[str, Any] = {}
            for key in ("name", "userId", "sessionId", "tags", "version", "release"):
                if trace_data.get(key) is not None:
                    metadata[key] = trace_data[key]

            results.append(
                NormalizedTrace(
                    trace_id=str(trace_id),
                    spans=spans,
                    source_format="langfuse",
                    metadata=metadata,
                    session_id=trace_data.get("sessionId"),
                )
            )

        return results
