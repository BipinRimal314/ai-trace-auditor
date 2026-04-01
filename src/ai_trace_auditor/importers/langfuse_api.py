"""Langfuse API trace importer.

Pulls traces from Langfuse's REST API and converts them to NormalizedTrace
using the same parsing logic as the file-based LangfuseIngestor.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from ai_trace_auditor.importers.base import ImportConfig
from ai_trace_auditor.ingest.langfuse import _parse_observation
from ai_trace_auditor.models.trace import NormalizedTrace

logger = logging.getLogger(__name__)

_DEFAULT_LANGFUSE_URL = "https://cloud.langfuse.com"
_PAGE_SIZE = 50


class LangfuseImporter:
    """Import traces from Langfuse via REST API.

    Authentication uses HTTP Basic Auth with public_key:secret_key.
    Works with both Langfuse Cloud and self-hosted instances.
    """

    platform_name = "Langfuse"

    def __init__(self, api_url: str = _DEFAULT_LANGFUSE_URL, api_key: str = "", secret_key: str = ""):
        self._api_url = api_url.rstrip("/")
        self._auth_header = _build_auth_header(api_key, secret_key)

    def test_connection(self) -> bool:
        """Verify the API connection by fetching a single trace."""
        try:
            response = httpx.get(
                f"{self._api_url}/api/public/traces",
                headers=self._auth_header,
                params={"limit": 1},
                timeout=10.0,
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def import_traces(self, config: ImportConfig) -> list[NormalizedTrace]:
        """Fetch traces from Langfuse and normalize them.

        Paginates through all matching traces, fetches full observation
        details for each, and converts using the shared Langfuse parser.
        """
        traces: list[NormalizedTrace] = []
        page = 1
        fetched = 0

        while fetched < config.limit:
            page_size = min(_PAGE_SIZE, config.limit - fetched)
            params = _build_query_params(config, page, page_size)

            response = _fetch(
                f"{self._api_url}/api/public/traces",
                headers=self._auth_header,
                params=params,
            )
            if response is None:
                break

            data = response.get("data", [])
            if not data:
                break

            for trace_data in data:
                normalized = _parse_trace(trace_data, self._api_url, self._auth_header)
                if normalized is not None:
                    traces.append(normalized)
                    fetched += 1
                    if fetched >= config.limit:
                        break

            meta = response.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1

        logger.info("Imported %d traces from Langfuse", len(traces))
        return traces


def _build_auth_header(api_key: str, secret_key: str) -> dict[str, str]:
    """Build HTTP Basic Auth header from Langfuse public + secret key."""
    credentials = base64.b64encode(f"{api_key}:{secret_key}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


def _build_query_params(config: ImportConfig, page: int, limit: int) -> dict[str, Any]:
    """Build query parameters for the traces endpoint."""
    params: dict[str, Any] = {"page": page, "limit": limit}
    if config.since:
        params["fromTimestamp"] = config.since.isoformat()
    if config.until:
        params["toTimestamp"] = config.until.isoformat()
    if config.tags:
        params["tags"] = config.tags
    return params


def _fetch(url: str, headers: dict[str, str], params: dict[str, Any]) -> dict[str, Any] | None:
    """Make an authenticated GET request and return parsed JSON."""
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error("Langfuse API error: %s %s", e.response.status_code, e.response.text[:200])
        return None
    except httpx.HTTPError as e:
        logger.error("Langfuse connection error: %s", e)
        return None


def _fetch_trace_detail(
    trace_id: str, api_url: str, headers: dict[str, str]
) -> dict[str, Any] | None:
    """Fetch full trace detail including observations."""
    return _fetch(f"{api_url}/api/public/traces/{trace_id}", headers, {})


def _parse_trace(
    trace_data: dict[str, Any], api_url: str, headers: dict[str, str]
) -> NormalizedTrace | None:
    """Parse a Langfuse trace into NormalizedTrace.

    If the trace listing doesn't include observations, fetches them
    from the detail endpoint.
    """
    observations = trace_data.get("observations", [])

    if not observations:
        detail = _fetch_trace_detail(trace_data.get("id", ""), api_url, headers)
        if detail:
            observations = detail.get("observations", [])

    if not observations:
        return None

    spans = [_parse_observation(obs) for obs in observations]
    trace_id = trace_data.get("id") or "unknown"

    metadata: dict[str, Any] = {}
    for key in ("name", "userId", "sessionId", "tags", "version", "release"):
        value = trace_data.get(key)
        if value is not None:
            metadata[key] = value

    return NormalizedTrace(
        trace_id=str(trace_id),
        spans=spans,
        source_format="langfuse_api",
        metadata=metadata,
    )
