"""Flow analysis report renderer using Jinja2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import ai_trace_auditor
from ai_trace_auditor.models.flow import FlowDiagram, FlowScanResult, RoPAReport

TEMPLATES_DIR = Path(__file__).parent / "templates"


class FlowReporter:
    """Renders flow analysis results to Markdown."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(
        self,
        diagram: FlowDiagram,
        ropa: RoPAReport,
    ) -> str:
        """Render a flow diagram and RoPA to Markdown."""
        template = self.env.get_template("flow_report.md.jinja2")

        # Build lookup for flows by destination
        flows_by_dest = {f.destination: f for f in diagram.flows}

        return template.render(
            report=diagram,
            ropa=ropa,
            flows_by_dest=flows_by_dest,
            version=ai_trace_auditor.__version__,
        )

    def write(
        self,
        diagram: FlowDiagram,
        ropa: RoPAReport,
        output_path: Path,
    ) -> None:
        """Render and write to file."""
        content = self.render(diagram, ropa)
        output_path.write_text(content, encoding="utf-8")
