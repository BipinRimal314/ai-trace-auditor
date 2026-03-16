"""Base protocol for trace ingestors."""

from __future__ import annotations

from typing import Any, Protocol

from ai_trace_auditor.models.trace import NormalizedTrace


class TraceIngestor(Protocol):
    """Protocol that all trace format parsers must implement."""

    def can_parse(self, data: dict[str, Any] | list[Any]) -> bool:
        """Return True if this ingestor can handle the given data structure."""
        ...

    def parse(self, data: dict[str, Any] | list[Any]) -> list[NormalizedTrace]:
        """Parse raw data into normalized traces."""
        ...
