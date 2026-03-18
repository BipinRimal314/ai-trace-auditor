"""Top-level codebase scanner orchestrator."""

from __future__ import annotations

import time
from pathlib import Path

from ai_trace_auditor.models.docs import CodeScanResult
from ai_trace_auditor.scanner.deployment_scanner import scan_deployment
from ai_trace_auditor.scanner.js_scanner import scan_js_file
from ai_trace_auditor.scanner.patterns import JS_EXTENSIONS, PYTHON_EXTENSIONS, SKIP_DIRS
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

        ai_imports.extend(scan["ai_imports"])
        model_refs.extend(scan["model_refs"])
        vector_dbs.extend(scan["vector_dbs"])
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
    """Remove duplicate model references (same model + file)."""
    seen: set[tuple[str, str]] = set()
    unique = []
    for ref in refs:
        key = (ref.model_id, ref.file_path)
        if key not in seen:
            seen.add(key)
            unique.append(ref)
    return unique
