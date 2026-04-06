"""Evidence pack generator: bundles compliance artifacts for auditors."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import ai_trace_auditor
from typing import Any

from ai_trace_auditor.comply.runner import CompliancePackage
from ai_trace_auditor.reports.comply_report import ComplyReporter


def generate_evidence_pack(pkg: CompliancePackage, output_dir: Path) -> list[Path]:
    """Generate a compliance evidence pack folder.

    Creates a structured directory that a compliance officer can zip
    and hand to an auditor. Contents:
      - README.md           (table of contents, disclaimers)
      - compliance-report.md (full Markdown report)
      - compliance-report.pdf (PDF version, if weasyprint available)
      - data-flow.mermaid   (Mermaid diagram source)
      - data-flow.svg       (rendered SVG, if mmdc available)
      - requirement-checklist.md (checkbox list per requirement)
      - metadata.json       (tool version, timestamp, settings)
      - article-12-audit.md (individual report, if traces provided)
      - article-11-docs.md  (Annex IV documentation)
      - article-13-flows.md (flow report + RoPA)

    Returns list of all created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    reporter = ComplyReporter()
    md_content = reporter.render(pkg)

    # 1. Split individual reports
    split_files = reporter.write_split(pkg, output_dir)
    created.extend(split_files)

    # 2. PDF report (optional: graceful fallback)
    pdf_path = _write_pdf(md_content, output_dir / "compliance-report.pdf")
    if pdf_path is not None:
        created.append(pdf_path)

    # 3. SVG diagram (optional: graceful fallback)
    if pkg.flow_diagram and pkg.flow_diagram.mermaid:
        svg_path = _render_svg(pkg.flow_diagram.mermaid, output_dir / "data-flow.svg")
        if svg_path is not None:
            created.append(svg_path)

    # 4. Requirement checklist
    checklist_path = output_dir / "requirement-checklist.md"
    checklist_path.write_text(_build_checklist(pkg), encoding="utf-8")
    created.append(checklist_path)

    # 5. Metadata
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(_build_metadata(pkg), indent=2),
        encoding="utf-8",
    )
    created.append(metadata_path)

    # 6. README (table of contents)
    readme_path = output_dir / "README.md"
    readme_path.write_text(_build_readme(created, pkg), encoding="utf-8")
    created.append(readme_path)

    return created


def _write_pdf(md_content: str, output_path: Path) -> Path | None:
    """Generate PDF from Markdown. Returns None if weasyprint unavailable."""
    try:
        from ai_trace_auditor.reports.pdf_report import check_pdf_available, markdown_to_pdf
    except (ImportError, OSError):
        # OSError: weasyprint system libraries (libgobject, libpango) not installed
        return None

    try:
        if not check_pdf_available():
            return None
        markdown_to_pdf(md_content, output_path)
        return output_path
    except (ImportError, OSError):
        # System library not found at runtime
        return None
    except Exception as exc:
        import sys
        print(f"[ai-trace-auditor] PDF generation failed: {exc}", file=sys.stderr)
        return None


