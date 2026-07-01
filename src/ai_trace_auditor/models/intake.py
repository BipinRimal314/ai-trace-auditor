"""Data models for compliance scoping intake."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RoleType = Literal["provider", "deployer", "importer", "distributor"]


class IntakeProfile(BaseModel):
    """Answers from the scoping intake questionnaire used to filter requirements."""

    system_name: str
    """Name of the AI system."""

    role: RoleType = "provider"
    """The organization's role under the EU AI Act."""

    in_eu_market: bool = True
    """Whether the system is placed on the market or put into service in the EU."""

    is_high_risk: bool = False
    """Whether the system is classified as high-risk under Annex III."""

    is_biometric: bool = False
    """Whether the system involves biometric identification, categorisation, or emotion recognition."""

    is_financial_institution: bool = False
    """Whether the organization is a regulated financial institution."""

    is_human_interaction: bool = False
    """Whether the system interacts directly with natural persons."""

    is_content_generation: bool = False
    """Whether the system generates synthetic content (images, audio, video, etc.)."""

    is_deep_fake: bool = False
    """Whether the system generates or manipulates content to constitute deep fakes."""

    is_text_generation: bool = False
    """Whether the system generates text."""

    is_public_interest: bool = False
    """Whether the generated text is intended to inform the public on matters of public interest."""

    is_gpai: bool = False
    """Whether the system uses a General-Purpose AI (GPAI) model."""

    is_multi_agent: bool = False
    """Whether the system is a multi-agent workflow."""

    frameworks: list[str] = Field(
        default_factory=lambda: [
            "eu_ai_act",
            "nist_ai_rmf",
            "iso_42001",
            "soc2_ai",
            "best_practices",
        ]
    )
    """Regulatory frameworks / compliance standards to include."""

    def resolve_tags(self) -> set[str]:
        """Resolve the profile properties into a set of active compliance tags."""
        tags = set()
        if self.is_high_risk:
            tags.add("high_risk")
        if self.is_biometric:
            tags.add("annex_iii_1a_biometric")
            tags.add("biometric_categorisation")
            tags.add("emotion_recognition")
        if self.is_financial_institution:
            tags.add("financial_institution")
        if self.is_human_interaction:
            tags.add("human_interaction")
        if self.is_content_generation:
            tags.add("content_generation")
        if self.is_deep_fake:
            tags.add("deep_fake")
        if self.is_text_generation:
            tags.add("text_generation")
        if self.is_public_interest:
            tags.add("public_interest")
        if self.is_multi_agent:
            tags.add("multi_agent")
            tags.add("multi_agent_only")
        if self.is_gpai:
            tags.add("gpai")
        return tags
