"""Tests for report diffing (aitrace diff)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_trace_auditor.cli import app
from ai_trace_auditor.models.gap import GapReport, GapSummary, RequirementResult
from ai_trace_auditor.models.requirement import Requirement
from ai_trace_auditor.reports.diff import diff_reports, load_report, render_diff_markdown

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _requirement(req_id: str) -> Requirement:
    return Requirement(
        id=req_id,
        regulation="EU AI Act",
        article="Article 12",
        title=f"Requirement {req_id}",
        description="test",
        evidence_fields=[],
    )


def _result(req_id: str, status: str, score: float) -> RequirementResult:
    return RequirementResult(
        requirement=_requirement(req_id),
        status=status,
        evidence=[],
        gaps=[],
        coverage_score=score,
    )


def _report(results: list[RequirementResult], overall: float, source: str = "t.json") -> GapReport:
    return GapReport(
        generated_at=datetime.now(timezone.utc),
        trace_source=source,
        trace_count=1,
        span_count=1,
        regulations_checked=["EU AI Act"],
        overall_score=overall,
        requirement_results=results,
        summary=GapSummary(
            satisfied=sum(1 for r in results if r.status == "satisfied"),
            partial=sum(1 for r in results if r.status == "partial"),
            missing=sum(1 for r in results if r.status == "missing"),
            not_applicable=0,
        ),
    )


def test_diff_classifies_changes():
    old = _report(
        [_result("A", "partial", 0.5), _result("B", "satisfied", 1.0), _result("C", "missing", 0.0)],
        overall=0.5,
    )
    new = _report(
        [_result("A", "satisfied", 1.0), _result("B", "partial", 0.5), _result("D", "missing", 0.0)],
        overall=0.5,
    )
    d = diff_reports(old, new)
    assert [c.id for c in d.improved] == ["A"]
    assert [c.id for c in d.regressed] == ["B"]
    assert d.added == ["D"]
    assert d.removed == ["C"]
    assert d.unchanged_count == 0
    assert d.has_regressions


def test_diff_identical_reports_has_no_changes():
    r = _report([_result("A", "partial", 0.5)], overall=0.5)
    d = diff_reports(r, r)
    assert not d.improved and not d.regressed
    assert d.unchanged_count == 1
    assert not d.has_regressions


def test_render_markdown_mentions_movement():
    old = _report([_result("A", "missing", 0.0)], overall=0.0)
    new = _report([_result("A", "satisfied", 1.0)], overall=1.0)
    md = render_diff_markdown(diff_reports(old, new))
    assert "MISSING → SATISFIED" in md
    assert "+100.0pp" in md


def test_load_report_rejects_non_report_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": "world"}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid aitrace JSON report"):
        load_report(bad)


def _write_json_report(runner: CliRunner, trace: Path, out: Path) -> None:
    result = runner.invoke(
        app, ["audit", str(trace), "--report-format", "json", "-o", str(out)]
    )
    assert result.exit_code in (0, 1)
    assert out.is_file()


def test_cli_diff_self_is_clean_and_exits_zero(tmp_path):
    runner = CliRunner()
    report = tmp_path / "r.json"
    _write_json_report(runner, FIXTURES / "otel_chat_trace.json", report)

    result = runner.invoke(app, ["diff", str(report), str(report)])
    assert result.exit_code == 0
    assert "unchanged" in result.stdout


def test_cli_diff_detects_regression_and_exits_one(tmp_path):
    runner = CliRunner()
    better = tmp_path / "better.json"
    worse = tmp_path / "worse.json"
    # The chat trace logs more fields than the multi-agent sample.
    _write_json_report(runner, FIXTURES / "otel_chat_trace.json", better)
    _write_json_report(runner, FIXTURES / "otel_multi_agent_trace.json", worse)

    regression = runner.invoke(app, ["diff", str(better), str(worse)])
    assert regression.exit_code == 1

    tolerated = runner.invoke(
        app, ["diff", str(better), str(worse), "--no-fail-on-regression"]
    )
    assert tolerated.exit_code == 0


def test_cli_diff_missing_file_exits_two(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["diff", str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    assert result.exit_code == 2
