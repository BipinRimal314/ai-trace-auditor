"""End-to-end integration tests for multi-agent compliance auditing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_trace_auditor.analysis.dag import (
    build_adjacency_list,
    detect_circular_delegation,
)
from ai_trace_auditor.analysis.dag_mermaid import generate_agent_dag_mermaid
from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.ingest.otel import OTelIngestor
from ai_trace_auditor.regulations.registry import RequirementRegistry

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def registry():
    reg = RequirementRegistry()
    reg.load()
    return reg


@pytest.fixture
def analyzer(registry):
    return ComplianceAnalyzer(registry)


def _load_otel(name: str):
    with open(FIXTURES / name) as f:
        return OTelIngestor().parse(json.load(f))


class TestCrewAILinearDelegation:
    """Tests using the CrewAI-style multi-agent trace fixture."""

    def test_detects_multi_agent(self):
        traces = _load_otel("otel_multi_agent_trace.json")
        assert traces[0].is_multi_agent
        assert len(traces[0].agents) == 3

    def test_session_id_extracted(self):
        traces = _load_otel("otel_multi_agent_trace.json")
        assert traces[0].session_id == "session-multi-001"

    def test_agent_attributes_parsed(self):
        traces = _load_otel("otel_multi_agent_trace.json")
        orchestrator = traces[0].spans[0]
        assert orchestrator.agent_id == "orchestrator-1"
        assert orchestrator.agent_name == "Router"
        assert orchestrator.agent_framework == "crewai"

    def test_full_audit_produces_agent_scores(self, analyzer):
        traces = _load_otel("otel_multi_agent_trace.json")
        report = analyzer.analyze(traces, trace_source="crewai-test")

        assert report.agent_scores is not None
        assert "orchestrator-1" in report.agent_scores
        assert "researcher-1" in report.agent_scores
        assert "writer-1" in report.agent_scores

    def test_article_25_checked(self, analyzer):
        traces = _load_otel("otel_multi_agent_trace.json")
        report = analyzer.analyze(traces, trace_source="crewai-test")

        art25_ids = {
            r.requirement.id
            for r in report.requirement_results
            if "25" in r.requirement.article
        }
        assert "EU-AIA-25.1" in art25_ids
        assert "EU-AIA-25.2" in art25_ids

    def test_dag_built(self, analyzer):
        traces = _load_otel("otel_multi_agent_trace.json")
        analyzer.analyze(traces, trace_source="crewai-test")

        assert traces[0].dag_adjacency_list is not None
        assert "span-orchestrator" in traces[0].dag_adjacency_list

    def test_delegation_paths_set(self, analyzer):
        traces = _load_otel("otel_multi_agent_trace.json")
        analyzer.analyze(traces, trace_source="crewai-test")

        writer = [s for s in traces[0].spans if s.agent_id == "writer-1"][0]
        assert writer.delegation_path is not None
        assert "orchestrator-1" in writer.delegation_path

    def test_mermaid_dag_valid(self, analyzer):
        traces = _load_otel("otel_multi_agent_trace.json")
        report = analyzer.analyze(traces, trace_source="crewai-test")

        traces[0].dag_adjacency_list = build_adjacency_list(traces[0])
        mermaid = generate_agent_dag_mermaid(traces[0], report.agent_scores)

        assert mermaid.startswith("graph TD")
        assert "Router" in mermaid
        assert "Researcher" in mermaid


class TestLangGraphConditionalRouting:
    def test_detects_multi_agent(self):
        traces = _load_otel("langgraph_conditional_trace.json")
        assert traces[0].is_multi_agent

    def test_framework_detected(self):
        traces = _load_otel("langgraph_conditional_trace.json")
        router = traces[0].spans[0]
        assert router.agent_framework == "langgraph"

    def test_tool_call_classified(self):
        traces = _load_otel("langgraph_conditional_trace.json")
        tool_span = [s for s in traces[0].spans if s.tool_name == "vector_search"][0]
        assert tool_span.span_kind == "tool_call"

    def test_full_audit(self, analyzer):
        traces = _load_otel("langgraph_conditional_trace.json")
        report = analyzer.analyze(traces, trace_source="langgraph-test")
        assert report.agent_scores is not None
        assert "router-1" in report.agent_scores


class TestCircularDelegation:
    def test_multi_agent_detected(self):
        traces = _load_otel("otel_circular_delegation.json")
        assert traces[0].is_multi_agent

    def test_no_false_cycle_in_linear_trace(self):
        """This fixture is actually a linear chain (A->B->C), not circular."""
        traces = _load_otel("otel_circular_delegation.json")
        adj = build_adjacency_list(traces[0])
        cycles = detect_circular_delegation(adj)
        # A->B->C is linear, no cycle
        assert cycles == []


class TestMCPServerChain:
    def test_mcp_uri_extracted(self):
        traces = _load_otel("mcp_server_chain_trace.json")
        mcp_span = [s for s in traces[0].spans if s.mcp_server_uri][0]
        assert mcp_span.mcp_server_uri == "stdio://localhost/db-server"
        assert mcp_span.tool_name == "database_query"

    def test_multi_model_detected(self):
        traces = _load_otel("mcp_server_chain_trace.json")
        models = traces[0].models
        assert len(models) >= 2  # claude-3-opus and gpt-4


class TestSingleAgentBackwardCompatibility:
    """Ensure single-agent traces produce identical results to v0.12.0."""

    def test_no_agent_scores(self, analyzer):
        traces = _load_otel("otel_chat_trace.json")
        report = analyzer.analyze(traces, trace_source="single-agent")
        assert report.agent_scores is None

    def test_no_article_25(self, analyzer):
        traces = _load_otel("otel_chat_trace.json")
        report = analyzer.analyze(traces, trace_source="single-agent")
        art25 = [
            r for r in report.requirement_results if "25" in r.requirement.article
        ]
        assert art25 == []

    def test_is_not_multi_agent(self):
        traces = _load_otel("otel_chat_trace.json")
        assert not traces[0].is_multi_agent
