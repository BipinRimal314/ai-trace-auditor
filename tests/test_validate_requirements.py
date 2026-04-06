"""Tests for custom requirement packs and validate-requirements command."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trace_auditor.regulations.registry import RequirementRegistry


REQUIREMENTS_DIR = Path(__file__).parent.parent / "requirements"
ISO_42001_DIR = REQUIREMENTS_DIR / "iso_42001"
SOC2_AI_DIR = REQUIREMENTS_DIR / "soc2_ai"


def test_iso_42001_loads() -> None:
    """ISO 42001 requirement pack loads without errors."""
    registry = RequirementRegistry()
    registry.load(requirements_dir=ISO_42001_DIR)

    assert registry.count > 0
    assert "ISO 42001" in registry.regulations


def test_soc2_ai_loads() -> None:
    """SOC 2 AI requirement pack loads without errors."""
    registry = RequirementRegistry()
    registry.load(requirements_dir=SOC2_AI_DIR)

    assert registry.count > 0
    assert "SOC 2 Trust Services Criteria" in registry.regulations


def test_load_additional_appends() -> None:
    """load_additional adds requirements without clearing existing ones."""
    registry = RequirementRegistry()
    registry.load()  # Load built-in EU AI Act + NIST

    builtin_count = registry.count
    assert builtin_count > 0

    registry.load_additional(ISO_42001_DIR)

    assert registry.count > builtin_count
    assert "ISO 42001" in registry.regulations
    assert "EU AI Act" in registry.regulations  # still there


def test_extra_dirs_in_load() -> None:
    """extra_dirs parameter loads additional packs during initial load."""
    registry = RequirementRegistry()
    registry.load(extra_dirs=[ISO_42001_DIR, SOC2_AI_DIR])

    regs = registry.regulations
    assert "EU AI Act" in regs
    assert "ISO 42001" in regs
    assert "SOC 2 Trust Services Criteria" in regs


def test_load_additional_nonexistent_dir() -> None:
    """load_additional silently skips non-existent directories."""
    registry = RequirementRegistry()
    registry.load()
    before = registry.count

    registry.load_additional(Path("/nonexistent/path"))

    assert registry.count == before


def test_iso_42001_requirements_load_correctly() -> None:
    """ISO 42001 requirements load and have valid structure."""
    registry = RequirementRegistry()
    registry.load(requirements_dir=ISO_42001_DIR)

    for req in registry.get_all():
        assert req.id.startswith("ISO-42001-"), f"{req.id} has wrong prefix"
        assert req.severity in {"mandatory", "recommended", "best_practice"}


def test_soc2_requirements_have_valid_severity() -> None:
    """SOC 2 AI requirements use valid severity values."""
    registry = RequirementRegistry()
    registry.load(requirements_dir=SOC2_AI_DIR)

    valid = {"mandatory", "recommended", "best_practice"}
    for req in registry.get_all():
        assert req.severity in valid, f"{req.id} has invalid severity: {req.severity}"
