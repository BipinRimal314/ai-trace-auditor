"""Python source file scanner using AST parsing + regex."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ai_trace_auditor.models.docs import (
    AIEndpoint,
    AIImport,
    EvalScriptRef,
    ModelReference,
    TrainingDataRef,
    VectorDBUsage,
)
from ai_trace_auditor.scanner.patterns import (
    AI_SDK_IMPORTS,
    API_FRAMEWORK_PATTERNS,
    EVAL_METRIC_PATTERNS,
    MODEL_PATTERNS,
    TRAINING_DATA_PATTERNS,
    VECTOR_DB_IMPORTS,
)

# Build reverse lookup: module_prefix -> (category, library_name)
_IMPORT_LOOKUP: dict[str, tuple[str, str]] = {}
for lib, modules in AI_SDK_IMPORTS.items():
    for mod in modules:
        _IMPORT_LOOKUP[mod] = ("ai_sdk", lib)
for db, modules in VECTOR_DB_IMPORTS.items():
    for mod in modules:
        _IMPORT_LOOKUP[mod] = ("vector_db", db)


def scan_python_file(file_path: Path) -> dict[str, list]:
    """Scan a single Python file for AI framework usage.

    Returns a dict with keys: ai_imports, model_refs, vector_dbs,
    training_data, eval_metrics, endpoints.
    """
    result: dict[str, list] = {
        "ai_imports": [],
        "model_refs": [],
        "vector_dbs": [],
        "training_data": [],
        "eval_metrics": [],
        "endpoints": [],
    }

    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result

    lines = source.splitlines()
    fp = str(file_path)

    # --- AST-based import detection ---
    try:
        tree = ast.parse(source, filename=fp)
    except SyntaxError:
        # Fall back to regex-only for unparseable files
        _scan_lines(lines, fp, result)
        return result

    has_ai_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                match = _match_module(alias.name)
                if match:
                    category, lib = match
                    _add_import(category, lib, alias.name, fp, node.lineno, result)
                    if category == "ai_sdk":
                        has_ai_import = True

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                match = _match_module(node.module)
                if match:
                    category, lib = match
                    _add_import(category, lib, node.module, fp, node.lineno, result)
                    if category == "ai_sdk":
                        has_ai_import = True

    # --- String literal scan for model identifiers ---
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for pattern in MODEL_PATTERNS:
                m = pattern.search(node.value)
                if m:
                    context = _get_context(lines, node.lineno - 1)
                    result["model_refs"].append(ModelReference(
                        model_id=m.group(0),
                        file_path=fp,
                        line_number=node.lineno,
                        context=context,
                    ))
                    break  # one match per string

    # --- Line-by-line pattern scan ---
    _scan_lines(lines, fp, result)

    # --- API endpoint detection (only if file has AI imports) ---
    if has_ai_import:
        _detect_endpoints(lines, fp, result)

    return result


def _match_module(module_name: str) -> tuple[str, str] | None:
    """Check if a module name matches any known AI SDK or vector DB."""
    # Exact match
    if module_name in _IMPORT_LOOKUP:
        return _IMPORT_LOOKUP[module_name]
    # Prefix match (e.g., "langchain.chains" -> "langchain")
    for prefix, value in _IMPORT_LOOKUP.items():
        if module_name.startswith(prefix + "."):
            return value
    return None


def _add_import(
    category: str,
    lib: str,
    module_path: str,
    fp: str,
    line: int,
    result: dict[str, list],
) -> None:
    """Add an import to the appropriate result list."""
    if category == "ai_sdk":
        result["ai_imports"].append(AIImport(
            library=lib, module_path=module_path, file_path=fp, line_number=line,
        ))
    elif category == "vector_db":
        result["vector_dbs"].append(VectorDBUsage(
            db_name=lib, module_path=module_path, file_path=fp, line_number=line,
        ))


# API URL patterns for BYOK/requests-based AI usage (no SDK import)
_PY_API_URL_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic": re.compile(r"""api\.anthropic\.com"""),
    "openai": re.compile(r"""api\.openai\.com"""),
    "google_genai": re.compile(r"""generativelanguage\.googleapis\.com"""),
    "cohere": re.compile(r"""api\.cohere\.ai"""),
    "mistral": re.compile(r"""api\.mistral\.ai"""),
    "huggingface": re.compile(r"""api-inference\.huggingface\.co"""),
}


def _scan_lines(lines: list[str], fp: str, result: dict[str, list]) -> None:
    """Regex scan for training data, eval metrics, and BYOK API URLs."""
    eval_metrics_found: list[str] = []
    api_url_providers_seen: set[str] = set()

    for i, line in enumerate(lines, 1):
        for pattern in TRAINING_DATA_PATTERNS:
            if pattern.search(line):
                result["training_data"].append(TrainingDataRef(
                    pattern=pattern.pattern.rstrip(r"\s*\("),
                    file_path=fp,
                    line_number=i,
                    context=line.strip()[:120],
                ))
                break

        for pattern in EVAL_METRIC_PATTERNS:
            if pattern.search(line):
                metric_name = pattern.pattern.rstrip(r"\s*\(")
                if metric_name not in eval_metrics_found:
                    eval_metrics_found.append(metric_name)

        # BYOK / requests-based API URL detection
        for provider, url_pattern in _PY_API_URL_PATTERNS.items():
            if provider not in api_url_providers_seen and url_pattern.search(line):
                api_url_providers_seen.add(provider)
                result["ai_imports"].append(AIImport(
                    library=provider,
                    module_path=f"requests/{provider} (BYOK — API URL detected, no SDK import)",
                    file_path=fp,
                    line_number=i,
                ))

    if eval_metrics_found:
        result["eval_metrics"].append(EvalScriptRef(
            file_path=fp,
            metrics_detected=eval_metrics_found,
        ))


def _detect_endpoints(lines: list[str], fp: str, result: dict[str, list]) -> None:
    """Detect API endpoints in files that also import AI SDKs."""
    for i, line in enumerate(lines, 1):
        for framework, patterns in API_FRAMEWORK_PATTERNS.items():
            for pattern in patterns:
                m = pattern.search(line)
                if m:
                    route = _extract_route(lines, i - 1)
                    result["endpoints"].append(AIEndpoint(
                        framework=framework,
                        route=route,
                        file_path=fp,
                        line_number=i,
                    ))


_ROUTE_RE = re.compile(r"""['"](/[^'"]*?)['"]""")


def _extract_route(lines: list[str], line_idx: int) -> str:
    """Try to extract a route path from the decorator/function line."""
    # Check current and next line for a quoted path
    for offset in range(min(2, len(lines) - line_idx)):
        m = _ROUTE_RE.search(lines[line_idx + offset])
        if m:
            return m.group(1)
    return "[unknown]"


def _get_context(lines: list[str], line_idx: int) -> str:
    """Get a context snippet around the given line index."""
    if 0 <= line_idx < len(lines):
        return lines[line_idx].strip()[:120]
    return ""
