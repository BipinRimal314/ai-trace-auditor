"""Tests for built-in profile presets and --profile CLI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_trace_auditor.cli import app
from ai_trace_auditor.models.intake import IntakeProfile
from ai_trace_auditor.profiles.presets import (
    PRESETS,
    get_preset,
    preset_names,
    preset_rationale,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_preset_names_match_development_plan():
    assert preset_names() == ["agent", "chatbot", "high-risk", "rag-pipeline"]


def test_get_preset_returns_copy():
    a = get_preset("chatbot")
    a.is_high_risk = True
    assert PRESETS["chatbot"].is_high_risk is False


def test_get_preset_unknown_name_lists_available():
    with pytest.raises(ValueError, match="agent, chatbot, high-risk, rag-pipeline"):
        get_preset("nope")


def test_every_preset_has_rationale():
    for name in preset_names():
        assert preset_rationale(name), f"missing rationale for {name}"


def test_high_risk_preset_is_high_risk():
    assert get_preset("high-risk").is_high_risk is True
    assert get_preset("chatbot").is_high_risk is False
    assert get_preset("agent").is_multi_agent is True


def test_cli_profile_scopes_requirements():
    """A non-high-risk profile must check fewer requirements than the full dump."""
    runner = CliRunner()
    trace = str(FIXTURES / "otel_multi_agent_trace.json")

    full = runner.invoke(app, ["audit", trace])
    scoped = runner.invoke(app, ["audit", trace, "--profile", "chatbot"])

    assert full.exit_code in (0, 1)
    assert scoped.exit_code in (0, 1)
    assert "**Profile:** chatbot" in scoped.stdout
    assert "Why these requirements apply" in scoped.stdout

    def satisfied_count(out: str) -> int:
        for line in out.splitlines():
            if line.startswith("| Satisfied |"):
                return int(line.split("|")[2].strip())
        raise AssertionError("no satisfied row found")

    assert satisfied_count(scoped.stdout) < satisfied_count(full.stdout)


def test_cli_profile_unknown_name_exits_2():
    runner = CliRunner()
    trace = str(FIXTURES / "otel_multi_agent_trace.json")
    result = runner.invoke(app, ["audit", trace, "--profile", "nope"])
    assert result.exit_code == 2
    # No report should have been rendered.
    assert "Trace Field Coverage" not in result.stdout


def test_cli_profile_from_yaml_file(tmp_path):
    from ai_trace_auditor.intake.serializer import save_profile

    profile_path = tmp_path / "my_profile.yaml"
    save_profile(
        IntakeProfile(system_name="custom-sys", is_human_interaction=True),
        profile_path,
    )
    runner = CliRunner()
    trace = str(FIXTURES / "otel_multi_agent_trace.json")
    result = runner.invoke(app, ["audit", trace, "--profile", str(profile_path)])
    assert result.exit_code in (0, 1)
    assert "**Profile:** custom-sys" in result.stdout


def test_multi_agent_trace_keeps_article_25_even_with_single_agent_profile():
    """Trace evidence outranks the declared profile for multi-agent checks."""
    runner = CliRunner()
    trace = str(FIXTURES / "otel_multi_agent_trace.json")
    result = runner.invoke(app, ["audit", trace, "--profile", "chatbot"])
    assert result.exit_code in (0, 1)
    assert "Per-Agent Compliance Scores" in result.stdout
