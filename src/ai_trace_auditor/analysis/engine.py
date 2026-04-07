"""Core compliance analysis engine.

Orchestrates: traces + requirements -> field mapping -> scoring -> gap report.
Supports both single-agent and multi-agent traces. Multi-agent traces get
additional DAG analysis, per-agent scoring, and Article 25 requirements.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_trace_auditor.analysis.dag import (
    build_adjacency_list,
    build_delegation_paths,
    detect_circular_delegation,
    find_unsupervised_agents,
)
from ai_trace_auditor.analysis.field_mapper import resolve_field
from ai_trace_auditor.analysis.multi_agent_scorer import (
    compute_system_score,
    detect_liability_shifts,
    score_multi_agent_trace,
)
from ai_trace_auditor.analysis.scorer import (
    compute_requirement_score,
    determine_status,
    identify_gaps,
)
from ai_trace_auditor.models.gap import GapReport, GapSummary, RequirementResult, TieredScore
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

        Automatically detects multi-agent traces and enriches the report
        with per-agent scores, DAG analysis, and Article 25 requirements.
        """
        is_multi_agent = any(t.is_multi_agent for t in traces)

        # Get applicable requirements (filtered by multi-agent status)
        requirements = self.registry.get_applicable_for_trace(risk_level, is_multi_agent)
        if regulations:
            requirements = [r for r in requirements if r.regulation in regulations]

        # Enrich multi-agent traces with DAG data before analysis
        if is_multi_agent:
            self._enrich_multi_agent_traces(traces)

        # Analyze each requirement
        results: list[RequirementResult] = []
        for req in requirements:
            evidence = [resolve_field(traces, ef) for ef in req.evidence_fields]
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

        total_spans = sum(t.span_count for t in traces)
        scores = [r.coverage_score for r in results if r.status != "not_applicable"]
        overall = sum(scores) / len(scores) if scores else 0.0

        checked_regs = list({r.requirement.regulation for r in results})

        # Multi-agent enrichment
        agent_scores_dict: dict[str, float] | None = None
        if is_multi_agent:
            agent_scores_dict = self._compute_agent_scores(traces, results)

        tiered = self._compute_tiered_scores(results)

        return GapReport(
            generated_at=datetime.now(timezone.utc),
            trace_source=trace_source,
            trace_count=len(traces),
            span_count=total_spans,
            regulations_checked=sorted(checked_regs),
            overall_score=overall,
            requirement_results=results,
            summary=summary,
            tiered_scores=tiered,
            agent_scores=agent_scores_dict,
        )

    def _enrich_multi_agent_traces(self, traces: list[NormalizedTrace]) -> None:
        """Build DAGs and delegation paths for multi-agent traces."""
        for trace in traces:
            if not trace.is_multi_agent:
                continue

            # Build adjacency list
            adjacency = build_adjacency_list(trace)
            trace.dag_adjacency_list = adjacency

            # Build delegation paths and set on each span
            paths = build_delegation_paths(trace)
            for span in trace.spans:
                span.delegation_path = paths.get(span.span_id)

    def _compute_agent_scores(
        self,
        traces: list[NormalizedTrace],
        results: list[RequirementResult],
    ) -> dict[str, float]:
        """Compute per-agent compliance scores across all multi-agent traces."""
        all_agent_scores: dict[str, float] = {}

        for trace in traces:
            if not trace.is_multi_agent:
                continue
            agent_scores = score_multi_agent_trace(trace, results)
            for agent_id, score in agent_scores.items():
                all_agent_scores[agent_id] = score.final_score

        return all_agent_scores if all_agent_scores else None

    def _compute_tiered_scores(
        self, results: list[RequirementResult]
    ) -> list[TieredScore]:
        """Compute separate scores per compliance tier."""
        tier_config = {
            "deterministic": "Legal Compliance",
            "structural": "Structural Evidence",
            "quality": "Quality",
        }
        tier_results: dict[str, list[RequirementResult]] = {t: [] for t in tier_config}

        for r in results:
            tier = r.requirement.compliance_tier
            if tier in tier_results:
                tier_results[tier].append(r)

        tiered: list[TieredScore] = []
        for tier_name, label in tier_config.items():
            rr = tier_results[tier_name]
            if not rr:
                continue
            active = [r for r in rr if r.status != "not_applicable"]
            scores = [r.coverage_score for r in active]
            avg = sum(scores) / len(scores) if scores else 0.0
            tiered.append(
                TieredScore(
                    tier=tier_name,
                    label=label,
                    score=avg,
                    requirement_count=len(rr),
                    satisfied=sum(1 for r in rr if r.status == "satisfied"),
                    gaps=sum(1 for r in rr if r.status in ("partial", "missing")),
                )
            )
        return tiered

    def _extract_top_gaps(
        self, results: list[RequirementResult], max_gaps: int = 5
    ) -> list[str]:
        """Extract the most critical gaps across all requirements."""
        all_gaps: list[tuple[float, str]] = []

        for result in results:
            for gap in result.gaps:
                priority = 1.0 - result.coverage_score
                all_gaps.append((priority, gap.description))

        all_gaps.sort(reverse=True)
        return [desc for _, desc in all_gaps[:max_gaps]]
