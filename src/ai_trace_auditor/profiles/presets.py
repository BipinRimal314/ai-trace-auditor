"""Built-in intake profile presets for common AI system shapes.

Each preset is an :class:`IntakeProfile` pre-filled for a common deployment
pattern, so `aitrace audit --profile chatbot` shows the requirements that
apply to that system shape instead of the full registry dump.
"""

from __future__ import annotations

from ai_trace_auditor.models.intake import IntakeProfile

PRESETS: dict[str, IntakeProfile] = {
    "chatbot": IntakeProfile(
        system_name="chatbot",
        is_human_interaction=True,
        is_text_generation=True,
        is_content_generation=True,
        is_gpai=True,
    ),
    "agent": IntakeProfile(
        system_name="agent",
        is_multi_agent=True,
        is_human_interaction=True,
        is_text_generation=True,
        is_gpai=True,
    ),
    "rag-pipeline": IntakeProfile(
        system_name="rag-pipeline",
        is_human_interaction=True,
        is_text_generation=True,
        is_gpai=True,
    ),
    "high-risk": IntakeProfile(
        system_name="high-risk",
        is_high_risk=True,
        is_human_interaction=True,
        is_text_generation=True,
        is_gpai=True,
    ),
}

_PRESET_RATIONALE: dict[str, str] = {
    "chatbot": (
        "Conversational system interacting directly with natural persons. "
        "Includes universal record-keeping and trace-quality checks plus "
        "human-interaction and content-generation transparency obligations "
        "(EU AI Act Art 50). Excludes high-risk-only (Annex III) and "
        "multi-agent-only requirements."
    ),
    "agent": (
        "Multi-agent workflow interacting with natural persons. Includes "
        "universal checks, transparency obligations, and multi-agent value "
        "chain accountability (EU AI Act Art 25). Excludes high-risk-only "
        "(Annex III) requirements."
    ),
    "rag-pipeline": (
        "Retrieval-augmented generation pipeline. Includes universal "
        "record-keeping, trace-quality, and text-generation transparency "
        "checks. Excludes high-risk-only (Annex III) and multi-agent-only "
        "requirements."
    ),
    "high-risk": (
        "High-risk AI system under EU AI Act Annex III. Includes the full "
        "high-risk obligation set (Articles 11, 12, 13) plus universal and "
        "transparency checks. Multi-agent-only requirements are added "
        "automatically when multi-agent traces are detected."
    ),
}


def preset_names() -> list[str]:
    """Return available preset names, sorted."""
    return sorted(PRESETS)


def get_preset(name: str) -> IntakeProfile:
    """Return the preset profile for *name*.

    Raises :class:`ValueError` with the available names if unknown.
    """
    try:
        return PRESETS[name].model_copy(deep=True)
    except KeyError:
        raise ValueError(
            f"Unknown profile {name!r}. Available profiles: {', '.join(preset_names())}"
        ) from None


def preset_rationale(name: str) -> str:
    """Return a short 'why these requirements apply' explanation for a preset."""
    return _PRESET_RATIONALE.get(name, "")
