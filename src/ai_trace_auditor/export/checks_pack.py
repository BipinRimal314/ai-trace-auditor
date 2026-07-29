"""Export the requirement registry as a portable, machine-readable checks pack.

The checks pack is a public JSON artifact (``spec/checks-pack-v1.json``)
enumerating every check the auditor runs: framework, article, clause
citation, severity, scope tags, and the trace fields inspected. Any tool
can validate against it; it is the "deterministic + cited" claim in a
form that doesn't require running the CLI.

The output is deliberately deterministic (sorted by check id, no
timestamps) so regenerating it produces a meaningful git diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import ai_trace_auditor
from ai_trace_auditor.regulations.registry import RequirementRegistry

CHECKS_PACK_VERSION = 1


def build_checks_pack(registry: RequirementRegistry) -> dict:
    """Build the checks pack document from a loaded registry."""
    checks = []
    for req in sorted(registry.get_all(), key=lambda r: r.id):
        checks.append(
            {
                "id": req.id,
                "framework": req.regulation,
                "framework_nature": req.framework_nature,
                "article": req.article,
                "clause": req.legal_text,
                "title": req.title,
                "description": req.description,
                "severity": req.severity,
                "check_type": req.check_type,
                "compliance_tier": req.compliance_tier,
                "applies_to": req.applies_to,
                "verified_against_primary": req.verified_against_primary,
                "what_we_look_for": [
                    {
                        "field_path": ef.field_path,
                        "description": ef.description,
                        "required": ef.required,
                        "check_type": ef.check_type,
                        "legal_basis": ef.legal_basis,
                    }
                    for ef in req.evidence_fields
                ],
            }
        )

    frameworks: dict[str, int] = {}
    for check in checks:
        frameworks[check["framework"]] = frameworks.get(check["framework"], 0) + 1

    return {
        "checks_pack_version": CHECKS_PACK_VERSION,
        "generated_by": f"ai-trace-auditor v{ai_trace_auditor.__version__}",
        "description": (
            "Machine-readable registry of every compliance check AI Trace "
            "Auditor runs. Each check cites its framework, article, and "
            "clause; checks marked verified_against_primary have their "
            "quotes validated verbatim against the pinned primary source "
            "document in CI."
        ),
        "total_checks": len(checks),
        "verified_against_primary_count": sum(
            1 for c in checks if c["verified_against_primary"]
        ),
        "frameworks": dict(sorted(frameworks.items())),
        "checks": checks,
    }


def write_checks_pack(registry: RequirementRegistry, output_path: Path) -> dict:
    """Build and write the checks pack JSON; returns the document."""
    pack = build_checks_pack(registry)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return pack
