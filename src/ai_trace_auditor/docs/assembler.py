"""Assemble all Annex IV sections into a complete document."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_trace_auditor.docs.sections import (
    build_scope_check,
    build_section_1,
    build_section_2,
    build_section_3,
    build_section_4,
    build_section_5,
    build_section_6,
    build_section_7,
    build_section_8,
    build_section_9,
)
from ai_trace_auditor.models.docs import AnnexIVDocument, CodeScanResult
from ai_trace_auditor.models.gap import GapReport

_BUILDERS = [
    build_section_1,
    build_section_2,
    build_section_3,
    build_section_4,
    build_section_5,
    build_section_6,
    build_section_7,
    build_section_8,
    build_section_9,
]


def generate_annex_iv(
    scan: CodeScanResult,
    gap_report: GapReport | None = None,
) -> AnnexIVDocument:
    """Generate a complete Annex IV technical documentation package.

    Includes a scope check (Section 0) followed by the 9 Annex IV sections.

    Args:
        scan: Results from scanning the codebase.
        gap_report: Optional trace compliance report to enrich sections 3, 6, 9.

    Returns:
        An AnnexIVDocument with scope check + 9 sections.
    """
    sections = [build_scope_check(scan)]
    sections.extend(builder(scan, gap_report) for builder in _BUILDERS)

    return AnnexIVDocument(
        sections=sections,
        generated_at=datetime.now(timezone.utc),
        source_dir=scan.scanned_dir,
        scan_result=scan,
        trace_enriched=gap_report is not None,
    )
