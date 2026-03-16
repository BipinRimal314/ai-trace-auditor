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
