"""Deployment artifact scanner (Dockerfiles, compose, k8s, terraform)."""

from __future__ import annotations

import re
from pathlib import Path

from ai_trace_auditor.models.docs import DeploymentConfig
from ai_trace_auditor.scanner.patterns import AI_SDK_IMPORTS, DEPLOYMENT_FILES, JS_AI_IMPORTS

# Packages to look for in deployment files (pip install X, npm install X, etc.)
_AI_PACKAGE_NAMES: set[str] = set()
for modules in AI_SDK_IMPORTS.values():
    _AI_PACKAGE_NAMES.update(modules)
for packages in JS_AI_IMPORTS.values():
    _AI_PACKAGE_NAMES.update(packages)

_AI_DEP_PATTERN = re.compile(
    "|".join(re.escape(pkg) for pkg in sorted(_AI_PACKAGE_NAMES, key=len, reverse=True))
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

    # Also check requirements.txt and package.json at root
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


def _detect_ai_in_file(file_path: Path) -> bool:
    """Check if a file references AI SDK packages."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_AI_DEP_PATTERN.search(content))
