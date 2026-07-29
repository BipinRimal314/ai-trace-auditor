"""Native-accelerated codebase scanning via the optional `aitrace_core` wheel.

This module is an accelerator, never a requirement. If `aitrace-core` is not
installed, `is_available()` returns False and `scan.scan_codebase` uses the
pure-Python scanners unchanged.

# Division of labour

The Rust core walks the tree, reads files, parses them with tree-sitter, and
runs regexes supplied by *this* module. It has no idea what any of the results
mean. Every table that encodes compliance knowledge — which packages are AI
SDKs, which are vector databases, what a model identifier looks like — stays
in `patterns.py`, and is handed across the boundary on each call.

That boundary is deliberate. The pattern tables track a moving regulatory
target and are edited often; the parser is not. Compiling the tables into the
extension would mean rebuilding wheels for every platform to add one provider.

# Equivalence

For Python files the native path is intended to be bit-for-bit identical to
`python_scanner.scan_python_file`, and `tests/test_scanner/test_native_parity.py`
enforces that against real repositories.

For JavaScript and TypeScript it is deliberately *not* identical. The scanner
it replaces matched imports with regular expressions applied line by line,
which cannot distinguish code from a comment or a string. tree-sitter parses
properly, so the native path drops those false positives and finds real imports
the regexes missed. Those differences are improvements, and the parity test
asserts their direction rather than their absence. See `KNOWN_DIVERGENCES`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ai_trace_auditor.models.docs import (
    AIImport,
    EvalScriptRef,
    ModelReference,
    TrainingDataRef,
    VectorDBUsage,
)
from ai_trace_auditor.scanner.js_scanner import (
    _AI_API_URL_PATTERNS as JS_API_URL_PATTERNS,
)
from ai_trace_auditor.scanner.js_scanner import _EXPRESS_ROUTE as JS_EXPRESS_ROUTE
from ai_trace_auditor.scanner.js_scanner import _match_js_package
from ai_trace_auditor.scanner.js_scanner import scan_js_file
from ai_trace_auditor.scanner.patterns import (
    API_FRAMEWORK_PATTERNS,
    EVAL_METRIC_PATTERNS,
    JS_EXTENSIONS,
    MODEL_PATTERNS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
    TRAINING_DATA_PATTERNS,
)
from ai_trace_auditor.scanner.python_scanner import _PY_API_URL_PATTERNS as PY_API_URL_PATTERNS
from ai_trace_auditor.scanner.python_scanner import _match_module, scan_python_file

try:
    import aitrace_core as _core
except ImportError:  # pragma: no cover - exercised by the no-extension CI job
    _core = None


#: Differences between the native and pure-Python paths that are intended.
#: Each is pinned by a test in `tests/test_scanner/test_native_parity.py`, so
#: an unintended divergence cannot hide behind a blanket "these may differ".
#:
#: The first two are corrections of real defects in the scanners being
#: replaced, found by running both implementations over four large public AI
#: codebases. Both change audit output, so both are called out in the changelog
#: rather than shipped quietly as "performance work".
KNOWN_DIVERGENCES: dict[str, str] = {
    "py_relative_imports": (
        "FIXED FALSE POSITIVE. `from .openai import Foo` imports a local "
        "submodule, but CPython's ast splits the leading dots into a separate "
        "`level` field and reports `module='openai'`, which the pure-Python "
        "scanner then matched against the OpenAI SDK. Every package whose own "
        "submodule shares a name with a tracked SDK was affected — Haystack's "
        "`haystack/components/generators/chat/__init__.py` is one real case. "
        "tree-sitter keeps the dots, so relative imports no longer match."
    ),
    "py_syntax_error_recovery": (
        "FIXED FALSE NEGATIVE. When `ast.parse` raised SyntaxError the "
        "pure-Python scanner fell back to a line-regex pass that does no "
        "import detection at all, so a file that failed to parse reported "
        "zero imports. tree-sitter recovers from syntax errors and keeps "
        "going. Real case: CrewAI ships Jinja-templated `.py` files whose "
        "`from crewai import Agent, Crew` on line 1 was entirely invisible."
    ),
    "py_finding_ordering": (
        "Findings are reported in source order. The pure-Python scanner used "
        "`ast.walk`, which is breadth-first, so when one file imports the same "
        "library twice — or names the same model twice — the entry surviving "
        "deduplication could be any of them. Changes which line is cited, "
        "never whether the library or model is found."
    ),
    "js_comments": (
        "The regex scanner matched imports and model identifiers inside "
        "comments and string literals. tree-sitter does not, so the native "
        "path reports strictly fewer false positives on JS/TS."
    ),
    "js_multiline_imports": (
        "The regex scanner matched one line at a time and missed imports "
        "spanning several lines. The native path finds them."
    ),
    "js_model_refs_from_literals": (
        "JS model identifiers are matched against parsed string literals "
        "rather than raw lines, so a model name mentioned in a comment is no "
        "longer reported as usage."
    ),
}


def is_available() -> bool:
    """True when the native extension is importable."""
    return _core is not None


def version() -> str | None:
    """Version of the loaded native core, or None when unavailable."""
    return getattr(_core, "__version__", None) if _core else None


# ---------------------------------------------------------------------------
# Pattern marshalling
#
# The Rust side takes flat lists of regex strings and reports hits as indices
# back into them. These helpers build the lists and the offset table needed to
# map an index back to the group it came from.
# ---------------------------------------------------------------------------


class _PatternIndex:
    """A flat pattern list plus the group boundaries to decode its indices."""

    def __init__(self, groups: dict[str, list[re.Pattern[str]]]) -> None:
        self.patterns: list[str] = []
        self.bounds: dict[str, tuple[int, int]] = {}
        for name, group in groups.items():
            start = len(self.patterns)
            self.patterns.extend(p.pattern for p in group)
            self.bounds[name] = (start, len(self.patterns))

    def group_of(self, index: int) -> tuple[str, int] | None:
        """Map a flat index to `(group_name, index_within_group)`."""
        for name, (start, end) in self.bounds.items():
            if start <= index < end:
                return name, index - start
        return None


def _build_line_patterns() -> _PatternIndex:
    """Every pattern that the Python scanners apply line by line.

    `endpoint_hint` is not used to build findings. It exists only so the
    native pass can tell which files could possibly declare an HTTP route, so
    the (comparatively expensive) Python endpoint detection can be run on those
    files alone instead of on every file that imports an AI SDK.
    """
    endpoint_hints = [p for group in API_FRAMEWORK_PATTERNS.values() for p in group]
    endpoint_hints.append(JS_EXPRESS_ROUTE)
    return _PatternIndex(
        {
            "training_data": list(TRAINING_DATA_PATTERNS),
            "eval_metric": list(EVAL_METRIC_PATTERNS),
            "py_api_url": list(PY_API_URL_PATTERNS.values()),
            "js_api_url": list(JS_API_URL_PATTERNS.values()),
            "endpoint_hint": endpoint_hints,
        }
    )


_LINE_PATTERNS = _build_line_patterns()
_PY_API_PROVIDERS = list(PY_API_URL_PATTERNS.keys())
_JS_API_PROVIDERS = list(JS_API_URL_PATTERNS.keys())

#: `pattern.pattern.rstrip(r"\s*\(")` is how `python_scanner` derives the name
#: it stores on a TrainingDataRef. Computed here from the same objects so the
#: two can never drift.
_TRAINING_NAMES = [p.pattern.rstrip(r"\s*\(") for p in TRAINING_DATA_PATTERNS]
_EVAL_NAMES = [p.pattern.rstrip(r"\s*\(") for p in EVAL_METRIC_PATTERNS]


def _prefilter_literals() -> list[str]:
    """Literal substrings that make a file worth parsing.

    A file containing none of these cannot yield an import finding, so the
    native core skips parsing it. Being wrong in the *inclusive* direction is
    free (the file is parsed and yields nothing); being wrong in the exclusive
    direction would silently drop findings, so every module name and package
    name from both lookup tables is included in full.
    """
    from ai_trace_auditor.scanner.patterns import (
        AI_SDK_IMPORTS,
        JS_AI_IMPORTS,
        JS_VECTOR_DB_IMPORTS,
        VECTOR_DB_IMPORTS,
    )

    literals: set[str] = set()
    for table in (AI_SDK_IMPORTS, VECTOR_DB_IMPORTS, JS_AI_IMPORTS, JS_VECTOR_DB_IMPORTS):
        for names in table.values():
            literals.update(names)
    return sorted(literals)


# ---------------------------------------------------------------------------
# Result assembly
# ---------------------------------------------------------------------------


def _empty_result() -> dict[str, list]:
    return {
        "ai_imports": [],
        "model_refs": [],
        "vector_dbs": [],
        "training_data": [],
        "eval_metrics": [],
        "endpoints": [],
    }


def _apply_line_matches(
    line_matches: list[tuple[int, int, str]],
    fp: str,
    result: dict[str, list],
    api_providers: list[str],
    api_group: str,
    module_prefix: str,
) -> None:
    """Reproduce `_scan_lines` from the native core's line hits.

    The native core reports every (pattern, line) pair; the aggregation rules
    — first pattern wins per line, metric names unique and in first-seen order,
    one entry per API provider — are applied here so they stay in one place and
    keep matching the code being replaced.
    """
    eval_found: list[str] = []
    providers_seen: set[str] = set()
    training_lines: set[int] = set()

    # Native hits arrive ordered by (line, pattern index), which is the order
    # the Python loops visit them in.
    for flat_index, line_no, context in line_matches:
        decoded = _LINE_PATTERNS.group_of(flat_index)
        if decoded is None:
            continue
        group, local = decoded

        if group == "training_data":
            # Python breaks after the first matching pattern on a line.
            if line_no not in training_lines:
                training_lines.add(line_no)
                result["training_data"].append(
                    TrainingDataRef(
                        pattern=_TRAINING_NAMES[local],
                        file_path=fp,
                        line_number=line_no,
                        context=context,
                    )
                )

        elif group == "eval_metric":
            name = _EVAL_NAMES[local]
            if name not in eval_found:
                eval_found.append(name)

        elif group == api_group:
            provider = api_providers[local]
            if provider not in providers_seen:
                providers_seen.add(provider)
                result["ai_imports"].append(
                    AIImport(
                        library=provider,
                        module_path=(
                            f"{module_prefix}/{provider} "
                            "(BYOK — API URL detected, no SDK import)"
                        ),
                        file_path=fp,
                        line_number=line_no,
                    )
                )

    if eval_found:
        result["eval_metrics"].append(
            EvalScriptRef(file_path=fp, metrics_detected=eval_found)
        )


def _python_file_result(scan: Any, fp: str) -> tuple[dict[str, list], bool]:
    """Build a `scan_python_file`-shaped dict from native facts."""
    result = _empty_result()
    has_ai_import = False

    for module, qualified, line in scan.imports:
        match = _match_module(qualified)
        if not match:
            continue
        category, lib = match
        if category == "ai_sdk":
            result["ai_imports"].append(
                AIImport(
                    library=lib, module_path=qualified, file_path=fp, line_number=line
                )
            )
            has_ai_import = True
        elif category == "vector_db":
            result["vector_dbs"].append(
                VectorDBUsage(
                    db_name=lib, module_path=qualified, file_path=fp, line_number=line
                )
            )

    for _idx, matched, line, context in scan.string_matches:
        result["model_refs"].append(
            ModelReference(
                model_id=matched, file_path=fp, line_number=line, context=context
            )
        )

    _apply_line_matches(
        scan.line_matches, fp, result, _PY_API_PROVIDERS, "py_api_url", "requests"
    )
    return result, has_ai_import


def _js_file_result(scan: Any, fp: str) -> tuple[dict[str, list], bool]:
    """Build a `scan_js_file`-shaped dict from native facts."""
    result = _empty_result()
    has_ai_import = False

    for _module, qualified, line in scan.imports:
        match = _match_js_package(qualified)
        if not match:
            continue
        category, lib = match
        if category == "ai_sdk":
            result["ai_imports"].append(
                AIImport(
                    library=lib, module_path=qualified, file_path=fp, line_number=line
                )
            )
            has_ai_import = True
        elif category == "vector_db":
            result["vector_dbs"].append(
                VectorDBUsage(
                    db_name=lib, module_path=qualified, file_path=fp, line_number=line
                )
            )

    for _idx, matched, line, context in scan.string_matches:
        result["model_refs"].append(
            ModelReference(
                model_id=matched, file_path=fp, line_number=line, context=context
            )
        )

    _apply_line_matches(
        scan.line_matches, fp, result, _JS_API_PROVIDERS, "js_api_url", "fetch"
    )
    if result["ai_imports"]:
        has_ai_import = True
    return result, has_ai_import


def _may_declare_endpoint(scan: Any, fp: str, ext: str) -> bool:
    """Whether a file could possibly yield an endpoint finding.

    Conservative by construction: a false positive costs one redundant Python
    scan, a false negative would silently drop a finding. The Next.js branch
    has no line pattern to key on because that detection is driven purely by
    the file's path containing `/api/`.
    """
    start, end = _LINE_PATTERNS.bounds["endpoint_hint"]
    if any(start <= flat_index < end for flat_index, _line, _ctx in scan.line_matches):
        return True
    return ext in JS_EXTENSIONS and "/api/" in fp


def scan_all_files(root_dir: Path) -> tuple[dict[Path, dict[str, list]], int]:
    """Scan every source file under `root_dir` using the native core.

    Returns the per-file result dicts keyed by path — the same shape
    `scan_python_file` and `scan_js_file` return — and the number of source
    files considered.

    Raises RuntimeError if the native core is not installed; callers should
    check `is_available()` first.
    """
    if _core is None:
        raise RuntimeError("aitrace_core is not installed")

    native = _core.scan_tree(
        str(root_dir),
        skip_dirs=sorted(SKIP_DIRS),
        prefilter=_prefilter_literals(),
        line_patterns=_LINE_PATTERNS.patterns,
        string_patterns=[p.pattern for p in MODEL_PATTERNS],
    )

    results: dict[Path, dict[str, list]] = {}
    endpoint_candidates: list[Path] = []

    for scan in native.files:
        path = Path(scan.path)
        fp = scan.path
        ext = path.suffix.lower()

        if ext in PYTHON_EXTENSIONS:
            result, has_ai = _python_file_result(scan, fp)
        elif ext in JS_EXTENSIONS:
            result, has_ai = _js_file_result(scan, fp)
        else:
            continue

        results[path] = result
        if has_ai and _may_declare_endpoint(scan, fp, ext):
            endpoint_candidates.append(path)

    # Endpoint detection stays in Python. It needs a two-line lookahead to
    # recover a route path and has framework-specific fallbacks; reimplementing
    # that in Rust would risk divergence for very little gain.
    #
    # The gate above matters more than it looks. Running this on every file
    # that imports an AI SDK means re-parsing most of an AI-heavy repository in
    # Python and giving back nearly all of the speedup — on LangChain it cut
    # the improvement to almost nothing. Requiring an actual route-declaration
    # hint narrows it to the handful of files that can produce an endpoint.
    for path in endpoint_candidates:
        ext = path.suffix.lower()
        original = scan_python_file(path) if ext in PYTHON_EXTENSIONS else scan_js_file(path)
        results[path]["endpoints"] = original["endpoints"]

    return results, native.stats.files_considered


def native_stats(root_dir: Path) -> dict[str, int]:
    """Coverage counters for a scan, for reporting what was *not* examined."""
    if _core is None:
        raise RuntimeError("aitrace_core is not installed")
    native = _core.scan_tree(str(root_dir), skip_dirs=sorted(SKIP_DIRS))
    stats = native.stats
    return {
        "files_considered": stats.files_considered,
        "files_parsed": stats.files_parsed,
        "files_too_large": stats.files_too_large,
        "files_unreadable": stats.files_unreadable,
    }
