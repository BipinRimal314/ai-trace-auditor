"""Tests for DAG reconstruction and analysis."""

from __future__ import annotations

import pytest

from ai_trace_auditor.analysis.dag import (
    AgentSummary,
    build_adjacency_list,
    build_delegation_paths,
    compute_delegation_depth,
    detect_circular_delegation,
    extract_agents,
    find_root_span_ids,
    find_unsupervised_agents,
)
from ai_trace_auditor.models.trace import NormalizedSpan, NormalizedTrace


def _span(
    span_id: str,
    parent: str | None = None,
    agent_id: str | None = None,
    agent_name: str | None = None,
    agent_framework: str | None = None,
    operation: str = "chat",
    span_kind: str | None = None,
) -> NormalizedSpan:
    """Helper to build a minimal span for testing."""
    return NormalizedSpan(
        span_id=span_id,
        parent_span_id=parent,
        operation=operation,
        agent_id=agent_id,
        agent_name=agent_name,
        agent_framework=agent_framework,
        span_kind=span_kind,
    )


def _trace(spans: list[NormalizedSpan]) -> NormalizedTrace:
    return NormalizedTrace(trace_id="test-trace", spans=spans, source_format="test")


class TestBuildAdjacencyList:
    def test_linear_chain(self):
        spans = [_span("A"), _span("B", parent="A"), _span("C", parent="B")]
        adj = build_adjacency_list(_trace(spans))
        assert adj == {"A": ["B"], "B": ["C"]}

    def test_tree(self):
        spans = [_span("A"), _span("B", parent="A"), _span("C", parent="A")]
        adj = build_adjacency_list(_trace(spans))
        assert adj == {"A": ["B", "C"]}

    def test_single_span(self):
        spans = [_span("A")]
        adj = build_adjacency_list(_trace(spans))
        assert adj == {}

    def test_ignores_orphan_parent_refs(self):
        """Parent references to spans not in the trace are ignored."""
        spans = [_span("A"), _span("B", parent="MISSING")]
        adj = build_adjacency_list(_trace(spans))
        assert adj == {}


class TestDetectCircularDelegation:
    def test_no_cycle(self):
        adj = {"A": ["B"], "B": ["C"]}
        cycles = detect_circular_delegation(adj)
        assert cycles == []

    def test_with_cycle(self):
        adj = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycles = detect_circular_delegation(adj)
        assert len(cycles) >= 1
        # The cycle should contain all three nodes
        cycle_set = set(cycles[0][:-1])  # last element repeats the start
        assert {"A", "B", "C"} == cycle_set

    def test_self_loop(self):
        adj = {"A": ["A"]}
        cycles = detect_circular_delegation(adj)
        assert len(cycles) >= 1

    def test_empty_graph(self):
        cycles = detect_circular_delegation({})
        assert cycles == []


class TestComputeDelegationDepth:
    def test_root_is_depth_zero(self):
        adj = {"A": ["B"]}
        assert compute_delegation_depth(adj, {"A"}, "A") == 0

    def test_linear_chain_depth(self):
        adj = {"A": ["B"], "B": ["C"], "C": ["D"]}
        assert compute_delegation_depth(adj, {"A"}, "D") == 3

    def test_unreachable_returns_negative(self):
        adj = {"A": ["B"]}
        assert compute_delegation_depth(adj, {"A"}, "Z") == -1


class TestFindRootSpanIds:
    def test_single_root(self):
        spans = [_span("A"), _span("B", parent="A"), _span("C", parent="B")]
        roots = find_root_span_ids(_trace(spans))
        assert roots == {"A"}

    def test_multiple_roots(self):
        spans = [_span("A"), _span("B"), _span("C", parent="A")]
        roots = find_root_span_ids(_trace(spans))
        assert roots == {"A", "B"}


class TestExtractAgents:
    def test_groups_by_agent_id(self):
        spans = [
            _span("s1", agent_id="researcher", agent_name="Researcher"),
            _span("s2", agent_id="researcher", agent_name="Researcher"),
            _span("s3", agent_id="writer", agent_name="Writer"),
        ]
        agents = extract_agents(_trace(spans))
        agent_map = {a.agent_id: a for a in agents}

        assert len(agent_map) == 2
        assert agent_map["researcher"].span_count == 2
        assert agent_map["writer"].span_count == 1
        assert agent_map["writer"].agent_name == "Writer"

    def test_unknown_agent_for_missing_id(self):
        spans = [_span("s1")]
        agents = extract_agents(_trace(spans))
        assert agents[0].agent_id == "_unknown"


class TestBuildDelegationPaths:
    def test_linear_delegation(self):
        spans = [
            _span("s1", agent_id="orchestrator"),
            _span("s2", parent="s1", agent_id="researcher"),
            _span("s3", parent="s2", agent_id="writer"),
        ]
        paths = build_delegation_paths(_trace(spans))

        assert paths["s1"] == ["orchestrator"]
        assert paths["s2"] == ["orchestrator", "researcher"]
        assert paths["s3"] == ["orchestrator", "researcher", "writer"]

    def test_single_agent_path(self):
        spans = [_span("s1", agent_id="solo")]
        paths = build_delegation_paths(_trace(spans))
        assert paths["s1"] == ["solo"]


class TestFindUnsupervisedAgents:
    def test_all_unsupervised(self):
        spans = [
            _span("s1", agent_id="agent-a"),
            _span("s2", parent="s1", agent_id="agent-b"),
        ]
        unsupervised = find_unsupervised_agents(_trace(spans))
        assert set(unsupervised) == {"agent-a", "agent-b"}

    def test_supervised_agent_excluded(self):
        spans = [
            _span("s1", agent_id="agent-a", operation="human_review"),
            _span("s2", parent="s1", agent_id="agent-b"),
        ]
        unsupervised = find_unsupervised_agents(_trace(spans))
        assert "agent-a" not in unsupervised
        assert "agent-b" in unsupervised

    def test_unknown_agents_excluded(self):
        spans = [_span("s1")]
        unsupervised = find_unsupervised_agents(_trace(spans))
        assert unsupervised == []
