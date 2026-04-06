"""Tests for evidence pack generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_trace_auditor.comply.runner import run_full_compliance
from ai_trace_auditor.evidence.pack import generate_evidence_pack


SAMPLE_CODEBASE = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


@pytest.fixture
def evidence_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence-pack"


@pytest.fixture
def compliance_pkg():
    return run_full_compliance(SAMPLE_CODEBASE)


def test_creates_expected_structure(compliance_pkg, evidence_dir: Path) -> None:
    """Evidence pack creates the core files."""
    created = generate_evidence_pack(compliance_pkg, evidence_dir)

    assert evidence_dir.is_dir()
    names = {f.name for f in created}
    assert "README.md" in names
    assert "compliance-summary.md" in names
    assert "requirement-checklist.md" in names
    assert "metadata.json" in names


def test_readme_has_contents(compliance_pkg, evidence_dir: Path) -> None:
    """README.md contains a table of contents section."""
    generate_evidence_pack(compliance_pkg, evidence_dir)

    readme = (evidence_dir / "README.md").read_text(encoding="utf-8")
    assert "## Contents" in readme
    assert "## Disclaimer" in readme
    assert "AI Trace Auditor" in readme


def test_metadata_json_valid(compliance_pkg, evidence_dir: Path) -> None:
    """metadata.json has correct version and structure."""
    generate_evidence_pack(compliance_pkg, evidence_dir)

    data = json.loads((evidence_dir / "metadata.json").read_text(encoding="utf-8"))
    assert data["tool"] == "ai-trace-auditor"
    assert "version" in data
    assert "generated_at" in data
    assert "articles_covered" in data
    assert isinstance(data["articles_covered"], list)


def test_checklist_has_article_sections(compliance_pkg, evidence_dir: Path) -> None:
    """Requirement checklist covers generated articles."""
    generate_evidence_pack(compliance_pkg, evidence_dir)

    checklist = (evidence_dir / "requirement-checklist.md").read_text(encoding="utf-8")
    assert "# Compliance Requirement Checklist" in checklist
    # Should have at least Article 11 or 13 sections
    assert "Article 11" in checklist or "Article 13" in checklist


def test_mermaid_diagram_present(compliance_pkg, evidence_dir: Path) -> None:
    """Mermaid diagram source is written when flows exist."""
    generate_evidence_pack(compliance_pkg, evidence_dir)

    names = {f.name for f in evidence_dir.iterdir()}
    assert "data-flow.mermaid" in names


def test_pdf_skipped_gracefully_without_weasyprint(
    compliance_pkg, evidence_dir: Path, monkeypatch
) -> None:
    """Evidence pack doesn't crash when weasyprint is unavailable."""
    # Mock check_pdf_available to return False
    import ai_trace_auditor.evidence.pack as pack_mod

    monkeypatch.setattr(pack_mod, "_write_pdf", lambda md, path: None)

    created = generate_evidence_pack(compliance_pkg, evidence_dir)
    names = {f.name for f in created}

    # PDF should not be in the list
    assert "compliance-report.pdf" not in names
    # But everything else should still be there
    assert "README.md" in names
    assert "metadata.json" in names


def test_individual_article_reports(compliance_pkg, evidence_dir: Path) -> None:
    """Split article reports are included in the evidence pack."""
    created = generate_evidence_pack(compliance_pkg, evidence_dir)
    names = {f.name for f in created}

    # Article 11 is always generated
    assert "article-11-docs.md" in names
    # Article 13 flows are always generated for codebases with AI usage
    assert "article-13-flows.md" in names
