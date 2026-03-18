"""Unified compliance package report renderer."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import ai_trace_auditor
from ai_trace_auditor.comply.runner import CompliancePackage

TEMPLATES_DIR = Path(__file__).parent / "templates"


class ComplyReporter:
    """Renders a full CompliancePackage to Markdown."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, pkg: CompliancePackage) -> str:
        """Render the full compliance package to a single Markdown document."""
        template = self.env.get_template("compliance_package.md.jinja2")
        flows_by_dest = {}
        if pkg.flow_diagram:
            flows_by_dest = {f.destination: f for f in pkg.flow_diagram.flows}

        return template.render(
            pkg=pkg,
            flows_by_dest=flows_by_dest,
            version=ai_trace_auditor.__version__,
        )

    def write(self, pkg: CompliancePackage, output_path: Path) -> None:
        """Render and write to file."""
        content = self.render(pkg)
        output_path.write_text(content, encoding="utf-8")

    def write_split(self, pkg: CompliancePackage, output_dir: Path) -> list[Path]:
        """Write individual reports to a directory.

        Creates:
          - compliance-summary.md  (overview)
          - article-12-audit.md    (if traces provided)
          - article-11-docs.md     (Annex IV)
          - article-13-flows.md    (data flow + RoPA)
          - data-flow.mermaid      (diagram source)

        Returns list of created file paths.
        """
        from ai_trace_auditor.reports.docs_report import DocsReporter
        from ai_trace_auditor.reports.flow_report import FlowReporter
        from ai_trace_auditor.reports.markdown import MarkdownReporter

        output_dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []

        # Summary
        summary_path = output_dir / "compliance-summary.md"
        summary_path.write_text(self.render(pkg), encoding="utf-8")
        created.append(summary_path)

        # Article 12
        if pkg.gap_report:
            audit_path = output_dir / "article-12-audit.md"
            md = MarkdownReporter().render(pkg.gap_report)
            audit_path.write_text(md, encoding="utf-8")
            created.append(audit_path)

        # Article 11
        if pkg.annex_iv:
            from ai_trace_auditor.reports.docs_report import DocsReporter
            docs_path = output_dir / "article-11-docs.md"
            DocsReporter().write(pkg.annex_iv, docs_path)
            created.append(docs_path)

        # Article 13 + GDPR
        if pkg.flow_diagram and pkg.ropa:
            flow_path = output_dir / "article-13-flows.md"
            FlowReporter().write(pkg.flow_diagram, pkg.ropa, flow_path)
            created.append(flow_path)

            # Raw Mermaid
            mermaid_path = output_dir / "data-flow.mermaid"
            mermaid_path.write_text(pkg.flow_diagram.mermaid, encoding="utf-8")
            created.append(mermaid_path)

        return created
