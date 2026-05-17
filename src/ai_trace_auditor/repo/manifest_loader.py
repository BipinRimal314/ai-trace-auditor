"""Load and validate governance-doc manifest entries."""

from __future__ import annotations

from pathlib import Path

import yaml

from ai_trace_auditor.repo.models import DocCheck

_REQUIRED_FIELDS = (
    "id",
    "legal_text",
    "verified_against_primary",
    "framework_nature",
    "compliance_tier",
    "regulation",
    "article",
    "detector_kind",
    "detector_config",
    "evidence_when_present",
    "evidence_when_absent",
)


def load_manifest(path: Path) -> list[DocCheck]:
    """Load and validate the manifest YAML at ``path``.

    Raises ValueError if any entry is missing a required field, has an
    unknown detector kind, or if the file is empty.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Manifest file has no entries (or is empty): {path}")

    if not isinstance(data, list):
        raise ValueError(f"Manifest root must be a list, got {type(data).__name__}")

    checks: list[DocCheck] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry #{index} is not a mapping")
        for field in _REQUIRED_FIELDS:
            if field not in entry:
                raise ValueError(
                    f"Manifest entry #{index} ({entry.get('id', '<unknown>')}) "
                    f"missing required field '{field}'"
                )
        try:
            checks.append(DocCheck(**entry))
        except TypeError as exc:
            raise ValueError(
                f"Manifest entry #{index} ({entry.get('id', '<unknown>')}): {exc}"
            ) from exc

    return checks
