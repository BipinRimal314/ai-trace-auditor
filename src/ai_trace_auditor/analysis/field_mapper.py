"""Resolve field path strings against normalized trace data.

Field paths use dot notation with [] for arrays:
  "spans[].start_time"     -> check start_time across all spans
  "spans[].tool_calls"     -> check if tool_calls is non-null/non-empty
  "spans[].model_used"     -> check model_used across all spans
  "metadata.user_id"       -> check trace-level metadata
"""

from __future__ import annotations

from typing import Any

from ai_trace_auditor.models.evidence import EvidenceRecord
from ai_trace_auditor.models.requirement import EvidenceField
from ai_trace_auditor.models.trace import NormalizedTrace

MAX_SAMPLE_VALUES = 5


def _get_field_value(obj: Any, field_name: str) -> Any:
    """Get a field value from a Pydantic model or dict."""
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


def _is_present(value: Any, check_type: str) -> bool:
    """Check if a value satisfies the given check type."""
    if check_type == "present":
        # Field exists in the model (always true for Pydantic models with defaults)
        return True

    if check_type == "non_null":
        return value is not None

    if check_type == "non_empty":
        if value is None:
            return False
        if isinstance(value, (list, dict, str)):
            return len(value) > 0
        return True

    # Default: non-null check
    return value is not None


def resolve_field(
    traces: list[NormalizedTrace],
    evidence_field: EvidenceField,
) -> EvidenceRecord:
    """Resolve a field path against traces and compute coverage statistics.

    Returns an EvidenceRecord with how many spans had the field populated
    and sample values.
    """
    path = evidence_field.field_path
    check_type = evidence_field.check_type
    parts = path.split(".")

    # Handle spans[].field_name pattern (most common)
    if parts[0] == "spans[]" and len(parts) == 2:
        field_name = parts[1]
        return _check_span_field(traces, field_name, check_type, path)

    # Handle spans[].nested.field pattern
    if parts[0] == "spans[]" and len(parts) > 2:
        return _check_nested_span_field(traces, parts[1:], check_type, path)

    # Handle metadata.field pattern
    if parts[0] == "metadata" and len(parts) == 2:
        return _check_metadata_field(traces, parts[1], check_type, path)

    # Handle trace-level fields
    if len(parts) == 1:
        return _check_trace_field(traces, parts[0], check_type, path)

    return EvidenceRecord(field_path=path, population=0, present_count=0, coverage_pct=0.0)


def _check_span_field(
    traces: list[NormalizedTrace],
    field_name: str,
    check_type: str,
    path: str,
) -> EvidenceRecord:
    """Check a field across all spans in all traces."""
    population = 0
    present_count = 0
    sample_values: list[Any] = []

    for trace in traces:
        for span in trace.spans:
            population += 1
            value = _get_field_value(span, field_name)
            if _is_present(value, check_type):
                present_count += 1
                if len(sample_values) < MAX_SAMPLE_VALUES and value is not None:
                    # Truncate long values for readability
                    sample = _truncate(value)
                    if sample not in sample_values:
                        sample_values.append(sample)

    coverage = present_count / population if population > 0 else 0.0

    return EvidenceRecord(
        field_path=path,
        sample_values=sample_values,
        population=population,
        present_count=present_count,
        coverage_pct=coverage,
    )


def _check_nested_span_field(
    traces: list[NormalizedTrace],
    parts: list[str],
    check_type: str,
    path: str,
) -> EvidenceRecord:
    """Check a nested field in span attributes (e.g., raw_attributes.some.key)."""
    population = 0
    present_count = 0
    sample_values: list[Any] = []

    for trace in traces:
        for span in trace.spans:
            population += 1
            obj: Any = span
            for part in parts:
                obj = _get_field_value(obj, part)
                if obj is None:
                    break
            if _is_present(obj, check_type):
                present_count += 1
                if len(sample_values) < MAX_SAMPLE_VALUES and obj is not None:
                    sample_values.append(_truncate(obj))

    coverage = present_count / population if population > 0 else 0.0
    return EvidenceRecord(
        field_path=path,
        sample_values=sample_values,
        population=population,
        present_count=present_count,
        coverage_pct=coverage,
    )


def _check_metadata_field(
    traces: list[NormalizedTrace],
    field_name: str,
    check_type: str,
    path: str,
) -> EvidenceRecord:
    """Check a metadata field across all traces."""
    population = len(traces)
    present_count = 0
    sample_values: list[Any] = []

    for trace in traces:
        value = trace.metadata.get(field_name)
        if _is_present(value, check_type):
            present_count += 1
            if len(sample_values) < MAX_SAMPLE_VALUES and value is not None:
                sample_values.append(_truncate(value))

    coverage = present_count / population if population > 0 else 0.0
    return EvidenceRecord(
        field_path=path,
        sample_values=sample_values,
        population=population,
        present_count=present_count,
        coverage_pct=coverage,
    )


def _check_trace_field(
    traces: list[NormalizedTrace],
    field_name: str,
    check_type: str,
    path: str,
) -> EvidenceRecord:
    """Check a trace-level field."""
    population = len(traces)
    present_count = 0
    sample_values: list[Any] = []

    for trace in traces:
        value = _get_field_value(trace, field_name)
        if _is_present(value, check_type):
            present_count += 1
            if len(sample_values) < MAX_SAMPLE_VALUES and value is not None:
                sample_values.append(_truncate(value))

    coverage = present_count / population if population > 0 else 0.0
    return EvidenceRecord(
        field_path=path,
        sample_values=sample_values,
        population=population,
        present_count=present_count,
        coverage_pct=coverage,
    )


def _truncate(value: Any, max_len: int = 80) -> Any:
    """Truncate long values for display in sample_values."""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    if isinstance(value, list) and len(value) > 3:
        return value[:3]
    if isinstance(value, dict) and len(str(value)) > max_len:
        return {k: "..." for k in list(value.keys())[:3]}
    return value
