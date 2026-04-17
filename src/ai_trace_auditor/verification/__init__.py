"""Primary-source verification for AI Trace Auditor requirement YAMLs.

This package is the structural gate that prevents requirement fabrication.
It exposes three layers of protection:

1. **Source pinning** (``sources.py``, ``registry.yaml``): every legal or
   regulatory document the auditor cites is registered with a SHA-256 hash
   of its byte-for-byte content on disk. Any drift fails CI loudly.

2. **Exact-quote enforcement** (``quote_validator.py``): every requirement
   entry must declare an ``exact_quote`` — verbatim text from the pinned
   source. The validator substring-matches the quote against the normalized
   extracted text. An LLM cannot silently invent a substring that has to
   appear byte-for-byte in a hashed document.

3. **Evidence-field provenance** (``provenance.py``): every trace-field an
   evidence-field maps to must declare a ``legal_basis`` (``direct``,
   ``structural``, ``product_inference``). ``required: true`` fields are
   allowed only when the basis is ``direct`` and a ``source_quote`` is
   provided. This is the gate that catches "fabricated mandatory field"
   mistakes like the Article 12 audit findings.

The package is only needed at development time (running ``pytest`` or the
release gate). It is NOT a runtime dependency of the CLI or web UI. Install
with the ``verify`` extra: ``pip install -e ".[verify]"``.
"""

from .sources import (
    SourceDocument,
    SourceHashMismatch,
    SourceNotFoundError,
    get_source,
    list_sources,
)
from .text_normalize import normalize_for_substring_match

__all__ = [
    "SourceDocument",
    "SourceHashMismatch",
    "SourceNotFoundError",
    "get_source",
    "list_sources",
    "normalize_for_substring_match",
]
