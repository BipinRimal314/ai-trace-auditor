"""Serialization for compliance scoping intake profiles."""

from __future__ import annotations

from pathlib import Path
import yaml

from ai_trace_auditor.models.intake import IntakeProfile


def load_profile(path: Path) -> IntakeProfile:
    """Load an IntakeProfile from a YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Intake profile file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid intake profile format in {path}")

    # Pydantic v2 model validation
    return IntakeProfile.model_validate(data)


def save_profile(profile: IntakeProfile, path: Path) -> None:
    """Save an IntakeProfile to a YAML file."""
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    data = profile.model_dump()

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
