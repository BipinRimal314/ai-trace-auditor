"""Evidence record models for gap analysis results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EvidenceRecord(BaseModel):
    """Records what trace data was found for a given evidence field."""

    field_path: str
    sample_values: list[Any] = []  # First N non-null values found
    population: int = 0  # Total spans checked
    present_count: int = 0  # Spans where field was non-null
    coverage_pct: float = 0.0  # present_count / population
