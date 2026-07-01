"""Scoping rules for checking if a requirement applies to an IntakeProfile."""

from __future__ import annotations

from ai_trace_auditor.models.requirement import Requirement
from ai_trace_auditor.models.intake import IntakeProfile

FRAMEWORK_MAP = {
    "EU AI Act": "eu_ai_act",
    "NIST AI RMF": "nist_ai_rmf",
    "ISO 42001": "iso_42001",
    "SOC 2 Trust Services Criteria": "soc2_ai",
    "LLM Observability Best Practices": "best_practices",
}


def matches_profile(req: Requirement, profile: IntakeProfile) -> bool:
    """Check if a requirement applies to the given intake profile.

    Returns:
        True if the requirement applies, False otherwise.
    """
    # 1. Framework filter
    target_fw = FRAMEWORK_MAP.get(req.regulation)
    if target_fw and target_fw not in profile.frameworks:
        return False

    # 2. EU AI Act market exemption
    if req.regulation == "EU AI Act" and not profile.in_eu_market:
        return False

    # 3. If applies_to is empty or None, it applies to all by default (within its framework)
    if not req.applies_to:
        return True

    # 4. Resolve active tags from profile
    active_tags = profile.resolve_tags()

    # 5. Evaluate matching rules
    req_tags = set(req.applies_to)

    # If "all" is one of the tags, we want the other tags in the list to be active.
    # e.g., ["all", "human_interaction"] means it applies to all profiles that have "human_interaction" active.
    if "all" in req_tags:
        other_tags = req_tags - {"all"}
        if not other_tags:
            return True
        return other_tags.issubset(active_tags)

    # Special case: biometric transparency OR condition
    # e.g. ["emotion_recognition", "biometric_categorisation"] applies if either is active.
    biometric_or_tags = {"emotion_recognition", "biometric_categorisation"}
    if req_tags.intersection(biometric_or_tags):
        return bool(req_tags.intersection(active_tags))

    # Default logic: AND (all tags must be active)
    # e.g. ["high_risk", "financial_institution"]
    return req_tags.issubset(active_tags)
