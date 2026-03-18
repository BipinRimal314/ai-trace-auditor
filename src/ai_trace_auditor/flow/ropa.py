"""Generate GDPR Article 30 Record of Processing Activities from flow analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_trace_auditor.models.flow import DataFlow, FlowScanResult, RoPAEntry, RoPAReport

MANUAL = "[MANUAL INPUT REQUIRED]"


def generate_ropa(flow_result: FlowScanResult) -> RoPAReport:
    """Generate a GDPR Article 30 RoPA from detected data flows."""
    entries: list[RoPAEntry] = []
    seen: set[str] = set()

    for flow in flow_result.data_flows:
        key = f"{flow.destination}_{flow.purpose}"
        if key in seen:
            continue
        seen.add(key)

        entries.append(RoPAEntry(
            processing_activity=_activity_description(flow),
            purpose=_purpose_description(flow),
            data_categories=_data_categories(flow),
            data_subjects=MANUAL,
            recipients=flow.destination,
            transfers=_transfer_description(flow),
        ))

    return RoPAReport(
        entries=entries,
        generated_at=datetime.now(timezone.utc),
        source_dir=flow_result.scanned_dir,
    )


def _activity_description(flow: DataFlow) -> str:
    """Generate a description of the processing activity."""
    descriptions = {
        "inference": f"Sending {flow.data_type} to {flow.destination} for AI inference",
        "storage": f"Storing {flow.data_type} in {flow.destination}",
        "training": f"Using {flow.data_type} for model training via {flow.destination}",
        "monitoring": f"Logging {flow.data_type} to {flow.destination} for monitoring",
        "api_call": f"Sending data to {flow.destination} via API",
    }
    return descriptions.get(flow.purpose, f"Processing {flow.data_type} via {flow.destination}")


def _purpose_description(flow: DataFlow) -> str:
    """Generate a purpose statement."""
    purposes = {
        "inference": "AI-powered content generation and analysis",
        "storage": "Data persistence and retrieval",
        "training": "Model improvement and fine-tuning",
        "monitoring": "System monitoring and compliance logging",
        "api_call": "External service integration",
    }
    return purposes.get(flow.purpose, flow.purpose)


def _data_categories(flow: DataFlow) -> str:
    """Map data type to GDPR data categories."""
    categories = {
        "prompts": "User-generated text content (may contain personal data)",
        "embeddings": "Vector representations of text content (derived personal data)",
        "user_data": "User records and associated data",
        "model_responses": "AI-generated content",
        "model_data": "Model parameters and training data",
        "logs": "System logs and usage data",
    }
    return categories.get(flow.data_type, flow.data_type)


def _transfer_description(flow: DataFlow) -> str:
    """Describe data transfer characteristics."""
    if flow.gdpr_role == "controller":
        return "Internal processing (no third-party transfer)"
    return f"Transfer to {flow.destination} as {flow.gdpr_role}"
