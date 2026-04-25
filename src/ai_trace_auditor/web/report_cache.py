"""In-memory TTL cache for rendered audit reports.

Lets the web UI hand out a short-lived report id with the results page,
which the client then exchanges for a PDF download via /audit/pdf/{id}.

Single-process only. Suitable for the Railway deployment; not for
multi-replica or serverless setups.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from threading import Lock

DEFAULT_TTL_SECONDS = 60 * 60  # 1 hour
MAX_ENTRIES = 256


@dataclass(frozen=True)
class CachedReport:
    markdown: str
    trace_source: str
    expires_at: float


class ReportCache:
    """Thread-safe TTL cache keyed by an opaque token."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[str, CachedReport] = {}
        self._lock = Lock()

    def put(self, markdown: str, trace_source: str) -> str:
        token = secrets.token_urlsafe(16)
        entry = CachedReport(
            markdown=markdown,
            trace_source=trace_source,
            expires_at=time.monotonic() + self._ttl,
        )
        with self._lock:
            self._evict_locked()
            self._store[token] = entry
        return token

    def get(self, token: str) -> CachedReport | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(token)
            if entry is None:
                return None
            if entry.expires_at < now:
                self._store.pop(token, None)
                return None
            return entry

    def _evict_locked(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if v.expires_at < now]
        for key in expired:
            self._store.pop(key, None)
        if len(self._store) >= self._max:
            oldest = sorted(
                self._store.items(), key=lambda kv: kv[1].expires_at
            )
            for key, _ in oldest[: len(self._store) - self._max + 1]:
                self._store.pop(key, None)
