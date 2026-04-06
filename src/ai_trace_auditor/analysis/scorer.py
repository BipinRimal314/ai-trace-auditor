"""Coverage scoring and gap identification."""

from __future__ import annotations

from ai_trace_auditor.models.evidence import EvidenceRecord
from ai_trace_auditor.models.gap import GapDetail
from ai_trace_auditor.models.requirement import Requirement


def compute_requirement_score(
    requirement: Requirement,
    evidence: list[EvidenceRecord],
) -> float:
    """Compute a 0.0-1.0 coverage score for a single requirement.

    Required evidence fields are weighted 2x relative to optional fields.
    """
    if not requirement.evidence_fields:
        return 1.0  # No evidence needed = satisfied

    total_weight = 0.0
    weighted_coverage = 0.0

    for ef, record in zip(requirement.evidence_fields, evidence):
        weight = 2.0 if ef.required else 1.0
        total_weight += weight
        weighted_coverage += record.coverage_pct * weight

    return weighted_coverage / total_weight if total_weight > 0 else 0.0


def determine_status(score: float) -> str:
    """Map a coverage score to a status label."""
    if score >= 0.95:
        return "satisfied"
    if score >= 0.25:
        return "partial"
    return "missing"


def identify_gaps(
    requirement: Requirement,
    evidence: list[EvidenceRecord],
) -> list[GapDetail]:
    """Identify specific gaps with actionable recommendations."""
    gaps: list[GapDetail] = []

    for ef, record in zip(requirement.evidence_fields, evidence):
        if record.coverage_pct >= 0.95:
            continue

        # Generate human-readable gap description with legal citation
        cite = requirement.legal_text or f"{requirement.article}"
        source = f"{requirement.regulation} {cite}"
        guidance_note = " (implementation guidance)" if ef.note else ""

        if record.coverage_pct == 0.0:
            description = f"Not logging: {ef.description}"
            impact = (
                f"{source} — your traces contain zero values for "
                f"`{ef.field_path}`.{guidance_note}"
            )
        else:
            pct = round(record.coverage_pct * 100, 1)
            description = f"Incomplete: {ef.description} ({pct}% coverage)"
            impact = (
                f"{source} — only {record.present_count}/{record.population} "
                f"spans have `{ef.field_path}`.{guidance_note}"
            )

        recommendation = _generate_recommendation(ef.field_path, record)
        gaps.append(
            GapDetail(
                field_path=ef.field_path,
                description=description,
                impact=impact,
                recommendation=recommendation,
            )
        )

    return gaps


def _generate_recommendation(field_path: str, record: EvidenceRecord) -> str:
    """Generate an actionable recommendation for a gap."""
    field = field_path.split(".")[-1]

    recommendations: dict[str, str] = {
        "start_time": (
            "Ensure your trace exporter includes span timestamps. "
            "OTel exporters do this by default; check your export configuration."
        ),
        "end_time": (
            "Ensure span end timestamps are recorded. "
            "This requires proper span.end() calls in your instrumentation."
        ),
        "model_used": (
            "Log the actual model version returned in the API response, not just the requested model. "
            "OTel: set gen_ai.response.model. Langfuse: set internalModel."
        ),
        "model_requested": (
            "Log the model name specified in the API request. "
            "OTel: set gen_ai.request.model."
        ),
        "input_tokens": (
            "Enable token usage logging. Most LLM APIs return token counts in the response. "
            "OTel: set gen_ai.usage.input_tokens."
        ),
        "output_tokens": (
            "Enable token usage logging. "
            "OTel: set gen_ai.usage.output_tokens."
        ),
        "error_type": (
            "Log error types when API calls fail. "
            "OTel: set error.type on the span and mark span status as ERROR."
        ),
        "finish_reasons": (
            "Log the finish/stop reason from the API response. "
            "OTel: set gen_ai.response.finish_reasons."
        ),
        "input_messages": (
            "Enable content logging (opt-in for privacy). "
            "OTel: emit gen_ai.client.inference.operation.details events with gen_ai.input.messages. "
            "Note: this may contain sensitive data."
        ),
        "output_messages": (
            "Enable content logging (opt-in for privacy). "
            "OTel: emit gen_ai.client.inference.operation.details events with gen_ai.output.messages."
        ),
        "tool_calls": (
            "Log tool/function calls made by the model. "
            "OTel: use gen_ai.tool.name, gen_ai.tool.call.id attributes."
        ),
        "provider": (
            "Include the AI provider name in your traces. "
            "OTel: set gen_ai.provider.name (e.g., 'openai', 'anthropic')."
        ),
    }

    if field in recommendations:
        return recommendations[field]

    return (
        f"Add `{field_path}` to your trace exports. "
        f"Currently {record.present_count}/{record.population} spans include this field."
    )
