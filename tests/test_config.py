"""Tests for .aitrace.toml config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trace_auditor.config import (
    AiTraceConfig,
    CIConfig,
    load_config,
    merge_config_with_cli,
)


def test_load_valid_config(tmp_path: Path) -> None:
    """A valid .aitrace.toml is parsed into AiTraceConfig."""
    config_file = tmp_path / ".aitrace.toml"
    config_file.write_text(
        'risk_level = "limited_risk"\n'
        'report_format = "pdf"\n'
        "split = true\n"
        'trace_format = "otel"\n'
        "\n"
        "[ci]\n"
        "fail_on_gaps = false\n"
    )

    cfg = load_config(tmp_path)

    assert cfg is not None
    assert cfg.risk_level == "limited_risk"
    assert cfg.report_format == "pdf"
    assert cfg.split is True
    assert cfg.trace_format == "otel"
    assert cfg.ci.fail_on_gaps is False


def test_load_returns_none_when_missing(tmp_path: Path) -> None:
    """Returns None when no .aitrace.toml exists anywhere up the tree."""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)

    assert load_config(deep) is None


def test_walks_up_directories(tmp_path: Path) -> None:
    """Config is found by walking up from a subdirectory."""
    config_file = tmp_path / ".aitrace.toml"
    config_file.write_text('risk_level = "minimal_risk"\n')

    nested = tmp_path / "src" / "app"
    nested.mkdir(parents=True)

    cfg = load_config(nested)

    assert cfg is not None
    assert cfg.risk_level == "minimal_risk"


def test_cli_overrides_config() -> None:
    """CLI kwargs take precedence over config values."""
    cfg = AiTraceConfig(risk_level="limited_risk", report_format="pdf")

    merged = merge_config_with_cli(cfg, risk_level="high_risk", report_format=None)

    assert merged["risk_level"] == "high_risk"
    assert merged["report_format"] == "pdf"  # falls back to config


def test_merge_with_none_config() -> None:
    """When config is None, CLI kwargs pass through unchanged."""
    result = merge_config_with_cli(None, risk_level="high_risk", output=None)

    assert result == {"risk_level": "high_risk", "output": None}


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    """Unknown TOML keys are silently ignored for forward compatibility."""
    config_file = tmp_path / ".aitrace.toml"
    config_file.write_text(
        'risk_level = "high_risk"\n'
        'future_feature = "some_value"\n'
        "another_unknown = 42\n"
    )

    cfg = load_config(tmp_path)

    assert cfg is not None
    assert cfg.risk_level == "high_risk"


def test_invalid_toml_raises(tmp_path: Path) -> None:
    """Malformed TOML produces a clear error."""
    config_file = tmp_path / ".aitrace.toml"
    config_file.write_text("this is not valid toml [[[")

    with pytest.raises(Exception):
        load_config(tmp_path)


def test_defaults_applied(tmp_path: Path) -> None:
    """An empty config file uses all defaults."""
    config_file = tmp_path / ".aitrace.toml"
    config_file.write_text("")

    cfg = load_config(tmp_path)

    assert cfg is not None
    assert cfg.risk_level == "high_risk"
    assert cfg.report_format == "markdown"
    assert cfg.trace_format == "auto"
    assert cfg.split is False
    assert cfg.ci.fail_on_gaps is True


def test_custom_requirements_loaded(tmp_path: Path) -> None:
    """custom_requirements paths are preserved from config."""
    config_file = tmp_path / ".aitrace.toml"
    config_file.write_text(
        'custom_requirements = ["./internal-policies/", "./iso_42001/"]\n'
    )

    cfg = load_config(tmp_path)

    assert cfg is not None
    assert cfg.custom_requirements == ["./internal-policies/", "./iso_42001/"]
