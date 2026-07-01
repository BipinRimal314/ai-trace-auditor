"""Compliance Verification Gate over the shipped manifest.yaml.

Mirrors the discipline applied to existing regulation YAMLs: every entry
must declare legal_text, verified_against_primary, framework_nature,
compliance_tier, and a valid detector config.
"""

from pathlib import Path

import pytest

from ai_trace_auditor.repo.manifest_loader import load_manifest
from ai_trace_auditor.repo.models import DocCheck

MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "ai_trace_auditor"
    / "repo"
    / "manifest.yaml"
)


@pytest.fixture(scope="module")
def checks() -> list[DocCheck]:
    return load_manifest(MANIFEST_PATH)


def test_manifest_has_at_least_twelve_entries(checks: list[DocCheck]) -> None:
    assert len(checks) >= 12


def test_every_entry_has_non_empty_legal_text(checks: list[DocCheck]) -> None:
    for c in checks:
        assert c.legal_text.strip(), f"{c.id}: empty legal_text"
        assert len(c.legal_text) > 20, f"{c.id}: legal_text too short"


def test_every_entry_has_unique_id(checks: list[DocCheck]) -> None:
    ids = [c.id for c in checks]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_every_entry_has_valid_framework_nature(checks: list[DocCheck]) -> None:
    valid = {"law", "voluntary", "certifiable_standard", "audit_framework"}
    for c in checks:
        assert c.framework_nature in valid, f"{c.id}: bad framework_nature"


def test_every_entry_has_valid_compliance_tier(checks: list[DocCheck]) -> None:
    valid = {"deterministic", "structural", "quality", "organizational"}
    for c in checks:
        assert c.compliance_tier in valid, f"{c.id}: bad compliance_tier"


def test_file_presence_entries_have_patterns(checks: list[DocCheck]) -> None:
    for c in checks:
        if c.detector_kind == "file_presence":
            patterns = c.detector_config.get("patterns")
            assert patterns, f"{c.id}: file_presence requires patterns"
            assert all(isinstance(p, str) for p in patterns)


def test_content_contains_entries_have_file_patterns_and_phrases(
    checks: list[DocCheck],
) -> None:
    for c in checks:
        if c.detector_kind == "content_contains":
            assert c.detector_config.get("file_patterns"), (
                f"{c.id}: content_contains requires file_patterns"
            )
            assert c.detector_config.get("phrases"), (
                f"{c.id}: content_contains requires phrases"
            )


def test_config_key_entries_have_filenames_and_keys(checks: list[DocCheck]) -> None:
    for c in checks:
        if c.detector_kind == "config_key":
            assert c.detector_config.get("filenames"), (
                f"{c.id}: config_key requires filenames"
            )
            assert c.detector_config.get("keys"), (
                f"{c.id}: config_key requires keys"
            )


def test_eu_ai_act_entries_are_verified_against_primary(
    checks: list[DocCheck],
) -> None:
    for c in checks:
        if c.regulation == "EU AI Act":
            assert c.verified_against_primary is True, (
                f"{c.id}: EU AI Act entries must be verified_against_primary"
            )
