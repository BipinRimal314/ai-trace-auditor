"""JavaScript/TypeScript source file scanner using regex."""

from __future__ import annotations

import re
from pathlib import Path

from ai_trace_auditor.models.docs import (
    AIEndpoint,
    AIImport,
    ModelReference,
    VectorDBUsage,
)
from ai_trace_auditor.scanner.patterns import (
    JS_AI_IMPORTS,
    JS_VECTOR_DB_IMPORTS,
    MODEL_PATTERNS,
)

# Import patterns for ESM and CJS
_ESM_IMPORT = re.compile(r"""import\s+.*?\s+from\s+['"](.+?)['"]""")
_ESM_SIDE_EFFECT = re.compile(r"""import\s+['"](.+?)['"]""")
_DYNAMIC_IMPORT = re.compile(r"""import\s*\(\s*['"](.+?)['"]\s*\)""")
_CJS_REQUIRE = re.compile(r"""require\s*\(\s*['"](.+?)['"]\s*\)""")

# Express-style route patterns
_EXPRESS_ROUTE = re.compile(
    r"""(?:app|router)\.(get|post|put|delete|patch|all)\s*\("""
)

# Build reverse lookup: package_name -> (category, library_name)
_JS_IMPORT_LOOKUP: dict[str, tuple[str, str]] = {}
for lib, packages in JS_AI_IMPORTS.items():
    for pkg in packages:
        _JS_IMPORT_LOOKUP[pkg] = ("ai_sdk", lib)
for db, packages in JS_VECTOR_DB_IMPORTS.items():
    for pkg in packages:
        _JS_IMPORT_LOOKUP[pkg] = ("vector_db", db)


def scan_js_file(file_path: Path) -> dict[str, list]:
    """Scan a JS/TS file for AI framework usage.

    Returns same dict structure as python_scanner.scan_python_file.
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
    has_ai_import = False

    for i, line in enumerate(lines, 1):
        # --- Import detection ---
        for pattern in (_ESM_IMPORT, _ESM_SIDE_EFFECT, _DYNAMIC_IMPORT, _CJS_REQUIRE):
            for m in pattern.finditer(line):
                pkg = m.group(1)
                match = _match_js_package(pkg)
                if match:
                    category, lib = match
                    if category == "ai_sdk":
                        result["ai_imports"].append(AIImport(
                            library=lib,
                            module_path=pkg,
                            file_path=fp,
                            line_number=i,
                        ))
                        has_ai_import = True
                    elif category == "vector_db":
                        result["vector_dbs"].append(VectorDBUsage(
                            db_name=lib,
                            module_path=pkg,
                            file_path=fp,
                            line_number=i,
                        ))

        # --- Model identifier detection ---
        for pattern in MODEL_PATTERNS:
            m = pattern.search(line)
            if m:
                result["model_refs"].append(ModelReference(
                    model_id=m.group(0),
                    file_path=fp,
                    line_number=i,
                    context=line.strip()[:120],
                ))
                break

    # --- Express endpoints (only if AI imports found) ---
    if has_ai_import:
        for i, line in enumerate(lines, 1):
            if _EXPRESS_ROUTE.search(line):
                route = _extract_js_route(line)
                result["endpoints"].append(AIEndpoint(
                    framework="express",
                    route=route,
                    file_path=fp,
                    line_number=i,
                ))

    # --- Next.js API route detection via file path ---
    if has_ai_import and "/api/" in fp:
        result["endpoints"].append(AIEndpoint(
            framework="nextjs",
            route=_infer_nextjs_route(fp),
            file_path=fp,
            line_number=1,
        ))

    return result


def _match_js_package(pkg: str) -> tuple[str, str] | None:
    """Match a JS package name against known AI and vector DB packages."""
    if pkg in _JS_IMPORT_LOOKUP:
        return _JS_IMPORT_LOOKUP[pkg]
    # Handle scoped sub-paths: "@langchain/core/runnables" -> "@langchain/core"
    for known_pkg, value in _JS_IMPORT_LOOKUP.items():
        if pkg.startswith(known_pkg + "/"):
            return value
    return None


_JS_ROUTE_RE = re.compile(r"""['"](/[^'"]*?)['"]""")


def _extract_js_route(line: str) -> str:
    """Extract route path from Express-style route declaration."""
    m = _JS_ROUTE_RE.search(line)
    return m.group(1) if m else "[unknown]"


def _infer_nextjs_route(file_path: str) -> str:
    """Infer a Next.js API route from the file path."""
    # e.g., "src/app/api/chat/route.ts" -> "/api/chat"
    parts = file_path.replace("\\", "/").split("/api/")
    if len(parts) > 1:
        route_part = parts[-1]
        # Remove file name (route.ts, index.ts, etc.)
        route_part = "/".join(
            seg for seg in route_part.split("/")
            if not seg.startswith("route.") and not seg.startswith("index.")
        )
        return "/api/" + route_part.rstrip("/")
    return "/api/[unknown]"
