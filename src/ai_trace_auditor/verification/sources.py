"""Source-document registry: resolve, hash-verify, and text-extract.

The registry is read from ``registry.yaml``. Every entry declares a
human-readable ``name``, a file path relative to the project root, a
SHA-256 pin of the file bytes, the canonical publisher URL, and audit
metadata (who verified, when).

Public API:

* :func:`get_source` — load a source by name. Raises
  :class:`SourceHashMismatch` if the on-disk bytes no longer match the
  registry pin. Result is cached after first successful load.
* :func:`list_sources` — enumerate known source names.
* :class:`SourceDocument` — the returned object, carrying both the SHA-256
  of the file and the normalized extracted text ready for substring search.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .pdf_extract import extract_pdf_text

# ``verification/`` lives at src/ai_trace_auditor/verification/; the project
# root is four levels up (.. -> src/ai_trace_auditor -> src -> project root).
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_REGISTRY_PATH: Path = Path(__file__).parent / "registry.yaml"

_CHUNK_SIZE = 65_536

# Module-level cache so repeated ``get_source()`` calls within the same
# process don't re-extract the PDF (extraction for the EU AI Act costs
# ~1-2s). Keyed by registered name.
_CACHE: dict[str, "SourceDocument"] = {}


class SourceNotFoundError(KeyError):
    """Raised when a requested source name is not present in the registry."""


class SourceHashMismatch(RuntimeError):
    """Raised when the on-disk file's SHA-256 no longer matches the pin.

    Treat this as a fatal CI error. Investigation: diff the old vs new file,
    review whether every requirement that cites this source still holds,
    update the pin (and ``verified_date`` / ``verified_by``) only after a
    human review.
    """


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """A pinned legal or regulatory source document.

    Attributes:
        name: Registry key (e.g. ``"eu-ai-act-2024-1689"``).
        path: Absolute path to the file on disk.
        sha256: 64-character lowercase hex digest of the file's bytes.
        citation: Formal legal citation for display (e.g. ``"Regulation (EU) 2024/1689"``).
        source_url: Canonical publisher URL for fetching a fresh copy.
        verified_date: ISO date (``YYYY-MM-DD``) of the last human review.
        verified_by: Reviewer identifier (email, handle, or name).
        normalized_text: Full document text, run through
            :func:`.text_normalize.normalize_for_substring_match`, ready for
            substring comparison against requirement ``exact_quote`` fields.
    """

    name: str
    path: Path
    sha256: str
    citation: str
    source_url: str
    verified_date: str
    verified_by: str
    normalized_text: str

    @property
    def size_bytes(self) -> int:
        """Size of the source file on disk, in bytes."""
        return self.path.stat().st_size


def _sha256_of_file(path: Path) -> str:
    """Compute SHA-256 of *path*'s bytes without loading the whole file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def _load_registry() -> dict[str, dict[str, Any]]:
    """Parse ``registry.yaml`` and return the ``sources`` mapping."""
    with open(_REGISTRY_PATH, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "sources" not in data:
        raise RuntimeError(
            f"{_REGISTRY_PATH.name}: malformed — expected a top-level "
            "`sources:` mapping."
        )
    return data["sources"]


def list_sources() -> list[str]:
    """Return the names of all registered sources."""
    return sorted(_load_registry())


def get_source(
    name: str,
    *,
    project_root: Path | None = None,
    bypass_cache: bool = False,
) -> SourceDocument:
    """Load, hash-verify, and text-extract the source registered as *name*.

    Args:
        name: Registry key.
        project_root: Override the inferred project root. Tests use this to
            load the registry while pointing path resolution at a fixture
            directory.
        bypass_cache: Force a fresh hash + extraction even if the source is
            already cached.

    Raises:
        SourceNotFoundError: *name* is not in the registry.
        FileNotFoundError: the file at the registry path does not exist.
        SourceHashMismatch: the file bytes do not match the pinned hash.
    """
    if not bypass_cache and name in _CACHE:
        return _CACHE[name]

    registry = _load_registry()
    if name not in registry:
        known = ", ".join(sorted(registry))
        raise SourceNotFoundError(
            f"Unknown source {name!r}. Registered: {known}. "
            "Add an entry to src/ai_trace_auditor/verification/registry.yaml."
        )
    entry = registry[name]

    root = project_root if project_root is not None else _PROJECT_ROOT
    file_path = (root / entry["path"]).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(
            f"Source file for {name!r} not found at {file_path}. "
            f"Expected the publisher's copy (see {entry.get('source_url', 'registry.yaml')})."
        )

    actual_hash = _sha256_of_file(file_path)
    expected_hash = str(entry["sha256"]).lower().strip()
    if actual_hash != expected_hash:
        raise SourceHashMismatch(
            f"{name}: on-disk SHA-256 drifted from registry pin.\n"
            f"  file:     {file_path}\n"
            f"  expected: {expected_hash}\n"
            f"  actual:   {actual_hash}\n"
            "Review the diff and, if legitimate, update the pin and "
            "verified_date in registry.yaml — but only after re-checking "
            "every requirement that cites this source."
        )

    normalized_text = extract_pdf_text(file_path)

    doc = SourceDocument(
        name=name,
        path=file_path,
        sha256=actual_hash,
        citation=entry.get("citation", ""),
        source_url=entry.get("source_url", ""),
        verified_date=entry.get("verified_date", ""),
        verified_by=entry.get("verified_by", ""),
        normalized_text=normalized_text,
    )
    _CACHE[name] = doc
    return doc
