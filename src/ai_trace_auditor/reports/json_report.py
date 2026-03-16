"""JSON report output."""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.models.gap import GapReport


class JSONReporter:
    """Renders GapReport to JSON."""

    def render(self, report: GapReport) -> str:
        return report.model_dump_json(indent=2)

    def write(self, report: GapReport, output_path: Path) -> None:
        output_path.write_text(self.render(report), encoding="utf-8")
