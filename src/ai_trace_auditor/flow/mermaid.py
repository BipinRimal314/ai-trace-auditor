"""Generate Mermaid data flow diagrams from FlowScanResult."""

from __future__ import annotations

from ai_trace_auditor.models.flow import DataFlow, ExternalService, FlowScanResult


# Shape mapping by service category
_SHAPES: dict[str, tuple[str, str]] = {
    "ai_provider": ("([", "])"),   # stadium (rounded)
    "vector_db": ("[(", ")]"),     # cylinder
    "database": ("[(", ")]"),      # cylinder
    "cloud": ("{{", "}}"),         # hexagon
    "cache": ("([", "])"),
    "queue": (">", "]"),           # asymmetric
    "http_api": ("([", "])"),
    "storage": ("[(", ")]"),
}

# Style classes by GDPR role (roles apply to the operating organization, not the software)
_STYLE_CLASSES = """
    classDef controller fill:#4ade80,stroke:#166534,color:#000
    classDef processor fill:#60a5fa,stroke:#1e40af,color:#000
    classDef sub_processor fill:#f59e0b,stroke:#92400e,color:#000
    classDef unknown fill:#94a3b8,stroke:#475569,color:#000
    classDef app fill:#a78bfa,stroke:#5b21b6,color:#000
    classDef user fill:#f472b6,stroke:#be185d,color:#000
"""

# Legend text clarifying GDPR roles apply to organizations
GDPR_LEGEND = (
    "**GDPR role legend** (roles apply to the *operating organization*, not the software):\n"
    "- Green = your organization typically acts as controller\n"
    "- Blue = the service operator typically acts as processor (verify per provider's DPA)\n"
    "- Yellow = sub-processor\n"
    "- Gray = role not determined"
)


def generate_mermaid(flow_result: FlowScanResult) -> str:
    """Generate a Mermaid flowchart from data flow analysis results."""
    lines: list[str] = ["graph LR"]

    # Add nodes
    lines.append("    USER((User))")
    lines.append("    APP[Application]")
    lines.append("")

    # Deduplicate services by name
    seen_services: dict[str, ExternalService] = {}
    for svc in flow_result.external_services:
        if svc.name not in seen_services:
            seen_services[svc.name] = svc

    for svc in seen_services.values():
        node_id = _safe_id(svc.name)
        open_br, close_br = _SHAPES.get(svc.category, ("([", "])"))
        lines.append(f"    {node_id}{open_br}{svc.name}{close_br}")

    lines.append("")

    # Add user -> app flow
    lines.append("    USER -->|user input| APP")

    # Add data flows
    seen_flows: set[str] = set()
    for flow in flow_result.data_flows:
        src_id = "APP" if flow.source == "application" else _safe_id(flow.source)
        dst_id = _safe_id(flow.destination)
        flow_key = f"{src_id}->{dst_id}"

        if flow_key in seen_flows:
            continue
        seen_flows.add(flow_key)

        label = _flow_label(flow)
        lines.append(f"    {src_id} -->|{label}| {dst_id}")

        # Bidirectional: add return flow for AI providers
        if flow.purpose == "inference":
            lines.append(f"    {dst_id} -->|responses| {src_id}")

    lines.append("")

    # Add style classes
    lines.append(_STYLE_CLASSES.rstrip())
    lines.append("")

    # Apply classes
    lines.append("    class USER user")
    lines.append("    class APP app")
    for svc in seen_services.values():
        node_id = _safe_id(svc.name)
        gdpr_class = _gdpr_class(flow_result.data_flows, svc.name)
        lines.append(f"    class {node_id} {gdpr_class}")

    return "\n".join(lines)


def _safe_id(name: str) -> str:
    """Convert a service name to a safe Mermaid node ID."""
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


def _flow_label(flow: DataFlow) -> str:
    """Create a concise label for a data flow edge."""
    parts = [flow.data_type]
    if flow.contains_pii == "likely":
        parts.append("PII likely")
    return ", ".join(parts)


def _gdpr_class(flows: list[DataFlow], service_name: str) -> str:
    """Determine the style class based on GDPR role."""
    for flow in flows:
        if flow.destination == service_name:
            return flow.gdpr_role.replace("-", "_")
    return "unknown"
