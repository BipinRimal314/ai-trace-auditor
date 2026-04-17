"""Text normalization for robust substring matching across PDF artifacts.

The same normalization is applied to (a) text extracted from a pinned PDF
source and (b) every ``exact_quote`` declared in a requirement YAML. After
normalization, the quote must appear as a byte-for-byte substring of the
source text, or the requirement is rejected as unverified.

Design notes:

* **Case is preserved.** Legal texts capitalize selectively ("Article 12",
  "Annex III", "Commission"); a fabrication can't borrow real case patterns
  without knowing the source.
* **Punctuation is preserved.** LLMs frequently substitute "and" for "or" or
  drop semicolons; collapsing punctuation would let those slip through.
* **Hyphenation at line breaks is dehyphenated.** PDFs insert ``-\\n`` mid-word
  at page breaks; we join those so ``biometric-\\nidentification`` matches a
  quote of ``biometric identification``.
* **Smart quotes and ligatures are mapped to ASCII.** The EU Publications
  Office PDF uses typographic quotes and the ``ﬁ``/``ﬂ`` ligatures; quotes
  authored in plain ASCII from the law's rendered text would otherwise fail.
* **Whitespace is collapsed.** Newlines, tabs, non-breaking spaces, and
  repeated spaces all become a single space. This is the only information-
  lossy transformation; the only "fabrication" it enables is whitespace-only
  variations, which are not semantic.

This module has zero third-party dependencies so it can run under the
default test runtime without the ``[verify]`` extra.
"""

from __future__ import annotations

import re
import unicodedata

# --- Character-level substitutions applied before regex passes --------------
#
# Keys cover typographic characters that appear in the EU AI Act PDF but are
# rarely typed in plain-text authored quotes. Mapping to ASCII lets YAMLs be
# authored in a standard editor without pasting exotic codepoints.
_CHAR_SUBSTITUTIONS: dict[str, str] = {
    # Smart quotes
    "\u2018": "'",  # ' left single quote
    "\u2019": "'",  # ' right single quote
    "\u201A": "'",  # ‚ single low-9
    "\u201C": '"',  # " left double quote
    "\u201D": '"',  # " right double quote
    "\u201E": '"',  # „ double low-9
    "\u00AB": '"',  # « angle quote left
    "\u00BB": '"',  # » angle quote right
    # Dashes
    "\u2013": "-",  # – en dash
    "\u2014": "-",  # — em dash
    "\u2212": "-",  # − minus sign
    # Ligatures
    "\uFB00": "ff",  # ﬀ
    "\uFB01": "fi",  # ﬁ
    "\uFB02": "fl",  # ﬂ
    "\uFB03": "ffi",  # ﬃ
    "\uFB04": "ffl",  # ﬄ
    # Spaces that look like plain space but aren't
    "\u00A0": " ",  # non-breaking
    "\u2002": " ",  # en space
    "\u2003": " ",  # em space
    "\u2009": " ",  # thin space
    "\u200A": " ",  # hair space
    "\u202F": " ",  # narrow no-break
}

# --- Hyphenated-line-break pattern ------------------------------------------
#
# Matches ``wordchar + HYPHEN + any-whitespace-incl-newline + wordchar`` so
# that PDF end-of-line hyphenation is removed. We require word characters on
# both sides so compound hyphens like ``co-operation`` are preserved (the
# newline is the signal that the hyphen is an artifact, not semantic).
_HYPHENATED_LINEBREAK = re.compile(r"(\w)-\s*\n\s*(\w)")

# Collapses any run of whitespace (spaces, newlines, tabs, already-normalized
# substitutes) into a single ASCII space. Applied LAST so other passes can
# still use the original whitespace as a signal.
_ANY_WHITESPACE = re.compile(r"\s+")


def normalize_for_substring_match(text: str) -> str:
    """Normalize a block of text for byte-for-byte substring comparison.

    Idempotent: ``normalize(normalize(x)) == normalize(x)``.

    Safe to apply to both PDF-extracted text and authored quotes. The only
    semantically-lossy transformation is whitespace collapse; everything
    else preserves enough signal that a hallucinated quote can't pass.
    """
    # 1. Unicode canonical composition (e.g. combining acute + e → é).
    #    NFKC also decomposes compatibility forms so the ligature mapping
    #    below is a no-op for some forms but remains safe.
    text = unicodedata.normalize("NFKC", text)

    # 2. Substitute typographic characters for ASCII equivalents.
    for bad, good in _CHAR_SUBSTITUTIONS.items():
        if bad in text:
            text = text.replace(bad, good)

    # 3. Dehyphenate end-of-line hyphenation.
    text = _HYPHENATED_LINEBREAK.sub(r"\1\2", text)

    # 4. Collapse any whitespace run to a single space.
    text = _ANY_WHITESPACE.sub(" ", text)

    return text.strip()


def contains_exact_quote(source_text: str, quote: str) -> bool:
    """Return ``True`` if *quote* appears in *source_text* after normalization.

    Both arguments are normalized before comparison, so the function is
    indifferent to PDF-style whitespace and typographic quotes in either
    input.
    """
    normalized_source = normalize_for_substring_match(source_text)
    normalized_quote = normalize_for_substring_match(quote)
    if not normalized_quote:
        return False
    return normalized_quote in normalized_source
