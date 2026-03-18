"""Top-level codebase scanner orchestrator."""

from __future__ import annotations

import time
from pathlib import Path

from ai_trace_auditor.models.docs import CodeScanResult
from ai_trace_auditor.scanner.deployment_scanner import scan_deployment
from ai_trace_auditor.scanner.js_scanner import scan_js_file
from ai_trace_auditor.scanner.patterns import (
    CONFIG_FILE_NAMES,
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
    TEST_DIR_NAMES,
    TEST_FILE_PREFIXES,
    TEST_FILE_SUFFIXES,
)
from ai_trace_auditor.scanner.python_scanner import scan_python_file


def scan_codebase(root_dir: Path) -> CodeScanResult:
    """Scan a codebase directory for AI framework usage.

    Walks the directory tree, dispatches to Python or JS/TS scanners,
    and aggregates results into a CodeScanResult.
    """
    start = time.monotonic()

    ai_imports = []
    model_refs = []
    vector_dbs = []
    training_data = []
    eval_metrics = []
    endpoints = []
    file_count = 0

    for file_path in _walk_source_files(root_dir):
        file_count += 1
        ext = file_path.suffix.lower()

        if ext in PYTHON_EXTENSIONS:
            scan = scan_python_file(file_path)
        elif ext in JS_EXTENSIONS:
            scan = scan_js_file(file_path)
        else:
            continue

        is_test = _is_test_file(file_path, root_dir)
        is_config = _is_config_file(file_path)

        # Always collect imports (test files legitimately import SDKs)
        ai_imports.extend(scan["ai_imports"])
        vector_dbs.extend(scan["vector_dbs"])

        # Model refs from test/config files are reference data, not usage.
        # Files with >10 model refs are likely mapping tables, not usage.
        file_model_refs = scan["model_refs"]
        if not is_test and not is_config and len(file_model_refs) <= 10:
            model_refs.extend(file_model_refs)

        # Training data and eval metrics: keep from all files
        training_data.extend(scan["training_data"])
        eval_metrics.extend(scan["eval_metrics"])
        endpoints.extend(scan["endpoints"])

    # Deployment artifacts
    deployment_configs = scan_deployment(root_dir)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return CodeScanResult(
        scanned_dir=str(root_dir),
        file_count=file_count,
        scan_duration_ms=elapsed_ms,
        ai_imports=_dedupe_imports(ai_imports),
        model_references=_dedupe_model_refs(model_refs),
        vector_dbs=vector_dbs,
        training_data_refs=training_data,
        eval_scripts=eval_metrics,
        deployment_configs=deployment_configs,
        ai_endpoints=endpoints,
    )


def _walk_source_files(root_dir: Path) -> list[Path]:
    """Walk directory tree, skipping excluded dirs, returning source files."""
    files: list[Path] = []
    all_extensions = PYTHON_EXTENSIONS | JS_EXTENSIONS

    for item in sorted(root_dir.rglob("*")):
        if item.is_dir():
            continue

        # Check if any parent dir should be skipped
        if _should_skip(item, root_dir):
            continue

        if item.suffix.lower() in all_extensions:
            files.append(item)

    return files


def _should_skip(file_path: Path, root_dir: Path) -> bool:
    """Check if file is inside a directory that should be skipped."""
    try:
        rel = file_path.relative_to(root_dir)
    except ValueError:
        return True

    for part in rel.parts[:-1]:  # check directory parts, not filename
        if part in SKIP_DIRS or part.endswith(".egg-info"):
            return True
    return False


def _dedupe_imports(imports: list) -> list:
    """Remove duplicate imports (same library + file)."""
    seen: set[tuple[str, str]] = set()
    unique = []
    for imp in imports:
        key = (imp.library, imp.file_path)
        if key not in seen:
            seen.add(key)
            unique.append(imp)
    return unique


def _dedupe_model_refs(refs: list) -> list:
    """Remove duplicate model references.

    Keeps the first occurrence of each model ID globally (not per-file).
    Normalizes IDs by stripping trailing punctuation.
    This prevents gateway/proxy codebases from listing hundreds of models
    that appear in routing tables.
    """
    seen: set[str] = set()
    unique = []
    for ref in refs:
        # Normalize: strip trailing dots, dashes, underscores
        clean_id = ref.model_id.rstrip(".-_")
        if not clean_id or clean_id in seen:
            continue
        # Skip obvious non-model strings that slipped through regex
        if any(ext in clean_id for ext in (".py", ".js", ".ts", ".html", ".ipynb", ".mjs")):
            continue
        seen.add(clean_id)
        # Update the ref with cleaned ID
        ref_copy = ref.model_copy(update={"model_id": clean_id})
        unique.append(ref_copy)
    return unique


def _is_test_file(file_path: Path, root_dir: Path) -> bool:
    """Check if a file is a test file (model refs are test data, not usage)."""
    name = file_path.name.lower()

    # Check filename patterns
    if name.startswith(TEST_FILE_PREFIXES):
        return True
    for suffix in TEST_FILE_SUFFIXES:
        if name.endswith(suffix):
            return True

    # Check if any parent directory is a test directory
    try:
        rel = file_path.relative_to(root_dir)
    except ValueError:
        return False
    for part in rel.parts[:-1]:
        if part.lower() in TEST_DIR_NAMES:
            return True

    return False


def _is_config_file(file_path: Path) -> bool:
    """Check if a file is a config/mapping file (model names are reference data)."""
    return file_path.name.lower() in CONFIG_FILE_NAMES