def _render_svg(mermaid_source: str, output_path: Path) -> Path | None:
    """Render Mermaid to SVG using mmdc. Returns None if mmdc unavailable."""
    try:
        result = subprocess.run(
            ["mmdc", "-i", "/dev/stdin", "-o", str(output_path)],
            input=mermaid_source,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and output_path.exists():
            return output_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _build_checklist(pkg: CompliancePackage) -> str:
    """Build a Markdown checklist from requirement results."""
    lines = [
        "# Compliance Requirement Checklist",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Tool: AI Trace Auditor v{ai_trace_auditor.__version__}",
        "",
    ]

    if pkg.gap_report and pkg.gap_report.requirement_results:
        lines.append("## Article 12 -- Record-Keeping")
        lines.append("")
        for rr in pkg.gap_report.requirement_results:
            check = "x" if rr.status == "satisfied" else " "
            status_label = rr.status.upper()
            lines.append(f"- [{check}] **{rr.requirement.id}**: {rr.requirement.title} ({status_label})")
            if rr.gaps:
                for gap in rr.gaps:
                    lines.append(f"  - Gap: {gap.description}")
        lines.append("")

    # Article 11
    if pkg.annex_iv:
        lines.append("## Article 11 -- Technical Documentation (Annex IV)")
        lines.append("")
        pct = pkg.docs_completion_pct
        check = "x" if pct >= 80 else " "
        lines.append(f"- [{check}] Annex IV document generated ({pct:.0f}% auto-populated)")
        lines.append("")

    # Article 13 / GDPR
    if pkg.flow_scan:
        lines.append("## Article 13 -- Data Flow Transparency (Provider → Deployer)")
        lines.append("")
        lines.append(f"- [x] Data flow diagram: {len(pkg.flow_scan.data_flows)} flows mapped")
        lines.append(f"- [x] External services: {len(pkg.flow_scan.external_services)} identified")
        lines.append("")

    if pkg.ropa and pkg.ropa.entries:
        lines.append("## GDPR Article 30 -- Records of Processing Activities")
        lines.append("")
        lines.append(f"- [x] RoPA generated: {len(pkg.ropa.entries)} processing activities")
        lines.append("")

    return "\n".join(lines)


def _build_metadata(pkg: CompliancePackage) -> dict[str, Any]:
    """Build metadata dict for the evidence pack."""
    meta: dict = {
        "tool": "ai-trace-auditor",
        "version": ai_trace_auditor.__version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": pkg.source_dir,
        "risk_level": "high_risk",
        "articles_covered": pkg.articles_covered,
        "compliance_score": pkg.compliance_score,
        "warnings_count": len(pkg.warnings),
    }
    if pkg.gap_report:
        meta["trace_source"] = pkg.gap_report.trace_source
        meta["trace_count"] = pkg.gap_report.trace_count
        meta["span_count"] = pkg.gap_report.span_count
    return meta


def _build_readme(files: list[Path], pkg: CompliancePackage) -> str:
    """Build the evidence pack README with table of contents."""
    lines = [
        "# EU AI Act Compliance Evidence Pack",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Tool: [AI Trace Auditor](https://github.com/BipinRimal314/ai-trace-auditor) v{ai_trace_auditor.__version__}",
        f"Source: `{pkg.source_dir}`",
        "",
        "## Contents",
        "",
    ]

    descriptions = {
        "compliance-summary.md": "Full compliance report (Markdown)",
        "compliance-report.pdf": "Full compliance report (PDF)",
        "article-12-audit.md": "Article 12 record-keeping audit results",
        "article-11-docs.md": "Article 11 Annex IV technical documentation",
        "article-13-flows.md": "Article 13 data flow transparency (provider → deployer) + GDPR RoPA",
        "data-flow.mermaid": "Data flow diagram (Mermaid source)",
        "data-flow.svg": "Data flow diagram (rendered SVG)",
        "requirement-checklist.md": "Per-requirement pass/fail checklist",
        "metadata.json": "Generation metadata (version, timestamp, settings)",
    }

    for f in sorted(files, key=lambda p: p.name):
        desc = descriptions.get(f.name, f.name)
        lines.append(f"- **{f.name}** -- {desc}")

    lines.extend([
        "",
        "## Disclaimer",
        "",
        "This evidence pack is generated by automated static analysis and trace auditing. "
        "It does not constitute legal advice. Risk classification under Annex III requires "
        "legal review of your specific use case. Consult qualified counsel before relying "
        "on this output for regulatory submissions.",
        "",
        "## Articles Covered",
        "",
    ])

    for article in pkg.articles_covered:
        lines.append(f"- {article}")

    if pkg.warnings:
        lines.extend(["", "## Warnings", ""])
        for w in pkg.warnings:
            lines.append(f"- {w}")

    return "\n".join(lines)
