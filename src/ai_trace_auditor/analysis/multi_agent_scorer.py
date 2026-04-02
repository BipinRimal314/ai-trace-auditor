"""Multi-agent compliance scoring with bottom-up penalty propagation.

Evaluates leaf agent nodes first, then propagates weighted penalties
upward through the delegation chain. This mirrors EU AI Act Article 25
liability: the delegator shares partial responsibility for downstream failures.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_trace_auditor.analysis.dag import build_adjacency_list, build_delegation_paths
from ai_trace_auditor.models.gap import RequirementResult
from ai_trace_auditor.models.trace import NormalizedTrace

# How much of a downstream agent's failure propagates to the delegator.
# 0.5 means: if your delegate scores 0.0, you lose at most 0.5 from your score.
DELEGATION_PENALTY_WEIGHT = 0.5


@dataclass(frozen=True)
class AgentScore:
    """Compliance score for a single agent in a multi-agent system."""

    agent_id: str
    agent_name: str | None
    own_score: float
    delegated_penalty: float
    final_score: float
    violation_count: int
    span_count: int


def score_multi_agent_trace(
    trace: NormalizedTrace,
    requirement_results: list[RequirementResult],
) -> dict[str, AgentScore]:
    """Compute per-agent compliance scores with penalty propagation.

    1. Group spans by agent_id
    2. Score each agent based on its own spans' contribution to requirements
    3. Build agent-level delegation graph
    4. Propagate penalties bottom-up: downstream failures penalize upstream agents
    """
    # Group spans by agent
    agent_spans: dict[str, list] = {}
    agent_names: dict[str, str | None] = {}
    for span in trace.spans:
        aid = span.agent_id or "_unknown"
        agent_spans.setdefault(aid, []).append(span)
        if aid not in agent_names:
            agent_names[aid] = span.agent_name

    # Compute own_score per agent: average coverage of requirements
    # weighted by how many of the agent's spans have the required fields
    agent_own_scores: dict[str, float] = {}
    agent_violations: dict[str, int] = {}

    for agent_id, spans in agent_spans.items():
        span_ids = {s.span_id for s in spans}
        scores: list[float] = []
        violations = 0

        for result in requirement_results:
            if result.status == "not_applicable":
                continue
            # Check if any evidence fields reference this agent's spans
            relevant = _has_relevant_evidence(result, span_ids, trace)
            if relevant:
                scores.append(result.coverage_score)
                if result.status in ("missing", "partial"):
                    violations += 1

        agent_own_scores[agent_id] = sum(scores) / len(scores) if scores else 1.0
        agent_violations[agent_id] = violations

    # Build agent-level delegation graph from span parent-child relationships
    agent_delegates = _build_agent_delegation_graph(trace)

    # Topological sort (handles cycles by breaking them)
    sorted_agents = _topological_sort(agent_delegates, set(agent_spans.keys()))

    # Bottom-up penalty propagation
    agent_penalties: dict[str, float] = {a: 0.0 for a in agent_spans}

    # Walk from leaves to roots (reversed topological order)
    for agent_id in reversed(sorted_agents):
        delegates = agent_delegates.get(agent_id, [])
        for delegate_id in delegates:
            delegate_final = max(
                0.0, agent_own_scores.get(delegate_id, 1.0) - agent_penalties.get(delegate_id, 0.0)
            )
            if delegate_final < 0.95:
                penalty = DELEGATION_PENALTY_WEIGHT * (1.0 - delegate_final)
                agent_penalties[agent_id] = agent_penalties.get(agent_id, 0.0) + penalty

    # Build final scores
    results: dict[str, AgentScore] = {}
    for agent_id, spans in agent_spans.items():
        own = agent_own_scores[agent_id]
        penalty = agent_penalties.get(agent_id, 0.0)
        final = max(0.0, min(1.0, own - penalty))

        results[agent_id] = AgentScore(
            agent_id=agent_id,
            agent_name=agent_names.get(agent_id),
            own_score=round(own, 4),
            delegated_penalty=round(penalty, 4),
            final_score=round(final, 4),
            violation_count=agent_violations.get(agent_id, 0),
            span_count=len(spans),
        )

    return results


def compute_system_score(agent_scores: dict[str, AgentScore]) -> float:
    """Compute system-level compliance score, weighted by span count."""
    total_spans = sum(a.span_count for a in agent_scores.values())
    if total_spans == 0:
        return 0.0

    weighted = sum(a.final_score * a.span_count for a in agent_scores.values())
    return round(weighted / total_spans, 4)


def detect_liability_shifts(trace: NormalizedTrace) -> list[str]:
    """Detect scenarios where a deployer may become a provider under Article 25.

    Heuristic: if different agents use different models or frameworks,
    the orchestration constitutes a potential "substantial modification."
    """
    warnings: list[str] = []
    models_by_agent: dict[str, set[str]] = {}
    frameworks: set[str] = set()

    for span in trace.spans:
        aid = span.agent_id or "_unknown"
        if span.model_used:
            models_by_agent.setdefault(aid, set()).add(span.model_used)
        if span.agent_framework:
            frameworks.add(span.agent_framework)

    # Check if different agents use different model families
    all_models = set()
    for models in models_by_agent.values():
        all_models.update(models)

    if len(all_models) > 1:
        warnings.append(
            f"Multiple model versions detected across agents ({', '.join(sorted(all_models))}). "
            "Orchestrating different models may constitute a 'substantial modification' "
            "under Article 25(1)(c), shifting the deployer into the Provider liability tier."
        )

    if len(frameworks) > 1:
        warnings.append(
            f"Multiple agent frameworks detected ({', '.join(sorted(frameworks))}). "
            "Mixing frameworks in a compound system may trigger Article 3(23) "
            "'substantial modification' classification."
        )

    return warnings


def _has_relevant_evidence(
    result: RequirementResult,
    span_ids: set[str],
    trace: NormalizedTrace,
) -> bool:
    """Check if a requirement result has evidence from the given agent's spans."""
    # For span-level fields, the requirement is relevant to all agents
    for ef in result.requirement.evidence_fields:
        if ef.field_path.startswith("spans[]"):
            return True
    return False


