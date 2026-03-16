"""Markdown report generation using Jinja2 templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import ai_trace_auditor
from ai_trace_auditor.models.gap import GapReport

TEMPLATES_DIR = Path(__file__).parent / "templates"


class MarkdownReporter:
    """Renders GapReport to Markdown using Jinja2 templates."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, report: GapReport) -> str:
        """Render a GapReport to a Markdown string."""
        template = self.env.get_template("compliance_report.md.jinja2")
        return template.render(
            report=report,
            version=ai_trace_auditor.__version__,
        )

    def write(self, report: GapReport, output_path: Path) -> None:
        """Render and write a GapReport to a Markdown file."""
        content = self.render(report)
        output_path.write_text(content, encoding="utf-8")
