"""Tests for governance-doc manifest YAML loader."""

from pathlib import Path

import pytest

from ai_trace_auditor.repo.manifest_loader import load_manifest


def test_loads_well_formed_manifest(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
- id: annex_iv_2b_model_card
  legal_text: "Annex IV(2)(b): a description of the elements..."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config:
    patterns:
      - MODEL_CARD.md
      - model_card.md
  evidence_when_present: "Model card found at {path}."
  evidence_when_absent: "No model card found."
"""
    )

    checks = load_manifest(manifest_file)

    assert len(checks) == 1
    check = checks[0]
    assert check.id == "annex_iv_2b_model_card"
    assert check.detector_kind == "file_presence"
    assert check.detector_config["patterns"] == ["MODEL_CARD.md", "model_card.md"]
    assert check.verified_against_primary is True


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
- id: x
  legal_text: "x"
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config: {patterns: [X]}
  # Missing evidence_when_present and evidence_when_absent
"""
    )
    with pytest.raises(ValueError, match="evidence_when"):
        load_manifest(manifest_file)


def test_rejects_unknown_detector_kind(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
- id: x
  legal_text: "x"
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: ast_walk
  detector_config: {}
  evidence_when_present: "p"
  evidence_when_absent: "a"
"""
    )
    with pytest.raises(ValueError, match="unknown detector kind"):
        load_manifest(manifest_file)


def test_rejects_empty_file(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_manifest(manifest_file)