def _build_agent_delegation_graph(trace: NormalizedTrace) -> dict[str, list[str]]:
    """Build an agent-to-agent delegation graph from span parent-child relationships."""
    span_map = {s.span_id: s for s in trace.spans}
    adjacency = build_adjacency_list(trace)
    agent_delegates: dict[str, set[str]] = {}

    for parent_id, child_ids in adjacency.items():
        parent_agent = (span_map.get(parent_id) or trace.spans[0]).agent_id or "_unknown"
        for child_id in child_ids:
            child_agent = (span_map.get(child_id) or trace.spans[0]).agent_id or "_unknown"
            if parent_agent != child_agent:
                agent_delegates.setdefault(parent_agent, set()).add(child_agent)

    return {k: list(v) for k, v in agent_delegates.items()}


def _topological_sort(graph: dict[str, list[str]], all_nodes: set[str]) -> list[str]:
    """Topological sort with cycle breaking. Returns nodes from roots to leaves."""
    in_degree: dict[str, int] = {n: 0 for n in all_nodes}
    for node, neighbors in graph.items():
        for n in neighbors:
            if n in in_degree:
                in_degree[n] = in_degree.get(n, 0) + 1

    queue = [n for n in all_nodes if in_degree.get(n, 0) == 0]
    result: list[str] = []
    visited: set[str] = set()

    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        result.append(node)
        for neighbor in graph.get(node, []):
            if neighbor in in_degree:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

    # Add any remaining nodes (part of cycles)
    for node in all_nodes:
        if node not in visited:
            result.append(node)

    return result
