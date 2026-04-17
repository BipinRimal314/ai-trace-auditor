"""Extract normalized text from a pinned PDF source document.

Uses ``pdfplumber`` (MIT, pure-Python-plus-pdfminer) to extract text page by
page, then runs the extracted text through the shared normalization so the
output is directly comparable to normalized ``exact_quote`` fields.

This module is only imported when the ``[verify]`` extra is installed. It is
not reachable from the runtime CLI or web server.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .text_normalize import normalize_for_substring_match

if TYPE_CHECKING:  # pragma: no cover
    pass


def extract_pdf_text(path: Path) -> str:
    """Return the full text of *path* as one normalized string.

    Extraction tolerances (``x_tolerance=2``, ``y_tolerance=2``) are tuned
    for EU Publications Office PDFs: they have a two-column header pattern
    on the first page and tight leading on body paragraphs; the default
    tolerances merge some words incorrectly.

    Raises :class:`FileNotFoundError` if *path* does not exist.
    """
    import pdfplumber  # Lazy import — only loaded when extras are installed.

    if not path.is_file():
        raise FileNotFoundError(f"PDF source missing: {path}")

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            pages.append(text)

    joined = "\n".join(pages)
    return normalize_for_substring_match(joined)
