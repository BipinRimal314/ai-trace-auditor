"""Base protocol and config for API-based trace importers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from ai_trace_auditor.models.trace import NormalizedTrace


class ImportConfig(BaseModel):
    """Configuration for connecting to a trace platform."""

    api_url: str
    api_key: str | None = None
    secret_key: str | None = None
    project_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=1000, ge=1, le=10000)
    tags: list[str] | None = None


class TraceImporter(Protocol):
    """Protocol for importing traces from external platforms via API."""

    def test_connection(self) -> bool:
        """Verify the API connection works. Return True if healthy."""
        ...

    def import_traces(self, config: ImportConfig) -> list[NormalizedTrace]:
        """Fetch and normalize traces from the platform."""
        ...

    @property
    def platform_name(self) -> str:
        """Human-readable platform name for CLI output."""
        ...
