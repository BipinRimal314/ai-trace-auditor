"""Tests for multi-agent compliance scorer with penalty propagation."""

from __future__ import annotations

import pytest

from ai_trace_auditor.analysis.multi_agent_scorer import (
    AgentScore,
    compute_system_score,
    detect_liability_shifts,
    score_multi_agent_trace,
)
from ai_trace_auditor.models.evidence import EvidenceRecord
from ai_trace_auditor.models.gap import RequirementResult
from ai_trace_auditor.models.requirement import EvidenceField, Requirement
from ai_trace_auditor.models.trace import NormalizedSpan, NormalizedTrace


def _span(
    span_id: str,
    parent: str | None = None,
    agent_id: str | None = None,
    agent_name: str | None = None,
    model_used: str | None = None,
    agent_framework: str | None = None,
    operation: str = "chat",
) -> NormalizedSpan:
    return NormalizedSpan(
        span_id=span_id,
        parent_span_id=parent,
        operation=operation,
        agent_id=agent_id,
        agent_name=agent_name,
        model_used=model_used,
        agent_framework=agent_framework,
    )


def _trace(spans: list[NormalizedSpan]) -> NormalizedTrace:
    return NormalizedTrace(trace_id="test", spans=spans, source_format="test")


def _requirement_result(coverage: float, status: str = "partial") -> RequirementResult:
    req = Requirement(
        id="test-req",
        regulation="EU AI Act",
        article="Article 12",
        title="Test",
        description="Test requirement",
        evidence_fields=[
            EvidenceField(field_path="spans[].start_time", description="timestamp")
        ],
    )
    return RequirementResult(
        requirement=req,
        status=status,
        evidence=[
            EvidenceRecord(
                field_path="spans[].start_time",
                population=10,
                present_count=int(coverage * 10),
                coverage_pct=coverage,
            )
        ],
        coverage_score=coverage,
    )


class TestScoreMultiAgentTrace:
    def test_single_agent_no_penalty(self):
        trace = _trace([_span("s1", agent_id="solo")])
        results = [_requirement_result(1.0, "satisfied")]
        scores = score_multi_agent_trace(trace, results)

        assert "solo" in scores
        assert scores["solo"].own_score == 1.0
        assert scores["solo"].delegated_penalty == 0.0
        assert scores["solo"].final_score == 1.0

    def test_two_agents_leaf_fails(self):
        trace = _trace([
            _span("s1", agent_id="agent-a"),
            _span("s2", parent="s1", agent_id="agent-b"),
        ])
        # Low coverage = agent-b fails
        results = [_requirement_result(0.3, "partial")]
        scores = score_multi_agent_trace(trace, results)

        assert scores["agent-b"].own_score == 0.3
        # agent-a should be penalized for delegating to a failing agent
        assert scores["agent-a"].delegated_penalty > 0.0
        assert scores["agent-a"].final_score < scores["agent-a"].own_score

    def test_penalty_clamped_to_zero(self):
        trace = _trace([
            _span("s1", agent_id="agent-a"),
            _span("s2", parent="s1", agent_id="agent-b"),
        ])
        # Zero coverage = total failure
        results = [_requirement_result(0.0, "missing")]
        scores = score_multi_agent_trace(trace, results)

        assert scores["agent-a"].final_score >= 0.0

    def test_system_score_weighted_by_span_count(self):
        score_a = AgentScore(
            agent_id="a", agent_name=None, own_score=1.0,
            delegated_penalty=0.0, final_score=1.0, violation_count=0, span_count=10,
        )
        score_b = AgentScore(
            agent_id="b", agent_name=None, own_score=0.0,
            delegated_penalty=0.0, final_score=0.0, violation_count=5, span_count=2,
        )
        system = compute_system_score({"a": score_a, "b": score_b})
        # 10 spans at 1.0 + 2 spans at 0.0 = 10/12 ≈ 0.8333
        assert 0.83 <= system <= 0.84

    def test_three_agents_cascading_penalty(self):
        trace = _trace([
            _span("s1", agent_id="a"),
            _span("s2", parent="s1", agent_id="b"),
            _span("s3", parent="s2", agent_id="c"),
        ])
        results = [_requirement_result(0.0, "missing")]
        scores = score_multi_agent_trace(trace, results)

        # c fails -> b penalized -> a penalized (cascading)
        assert scores["c"].final_score <= scores["b"].final_score
        assert scores["b"].final_score <= scores["a"].final_score

    def test_unknown_agent_grouped(self):
        trace = _trace([_span("s1")])
        results = [_requirement_result(0.5, "partial")]
        scores = score_multi_agent_trace(trace, results)

        assert "_unknown" in scores
        assert scores["_unknown"].span_count == 1


class TestDetectLiabilityShifts:
    def test_different_models_flagged(self):
        trace = _trace([
            _span("s1", agent_id="a", model_used="gpt-4"),
            _span("s2", parent="s1", agent_id="b", model_used="claude-3-sonnet"),
        ])
        warnings = detect_liability_shifts(trace)
        assert len(warnings) >= 1
        assert "substantial modification" in warnings[0].lower()

    def test_same_model_no_warning(self):
        trace = _trace([
            _span("s1", agent_id="a", model_used="gpt-4"),
            _span("s2", parent="s1", agent_id="b", model_used="gpt-4"),
        ])
        warnings = detect_liability_shifts(trace)
        assert len(warnings) == 0

    def test_mixed_frameworks_flagged(self):
        trace = _trace([
            _span("s1", agent_id="a", agent_framework="langgraph"),
            _span("s2", parent="s1", agent_id="b", agent_framework="crewai"),
        ])
        warnings = detect_liability_shifts(trace)
        assert any("framework" in w.lower() for w in warnings)
