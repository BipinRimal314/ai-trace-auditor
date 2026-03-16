"""Core compliance analysis engine.

Orchestrates: traces + requirements -> field mapping -> scoring -> gap report.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_trace_auditor.analysis.field_mapper import resolve_field
from ai_trace_auditor.analysis.scorer import (
    compute_requirement_score,
    determine_status,
    identify_gaps,
)
from ai_trace_auditor.models.gap import GapReport, GapSummary, RequirementResult
from ai_trace_auditor.models.trace import NormalizedTrace
from ai_trace_auditor.regulations.registry import RequirementRegistry


class ComplianceAnalyzer:
    """Analyzes traces against regulatory requirements and produces gap reports."""

    def __init__(self, registry: RequirementRegistry) -> None:
        self.registry = registry

    def analyze(
        self,
        traces: list[NormalizedTrace],
        regulations: list[str] | None = None,
        risk_level: str = "high_risk",
        trace_source: str = "unknown",
    ) -> GapReport:
        """Run compliance analysis on normalized traces.

        Args:
            traces: Normalized traces to analyze.
            regulations: Filter to specific regulations (e.g., ["EU AI Act"]).
                         None = check all loaded regulations.
            risk_level: Risk classification for filtering requirements.
            trace_source: Description of the trace source for the report.

        Returns:
            A GapReport with per-requirement results and overall score.
        """
        # Get applicable requirements
        requirements = self.registry.get_applicable(risk_level)
        if regulations:
            requirements = [r for r in requirements if r.regulation in regulations]

        # Analyze each requirement
        results: list[RequirementResult] = []
        for req in requirements:
            # Resolve evidence fields against traces
            evidence = [resolve_field(traces, ef) for ef in req.evidence_fields]

            # Score and identify gaps
            score = compute_requirement_score(req, evidence)
            status = determine_status(score)
            gaps = identify_gaps(req, evidence)

            results.append(
                RequirementResult(
                    requirement=req,
                    status=status,
                    evidence=evidence,
                    gaps=gaps,
                    coverage_score=score,
                )
            )

        # Compute summary
        summary = GapSummary(
            satisfied=sum(1 for r in results if r.status == "satisfied"),
            partial=sum(1 for r in results if r.status == "partial"),
            missing=sum(1 for r in results if r.status == "missing"),
            not_applicable=sum(1 for r in results if r.status == "not_applicable"),
            top_gaps=self._extract_top_gaps(results),
        )

        # Overall score
        total_spans = sum(t.span_count for t in traces)
        scores = [r.coverage_score for r in results if r.status != "not_applicable"]
        overall = sum(scores) / len(scores) if scores else 0.0

        checked_regs = list({r.requirement.regulation for r in results})

        return GapReport(
            generated_at=datetime.now(timezone.utc),
            trace_source=trace_source,
            trace_count=len(traces),
            span_count=total_spans,
            regulations_checked=sorted(checked_regs),
            overall_score=overall,
            requirement_results=results,
            summary=summary,
        )

    def _extract_top_gaps(
        self, results: list[RequirementResult], max_gaps: int = 5
    ) -> list[str]:
        """Extract the most critical gaps across all requirements."""
        all_gaps: list[tuple[float, str]] = []

        for result in results:
            for gap in result.gaps:
                # Priority: missing required fields first, then low coverage
                priority = 1.0 - result.coverage_score
                all_gaps.append((priority, gap.description))

        all_gaps.sort(reverse=True)
        return [desc for _, desc in all_gaps[:max_gaps]]
