"""Top-level codebase scanner orchestrator."""

from __future__ import annotations

import time
from pathlib import Path

from ai_trace_auditor.models.docs import CodeScanResult
from ai_trace_auditor.scanner.deployment_scanner import scan_dependency_files, scan_deployment
from ai_trace_auditor.scanner.js_scanner import scan_js_file
from ai_trace_auditor.scanner.patterns import (
    CONFIG_FILE_NAMES,
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
    SUPPORTS_DIR_NAMES,
    TEST_DIR_NAMES,
    TEST_FILE_PREFIXES,
    TEST_FILE_SUFFIXES,
)
from ai_trace_auditor.scanner.python_scanner import scan_python_file


def scan_codebase(root_dir: Path) -> CodeScanResult:
    """Scan a codebase directory for AI framework usage.

    Walks the directory tree, dispatches to Python or JS/TS scanners,
    and aggregates results into a CodeScanResult.

    Classifies imports as "uses" (direct usage in core code) or
    "supports" (optional integrations, plugins, examples).
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
        is_support = _is_supports_file(file_path, root_dir)

        # Classify imports as "uses" or "supports"
        usage_type = "supports" if (is_test or is_support) else "uses"
        for imp in scan["ai_imports"]:
            imp_with_type = imp.model_copy(update={"usage_type": usage_type})
            ai_imports.append(imp_with_type)

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

    # Dependency file scanning (requirements.txt, pyproject.toml, package.json)
    dep_imports = scan_dependency_files(root_dir)
    ai_imports.extend(dep_imports)

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
    """Remove duplicate imports (same library + file).

    When the same library appears as both "uses" and "supports",
    keep the "uses" classification (it's more specific).
    """
    best: dict[tuple[str, str], object] = {}
    for imp in imports:
        key = (imp.library, imp.file_path)
        existing = best.get(key)
        if existing is None:
            best[key] = imp
        elif imp.usage_type == "uses" and existing.usage_type == "supports":
            best[key] = imp
    return list(best.values())


def _dedupe_model_refs(refs: list) -> list:
    """Remove duplicate model references.

    Keeps the first occurrence of each model ID globally (not per-file).
    Normalizes IDs by stripping trailing punctuation.
    """
    seen: set[str] = set()
    unique = []
    for ref in refs:
        clean_id = ref.model_id.rstrip(".-_")
        if not clean_id or clean_id in seen:
            continue
        if any(ext in clean_id for ext in (".py", ".js", ".ts", ".html", ".ipynb", ".mjs")):
            continue
        seen.add(clean_id)
        ref_copy = ref.model_copy(update={"model_id": clean_id})
        unique.append(ref_copy)
    return unique


def _is_test_file(file_path: Path, root_dir: Path) -> bool:
    """Check if a file is a test file."""
    name = file_path.name.lower()

    if name.startswith(TEST_FILE_PREFIXES):
        return True
    for suffix in TEST_FILE_SUFFIXES:
        if name.endswith(suffix):
            return True

    try:
        rel = file_path.relative_to(root_dir)
    except ValueError:
        return False
    for part in rel.parts[:-1]:
        if part.lower() in TEST_DIR_NAMES:
            return True

    return False


def _is_config_file(file_path: Path) -> bool:
    """Check if a file is a config/mapping file."""
    return file_path.name.lower() in CONFIG_FILE_NAMES


def _is_supports_file(file_path: Path, root_dir: Path) -> bool:
    """Check if a file is in a supports/integration/plugin directory.

    Imports from these directories are optional integrations that the
    framework supports, not dependencies that the core code uses.
    """
    try:
        rel = file_path.relative_to(root_dir)
    except ValueError:
        return False
    for part in rel.parts[:-1]:
        if part.lower() in SUPPORTS_DIR_NAMES:
            return True
    return False
