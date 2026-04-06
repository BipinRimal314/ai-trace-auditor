"""Tests for Slack notification formatting."""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.comply.runner import run_full_compliance
from ai_trace_auditor.notify.slack import format_slack_message


SAMPLE_CODEBASE = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


def _get_pkg():
    return run_full_compliance(SAMPLE_CODEBASE)


def test_format_has_blocks() -> None:
    """Slack message contains Block Kit blocks."""
    msg = format_slack_message(_get_pkg())
    assert "blocks" in msg
    assert len(msg["blocks"]) >= 2


def test_header_block_present() -> None:
    """First block is a header with the report title."""
    msg = format_slack_message(_get_pkg())
    header = msg["blocks"][0]
    assert header["type"] == "header"
    assert "Compliance" in header["text"]["text"]


def test_fields_include_source() -> None:
    """Section blocks include the source directory."""
    msg = format_slack_message(_get_pkg())
    all_text = str(msg)
    assert "sample_codebase" in all_text
