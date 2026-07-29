"""Compare two JSON compliance reports and summarize progress/regressions.

Powers ``aitrace diff old.json new.json`` so teams can see whether logging
changes moved trace field coverage in the right direction between runs.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from ai_trace_auditor.models.gap import GapReport


class RequirementChange(BaseModel):
    """Status/score movement of one requirement between two reports."""

    id: str
    title: str
    regulation: str
    old_status: str
    new_status: str
    old_score: float
    new_score: float

    @property
    def score_delta(self) -> float:
        return self.new_score - self.old_score


class ReportDiff(BaseModel):
    """Structured comparison of two GapReports."""

    old_source: str
    new_source: str
    old_overall: float
    new_overall: float
    improved: list[RequirementChange]
    regressed: list[RequirementChange]
    added: list[str]
    removed: list[str]
    unchanged_count: int

    @property
    def overall_delta(self) -> float:
        return self.new_overall - self.old_overall

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressed) or self.overall_delta < 0


def load_report(path: Path) -> GapReport:
    """Load a GapReport from a JSON report file written by ``--report-format json``."""
    try:
        return GapReport.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(
            f"{path} is not a valid aitrace JSON report "
            f"(generate one with: aitrace audit traces.json --report-format json -o report.json): {e}"
        ) from e


_SCORE_EPSILON = 0.0005  # ignore sub-0.05pp float noise


def diff_reports(old: GapReport, new: GapReport) -> ReportDiff:
    """Compare two reports by requirement id."""
    old_by_id = {r.requirement.id: r for r in old.requirement_results}
    new_by_id = {r.requirement.id: r for r in new.requirement_results}

    improved: list[RequirementChange] = []
    regressed: list[RequirementChange] = []
    unchanged = 0

    for req_id in sorted(old_by_id.keys() & new_by_id.keys()):
        o, n = old_by_id[req_id], new_by_id[req_id]
        change = RequirementChange(
            id=req_id,
            title=n.requirement.title,
            regulation=n.requirement.regulation,
            old_status=o.status,
            new_status=n.status,
            old_score=o.coverage_score,
            new_score=n.coverage_score,
        )
        if n.coverage_score > o.coverage_score + _SCORE_EPSILON:
            improved.append(change)
        elif n.coverage_score < o.coverage_score - _SCORE_EPSILON:
            regressed.append(change)
        else:
            unchanged += 1

    return ReportDiff(
        old_source=old.trace_source,
        new_source=new.trace_source,
        old_overall=old.overall_score,
        new_overall=new.overall_score,
        improved=improved,
        regressed=regressed,
        added=sorted(new_by_id.keys() - old_by_id.keys()),
        removed=sorted(old_by_id.keys() - new_by_id.keys()),
        unchanged_count=unchanged,
    )


def render_diff_markdown(diff: ReportDiff) -> str:
    """Render a ReportDiff as a Markdown summary."""
    lines = [
        "# Compliance Report Diff",
        "",
        f"**Old:** {diff.old_source}",
        f"**New:** {diff.new_source}",
        "",
        f"**Trace field coverage:** {diff.old_overall * 100:.1f}% → "
        f"{diff.new_overall * 100:.1f}% ({diff.overall_delta * 100:+.1f}pp)",
        "",
    ]

    def _section(title: str, changes: list[RequirementChange]) -> None:
        if not changes:
            return
        lines.append(f"## {title} ({len(changes)})")
        lines.append("")
        lines.append("| Requirement | Regulation | Status | Coverage |")
        lines.append("|---|---|---|---|")
        for c in changes:
            status = (
                c.new_status.upper()
                if c.old_status == c.new_status
                else f"{c.old_status.upper()} → {c.new_status.upper()}"
            )
            lines.append(
                f"| {c.id}: {c.title} | {c.regulation} | {status} | "
                f"{c.old_score * 100:.1f}% → {c.new_score * 100:.1f}% |"
            )
        lines.append("")

    _section("Improved", diff.improved)
    _section("Regressed", diff.regressed)

    if diff.added:
        lines.append(f"## New requirements checked ({len(diff.added)})")
        lines.append("")
        lines.extend(f"- {req_id}" for req_id in diff.added)
        lines.append("")
    if diff.removed:
        lines.append(f"## No longer checked ({len(diff.removed)})")
        lines.append("")
        lines.extend(f"- {req_id}" for req_id in diff.removed)
        lines.append("")

    lines.append(f"{diff.unchanged_count} requirements unchanged.")
    lines.append("")
    return "\n".join(lines)
