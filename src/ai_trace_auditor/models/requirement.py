"""Regulatory requirement models."""

from __future__ import annotations

from pydantic import BaseModel


class EvidenceField(BaseModel):
    """Defines what trace data satisfies a regulatory requirement."""

    field_path: str  # e.g., "spans[].start_time", "spans[].model_used"
    description: str
    required: bool = True
    check_type: str = "non_null"  # "present", "non_null", "non_empty", "retention"
    check_params: dict[str, int | float | str] | None = None
    note: str | None = None  # e.g., "Implementation guidance — not a legal requirement"


class Requirement(BaseModel):
    """A single regulatory requirement that can be checked against trace data."""

    id: str  # "EU-AIA-12.1", "NIST-MEASURE-2.4"
    regulation: str  # "EU AI Act", "NIST AI RMF"
    article: str  # "Article 12", "MEASURE 2.4"
    title: str
    description: str
    evidence_fields: list[EvidenceField]
    severity: str = "mandatory"  # "mandatory", "recommended", "best_practice"
    applies_to: list[str] | None = None  # ["high_risk", "all", "biometric"]
    legal_text: str | None = None  # exact clause ref, e.g. "Article 12(2)(a)"
    framework_nature: str | None = None  # "law", "voluntary", "certifiable_standard", "audit_framework"
    check_type: str | None = None  # "deterministic", "organizational" — organizational can't be trace-verified
    verified_against_primary: bool = False
    compliance_tier: str | None = None  # "deterministic" | "structural" | "quality"
