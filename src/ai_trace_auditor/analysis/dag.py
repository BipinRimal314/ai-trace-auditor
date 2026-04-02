"""DAG reconstruction and analysis for multi-agent traces.

Builds a directed acyclic graph from parent-child span relationships,
detects cycles, computes delegation paths, and identifies unsupervised agents.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_trace_auditor.models.trace import NormalizedTrace


@dataclass(frozen=True)
class AgentSummary:
    """Summary statistics for a single agent within a trace."""

    agent_id: str
    agent_name: str | None
    framework: str | None
    span_count: int
    has_human_oversight: bool
    max_delegation_depth: int


def build_adjacency_list(trace: NormalizedTrace) -> dict[str, list[str]]:
    """Build a parent -> children adjacency list from span relationships.

    Returns a dict mapping each parent span_id to its list of child span_ids.
    Spans with no parent (roots) do not appear as keys unless they have children.
    """
    adjacency: dict[str, list[str]] = {}
    span_ids = {s.span_id for s in trace.spans}

    for span in trace.spans:
        if span.parent_span_id and span.parent_span_id in span_ids:
            adjacency.setdefault(span.parent_span_id, []).append(span.span_id)

    return adjacency


def detect_circular_delegation(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Detect cycles in the span DAG using DFS.

    Returns a list of cycles found. Each cycle is a list of span_ids
    forming the loop. Empty list means no cycles (healthy).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    all_nodes: set[str] = set()

    for parent, children in adjacency.items():
        all_nodes.add(parent)
        all_nodes.update(children)

    for node in all_nodes:
        color[node] = WHITE

    cycles: list[list[str]] = []
    path: list[str] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)

        for child in adjacency.get(node, []):
            if color.get(child, WHITE) == GRAY:
                cycle_start = path.index(child)
                cycles.append(path[cycle_start:] + [child])
            elif color.get(child, WHITE) == WHITE:
                dfs(child)

        path.pop()
        color[node] = BLACK

    for node in all_nodes:
        if color.get(node, WHITE) == WHITE:
            dfs(node)

    return cycles


def compute_delegation_depth(
    adjacency: dict[str, list[str]], root_ids: set[str], target_id: str
) -> int:
    """Compute the longest path from any root to the target span.

    Returns 0 if the target is itself a root.
    Returns -1 if the target is unreachable from any root.
    """
    if target_id in root_ids:
        return 0

    max_depth = -1

    def dfs(node: str, depth: int) -> None:
        nonlocal max_depth
        if node == target_id:
            max_depth = max(max_depth, depth)
            return
        for child in adjacency.get(node, []):
            dfs(child, depth + 1)

    for root in root_ids:
        dfs(root, 0)

    return max_depth


def find_root_span_ids(trace: NormalizedTrace) -> set[str]:
    """Find spans that have no parent (root spans)."""
    span_ids = {s.span_id for s in trace.spans}
    return {
        s.span_id
        for s in trace.spans
        if not s.parent_span_id or s.parent_span_id not in span_ids
    }


def extract_agents(trace: NormalizedTrace) -> list[AgentSummary]:
    """Group spans by agent_id and compute per-agent statistics."""
    agent_spans: dict[str, list] = {}
    for span in trace.spans:
        aid = span.agent_id or "_unknown"
        agent_spans.setdefault(aid, []).append(span)

    adjacency = build_adjacency_list(trace)
    roots = find_root_span_ids(trace)
    summaries: list[AgentSummary] = []

    for agent_id, spans in agent_spans.items():
        first = spans[0]
        max_depth = max(
            (compute_delegation_depth(adjacency, roots, s.span_id) for s in spans),
            default=0,
        )
        has_oversight = any(
            _is_human_oversight_span(s) for s in spans
        )

        summaries.append(
            AgentSummary(
                agent_id=agent_id,
                agent_name=first.agent_name,
                framework=first.agent_framework,
                span_count=len(spans),
                has_human_oversight=has_oversight,
                max_delegation_depth=max(max_depth, 0),
            )
        )

    return summaries


def build_delegation_paths(trace: NormalizedTrace) -> dict[str, list[str]]:
    """Build the delegation path (chain of agent_ids) for each span.

    Walks up the parent_span_id chain collecting agent_ids.
    Returns {span_id: [root_agent_id, ..., this_agent_id]}.
    """
    span_map = {s.span_id: s for s in trace.spans}
    paths: dict[str, list[str]] = {}

    for span in trace.spans:
        chain: list[str] = []
        seen: set[str] = set()
        current = span

        while current:
            if current.agent_id and current.agent_id not in seen:
                chain.append(current.agent_id)
                seen.add(current.agent_id)
            parent_id = current.parent_span_id
            if not parent_id or parent_id not in span_map or parent_id in seen:
                break
            seen.add(parent_id)
            current = span_map[parent_id]

        chain.reverse()
        paths[span.span_id] = chain

    return paths


def find_unsupervised_agents(trace: NormalizedTrace) -> list[str]:
    """Find agents with no human oversight in their delegation path.

    An agent is considered "supervised" if any span in the trace has
    a human oversight indicator in its delegation path leading to that agent.
    """
    agents = extract_agents(trace)
    return [a.agent_id for a in agents if not a.has_human_oversight and a.agent_id != "_unknown"]


def _is_human_oversight_span(span) -> bool:
    """Check if a span represents human-in-the-loop oversight."""
    op = (span.operation or "").lower()
    kind = (span.span_kind or "").lower()

    human_indicators = {"human_review", "human_approval", "human", "manual_review"}
    return op in human_indicators or kind in human_indicators
