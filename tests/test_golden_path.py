"""Acceptance tests for the golden path demo (examples/golden_path/).

These mirror the acceptance criteria in DEVELOPMENT.md: a fresh user must
be able to run one command on the committed sample and get a readable
report containing both satisfied and gap findings with article citations.
"""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from ai_trace_auditor.cli import app

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "examples" / "golden_path"


def test_golden_path_files_are_committed():
    assert (GOLDEN_PATH / "sample_traces.json").is_file()
    assert (GOLDEN_PATH / "sample_report.md").is_file()
    assert (GOLDEN_PATH / "README.md").is_file()


def test_golden_path_audit_writes_report(tmp_path):
    report_path = tmp_path / "report.md"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["audit", str(GOLDEN_PATH / "sample_traces.json"), "-o", str(report_path)],
    )
    # Exit 1 means gaps were found, which the sample intentionally contains.
    assert result.exit_code in (0, 1), f"unexpected exit: {result.exit_code}, stdout={result.stdout}"
    assert report_path.is_file()

    report = report_path.read_text(encoding="utf-8")
    assert "SATISFIED" in report
    assert "MISSING" in report or "PARTIAL" in report
    # At least one EU AI Act article citation in the requirement details.
    assert re.search(r"EU AI Act Article \d+", report)


def test_committed_sample_report_matches_acceptance_criteria():
    report = (GOLDEN_PATH / "sample_report.md").read_text(encoding="utf-8")
    assert "SATISFIED" in report
    assert "MISSING" in report or "PARTIAL" in report
    assert re.search(r"EU AI Act Article \d+", report)
    # Multi-agent differentiator: per-agent scores are present.
    assert "Per-Agent Compliance Scores" in report
