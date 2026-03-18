"""Annex IV documentation report renderer using Jinja2."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import ai_trace_auditor
from ai_trace_auditor.models.docs import AnnexIVDocument

TEMPLATES_DIR = Path(__file__).parent / "templates"


class DocsReporter:
    """Renders AnnexIVDocument to Markdown using Jinja2 templates."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, doc: AnnexIVDocument) -> str:
        """Render an AnnexIVDocument to a Markdown string."""
        template = self.env.get_template("annex_iv_docs.md.jinja2")
        return template.render(
            doc=doc,
            version=ai_trace_auditor.__version__,
        )

    def write(self, doc: AnnexIVDocument, output_path: Path) -> None:
        """Render and write an AnnexIVDocument to a Markdown file."""
        content = self.render(doc)
        output_path.write_text(content, encoding="utf-8")
