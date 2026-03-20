"""Deployment artifact and dependency file scanner."""

from __future__ import annotations

import re
from pathlib import Path

from ai_trace_auditor.models.docs import AIImport, DeploymentConfig
from ai_trace_auditor.scanner.patterns import (
    AI_SDK_IMPORTS,
    DEPLOYMENT_FILES,
    JS_AI_IMPORTS,
    VECTOR_DB_IMPORTS,
    JS_VECTOR_DB_IMPORTS,
)

# Build package name -> library mapping for dependency file scanning
_PY_PKG_TO_LIB: dict[str, str] = {}
for lib, modules in AI_SDK_IMPORTS.items():
    for mod in modules:
        _PY_PKG_TO_LIB[mod] = lib
for db, modules in VECTOR_DB_IMPORTS.items():
    for mod in modules:
        _PY_PKG_TO_LIB[mod] = f"vectordb:{db}"

_JS_PKG_TO_LIB: dict[str, str] = {}
for lib, packages in JS_AI_IMPORTS.items():
    for pkg in packages:
        _JS_PKG_TO_LIB[pkg] = lib
for db, packages in JS_VECTOR_DB_IMPORTS.items():
    for pkg in packages:
        _JS_PKG_TO_LIB[pkg] = f"vectordb:{db}"

# Combined pattern for quick detection
_ALL_PACKAGE_NAMES: set[str] = set()
_ALL_PACKAGE_NAMES.update(_PY_PKG_TO_LIB.keys())
_ALL_PACKAGE_NAMES.update(_JS_PKG_TO_LIB.keys())

_AI_DEP_PATTERN = re.compile(
    "|".join(re.escape(pkg) for pkg in sorted(_ALL_PACKAGE_NAMES, key=len, reverse=True))
)


def scan_deployment(root_dir: Path) -> list[DeploymentConfig]:
    """Scan for deployment artifacts in the project root."""
    configs: list[DeploymentConfig] = []

    for config_type, patterns in DEPLOYMENT_FILES.items():
        for pattern in patterns:
            for match in root_dir.glob(pattern):
                if match.is_file():
                    has_ai = _detect_ai_in_file(match)
                    configs.append(DeploymentConfig(
                        config_type=config_type,
                        file_path=str(match),
                        contains_ai_deps=has_ai,
                    ))

    # Check requirements.txt variants
    for req_file in ("requirements.txt", "requirements/base.txt", "requirements/prod.txt"):
        req_path = root_dir / req_file
        if req_path.is_file():
            has_ai = _detect_ai_in_file(req_path)
            if has_ai:
                configs.append(DeploymentConfig(
                    config_type="requirements",
                    file_path=str(req_path),
                    contains_ai_deps=True,
                ))

    # Check pyproject.toml
    pyproject = root_dir / "pyproject.toml"
    if pyproject.is_file():
        has_ai = _detect_ai_in_file(pyproject)
        if has_ai:
            configs.append(DeploymentConfig(
                config_type="pyproject",
                file_path=str(pyproject),
                contains_ai_deps=True,
            ))

    # Check setup.py / setup.cfg
    for setup_file in ("setup.py", "setup.cfg"):
        setup_path = root_dir / setup_file
        if setup_path.is_file():
            has_ai = _detect_ai_in_file(setup_path)
            if has_ai:
                configs.append(DeploymentConfig(
                    config_type="setup",
                    file_path=str(setup_path),
                    contains_ai_deps=True,
                ))

    # Check package.json
    pkg_json = root_dir / "package.json"
    if pkg_json.is_file():
        has_ai = _detect_ai_in_file(pkg_json)
        if has_ai:
            configs.append(DeploymentConfig(
                config_type="package_json",
                file_path=str(pkg_json),
                contains_ai_deps=True,
            ))

    return configs


def scan_dependency_files(root_dir: Path) -> list[AIImport]:
    """Extract AI dependencies from config files as AIImport entries.

    Scans requirements.txt, pyproject.toml, setup.py, setup.cfg, and
    package.json for AI package declarations. These are classified as
    "uses" since they're declared project dependencies, not optional
    integrations.
    """
    imports: list[AIImport] = []

    # Python dependency files
    py_dep_files = [
        root_dir / "requirements.txt",
        root_dir / "requirements/base.txt",
        root_dir / "requirements/prod.txt",
        root_dir / "pyproject.toml",
        root_dir / "setup.py",
        root_dir / "setup.cfg",
    ]
    for dep_file in py_dep_files:
        if dep_file.is_file():
            imports.extend(_extract_py_deps(dep_file))

    # JavaScript dependency files
    pkg_json = root_dir / "package.json"
    if pkg_json.is_file():
        imports.extend(_extract_js_deps(pkg_json))

    return imports


def _extract_py_deps(file_path: Path) -> list[AIImport]:
    """Extract AI package names from a Python dependency file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    found: list[AIImport] = []
    fp = str(file_path)

    for i, line in enumerate(content.splitlines(), 1):
        line_lower = line.strip().lower()
        # Skip comments and empty lines
        if not line_lower or line_lower.startswith("#") or line_lower.startswith(";"):
            continue
        # Check each known package
        for pkg, lib in _PY_PKG_TO_LIB.items():
            if pkg.lower() in line_lower:
                # Skip vectordb entries for now (handled separately)
                if lib.startswith("vectordb:"):
                    continue
                found.append(AIImport(
                    library=lib,
                    module_path=pkg,
                    file_path=fp,
                    line_number=i,
                    usage_type="uses",
                ))
                break

    return found


def _extract_js_deps(file_path: Path) -> list[AIImport]:
    """Extract AI package names from package.json."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    found: list[AIImport] = []
    fp = str(file_path)

    for i, line in enumerate(content.splitlines(), 1):
        for pkg, lib in _JS_PKG_TO_LIB.items():
            if f'"{pkg}"' in line or f"'{pkg}'" in line:
                if lib.startswith("vectordb:"):
                    continue
                found.append(AIImport(
                    library=lib,
                    module_path=pkg,
                    file_path=fp,
                    line_number=i,
                    usage_type="uses",
                ))
                break

    return found


def _detect_ai_in_file(file_path: Path) -> bool:
    """Check if a file references AI SDK packages."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_AI_DEP_PATTERN.search(content))
