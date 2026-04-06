"""Tests for email notification formatting."""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.comply.runner import run_full_compliance
from ai_trace_auditor.notify.email_notify import format_email_body


SAMPLE_CODEBASE = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


def _get_pkg():
    return run_full_compliance(SAMPLE_CODEBASE)


def test_body_has_header() -> None:
    """Email body starts with the report title."""
    body = format_email_body(_get_pkg())
    assert body.startswith("EU AI Act Compliance Report")


def test_body_includes_source() -> None:
    """Email body mentions the source directory."""
    body = format_email_body(_get_pkg())
    assert "sample_codebase" in body


def test_body_includes_articles() -> None:
    """Email body lists covered articles."""
    body = format_email_body(_get_pkg())
    assert "Article 11" in body
