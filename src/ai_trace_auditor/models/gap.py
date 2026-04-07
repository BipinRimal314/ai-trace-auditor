"""Gap report models for compliance analysis results."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ai_trace_auditor.models.evidence import EvidenceRecord
from ai_trace_auditor.models.requirement import Requirement


class GapDetail(BaseModel):
    """A specific compliance gap with actionable recommendation."""

    field_path: str
    description: str
    impact: str  # Why this matters for compliance
    recommendation: str  # What to do about it


class RequirementResult(BaseModel):
    """Analysis result for a single regulatory requirement."""

    requirement: Requirement
    status: str  # "satisfied", "partial", "missing", "not_applicable"
    evidence: list[EvidenceRecord] = []
    gaps: list[GapDetail] = []
    coverage_score: float = 0.0  # 0.0 - 1.0


class TieredScore(BaseModel):
    """Score for a single compliance tier."""

    tier: str  # "deterministic", "structural", "quality"
    label: str  # human-readable: "Legal Compliance", "Structural Evidence", "Quality"
    score: float = 0.0  # 0.0 - 1.0
    requirement_count: int = 0
    satisfied: int = 0
    gaps: int = 0


class GapSummary(BaseModel):
    """High-level summary of gap analysis results."""

    satisfied: int = 0
    partial: int = 0
    missing: int = 0
    not_applicable: int = 0
    top_gaps: list[str] = []


class GapReport(BaseModel):
    """Complete compliance gap analysis report."""

    generated_at: datetime
    trace_source: str
    trace_count: int
    span_count: int
    regulations_checked: list[str]
    overall_score: float  # 0.0 - 1.0
    requirement_results: list[RequirementResult]
    summary: GapSummary

    # Tiered scoring
    tiered_scores: list[TieredScore] = []

    # Multi-agent extensions
    agent_scores: dict[str, float] | None = None  # agent_id -> compliance score
    dag_mermaid: str | None = None  # Mermaid diagram source
