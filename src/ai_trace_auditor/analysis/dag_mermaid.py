"""Generate Mermaid diagrams for multi-agent execution DAGs.

Color-codes agents by compliance score: green (>= 90%), yellow (50-89%), red (< 50%).
"""

from __future__ import annotations

from ai_trace_auditor.models.trace import NormalizedTrace


def _score_color(score: float) -> str:
    """Map a compliance score to a CSS color class."""
    if score >= 0.9:
        return "#2ecc71"  # green
    if score >= 0.5:
        return "#f39c12"  # yellow/amber
    return "#e74c3c"  # red


def _sanitize_id(text: str) -> str:
    """Make a string safe for Mermaid node IDs."""
    return text.replace("-", "_").replace(".", "_").replace(" ", "_")


def generate_agent_dag_mermaid(
    trace: NormalizedTrace,
    agent_scores: dict[str, float] | None = None,
) -> str:
    """Generate a Mermaid graph showing the agent execution DAG.

    Nodes are agents (grouped by agent_id). Edges are delegation relationships.
    Tool call nodes are shown as hexagons. Agents are color-coded by score.
    """
    if not trace.dag_adjacency_list:
        return ""

    lines = ["graph TD"]

    # Collect unique agents and their roles
    agent_info: dict[str, dict] = {}
    tool_spans: list = []

    for span in trace.spans:
        aid = span.agent_id or "_unknown"
        if aid not in agent_info:
            agent_info[aid] = {
                "name": span.agent_name or aid,
                "framework": span.agent_framework,
            }
        if span.span_kind == "tool_call" and span.tool_name:
            tool_spans.append(span)

    # Define agent nodes with scores
    for agent_id, info in agent_info.items():
        safe_id = _sanitize_id(agent_id)
        label = info["name"]
        if agent_scores and agent_id in agent_scores:
            score = agent_scores[agent_id]
            pct = f"{score * 100:.0f}%"
            label = f"{info['name']}\\n{pct}"
            color = _score_color(score)
            lines.append(f"    {safe_id}[\"{label}\"]")
            lines.append(f"    style {safe_id} fill:{color},color:#fff")
        else:
            lines.append(f"    {safe_id}[\"{label}\"]")

    # Define tool nodes as hexagons
    for span in tool_spans:
        safe_id = _sanitize_id(span.span_id)
        lines.append(f"    {safe_id}{{{{{{\"{span.tool_name}\"}}}}}}")

    # Build agent-to-agent edges from the span DAG
    span_map = {s.span_id: s for s in trace.spans}
    agent_edges: set[tuple[str, str]] = set()
    tool_edges: list[tuple[str, str]] = []

    for parent_id, child_ids in trace.dag_adjacency_list.items():
        parent = span_map.get(parent_id)
        if not parent:
            continue
        parent_agent = parent.agent_id or "_unknown"

        for child_id in child_ids:
            child = span_map.get(child_id)
            if not child:
                continue

            if child.span_kind == "tool_call" and child.tool_name:
                tool_edges.append((parent_agent, child.span_id))
            else:
                child_agent = child.agent_id or "_unknown"
                if parent_agent != child_agent:
                    agent_edges.add((parent_agent, child_agent))

    for src, dst in agent_edges:
        lines.append(f"    {_sanitize_id(src)} --> {_sanitize_id(dst)}")

    for agent_id, tool_span_id in tool_edges:
        lines.append(f"    {_sanitize_id(agent_id)} -.-> {_sanitize_id(tool_span_id)}")

    return "\n".join(lines)
