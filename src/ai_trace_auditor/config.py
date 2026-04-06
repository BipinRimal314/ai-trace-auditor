"""Project-level configuration via .aitrace.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class CIConfig(BaseModel):
    """CI/CD-specific settings."""

    fail_on_gaps: bool = True
    slack_webhook: str | None = None
    email_to: str | None = None
    schedule: str | None = None


class AiTraceConfig(BaseModel):
    """Project-level configuration loaded from .aitrace.toml."""

    regulation: list[str] | None = None
    risk_level: str = "high_risk"
    output_format: str = "markdown"
    report_format: str = "markdown"
    traces_path: str | None = None
    trace_format: str = "auto"
    output_path: str | None = None
    split: bool = False
    custom_requirements: list[str] | None = None
    ci: CIConfig = CIConfig()


CONFIG_FILENAME = ".aitrace.toml"


def load_config(start_dir: Path) -> AiTraceConfig | None:
    """Load .aitrace.toml by walking up from start_dir to filesystem root.

    Returns None if no config file is found.
    """
    current = start_dir.resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return _parse_config(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _parse_config(path: Path) -> AiTraceConfig:
    """Parse a .aitrace.toml file into an AiTraceConfig."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Flatten [ci] section into CIConfig
    ci_data = raw.pop("ci", {})
    ci = CIConfig(**{k: v for k, v in ci_data.items() if k in CIConfig.model_fields})

    # Filter to known fields only (forward compatibility: ignore unknown keys)
    known = AiTraceConfig.model_fields
    filtered = {k: v for k, v in raw.items() if k in known}
    filtered["ci"] = ci

    return AiTraceConfig(**filtered)


def merge_config_with_cli(
    config: AiTraceConfig | None,
    **cli_kwargs: Any,
) -> dict[str, Any]:
    """Merge config file values with CLI arguments.

    CLI arguments take precedence. A CLI value is considered "set" if it
    differs from the typer default (non-None for Optional fields, non-default
    for others).
    """
    if config is None:
        return cli_kwargs

    base = config.model_dump()

    # CLI overrides config: only apply CLI value if it was explicitly provided
    # (not None for Optional fields, not the default value)
    merged = {}
    for key, cli_val in cli_kwargs.items():
        if cli_val is not None:
            merged[key] = cli_val
        elif key in base:
            merged[key] = base[key]
        else:
            merged[key] = cli_val

    return merged
