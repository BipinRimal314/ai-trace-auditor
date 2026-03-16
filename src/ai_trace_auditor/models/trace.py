"""Normalized trace model. All ingestion formats map to this single representation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A single tool/function call within a span."""

    id: str | None = None
    name: str
    type: str | None = None  # "function", "extension", "datastore"
    arguments: dict[str, Any] | None = None
    result: Any | None = None


class Evaluation(BaseModel):
    """An evaluation score attached to a span (e.g., from Langfuse)."""

    name: str
    score_value: float | None = None
    score_label: str | None = None
    explanation: str | None = None


class NormalizedSpan(BaseModel):
    """A single operation span, normalized from any trace format.

    Every field is optional except span_id and operation, because different
    trace formats and configurations capture different subsets of data.
    The gap analysis engine checks which fields are present vs. which
    regulations require.
    """

    span_id: str
    parent_span_id: str | None = None
    operation: str  # "chat", "embeddings", "text_completion", "tool_call", "agent"
    provider: str | None = None  # "openai", "anthropic", "google", etc.

    # Model identification
    model_requested: str | None = None
    model_used: str | None = None

    # Timing
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: float | None = None

    # Token usage
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    # Request parameters
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    seed: int | None = None
    stop_sequences: list[str] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None

    # Response metadata
    response_id: str | None = None
    finish_reasons: list[str] | None = None

    # Content (opt-in, may be absent for privacy)
    input_messages: list[dict[str, Any]] | None = None
    output_messages: list[dict[str, Any]] | None = None
    system_instructions: list[dict[str, Any]] | None = None

    # Tool usage
    tools_defined: list[dict[str, Any]] | None = None
    tool_calls: list[ToolCall] | None = None

    # Cost (provider-calculated, e.g., from Langfuse)
    input_cost: float | None = None
    output_cost: float | None = None
    total_cost: float | None = None

    # Error tracking
    error_type: str | None = None
    error_message: str | None = None

    # Evaluations (e.g., from Langfuse scores)
    evaluations: list[Evaluation] | None = None

    # Raw attributes for audit trail
    raw_attributes: dict[str, Any] = Field(default_factory=dict)


class NormalizedTrace(BaseModel):
    """A complete trace containing one or more spans.

    A trace represents a single logical operation (e.g., one user request)
    that may involve multiple LLM calls, tool invocations, and agent steps.
    """

    trace_id: str
    spans: list[NormalizedSpan]
    source_format: str  # "otel", "langfuse", "raw_api"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def span_count(self) -> int:
        return len(self.spans)

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens or 0 for s in self.spans)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens or 0 for s in self.spans)

    @property
    def providers(self) -> set[str]:
        return {s.provider for s in self.spans if s.provider}

    @property
    def models(self) -> set[str]:
        return {s.model_used or s.model_requested or "unknown" for s in self.spans}

    @property
    def earliest_time(self) -> datetime | None:
        times = [s.start_time for s in self.spans if s.start_time]
        return min(times) if times else None

    @property
    def latest_time(self) -> datetime | None:
        times = [s.end_time for s in self.spans if s.end_time]
        return max(times) if times else None
