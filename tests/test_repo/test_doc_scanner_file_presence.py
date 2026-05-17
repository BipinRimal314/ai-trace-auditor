"""Tests for the file_presence detector kind."""

from pathlib import Path

from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.models import DocCheck


def _make_check(patterns: list[str]) -> DocCheck:
    return DocCheck(
        id="test_check",
        legal_text="A clause requiring documentation.",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Annex IV",
        detector_kind="file_presence",
        detector_config={"patterns": patterns},
        evidence_when_present="Found at {path}.",
        evidence_when_absent="Not found.",
    )


def test_present_when_pattern_matches_basename(tmp_path: Path):
    (tmp_path / "MODEL_CARD.md").write_text("hi")
    check = _make_check(["MODEL_CARD.md", "model_card.md"])

    results = scan_docs(tmp_path, [check])

    assert len(results) == 1
    assert results[0].status == "present"
    assert results[0].matched_path is not None
    assert results[0].matched_path.name == "MODEL_CARD.md"
    assert "MODEL_CARD.md" in results[0].evidence


def test_present_matches_pattern_with_subdirectory(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "model-card.md").write_text("hi")
    check = _make_check(["docs/model-card.md", "MODEL_CARD.md"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"
    assert results[0].matched_path.name == "model-card.md"


def test_pattern_match_is_case_insensitive(tmp_path: Path):
    (tmp_path / "readme.md").write_text("hi")
    check = _make_check(["README.md"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"


def test_absent_when_no_pattern_matches(tmp_path: Path):
    (tmp_path / "unrelated.txt").write_text("hi")
    check = _make_check(["MODEL_CARD.md"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "absent"
    assert results[0].matched_path is None
    assert results[0].evidence == "Not found."


def test_directory_pattern_matches_directory(tmp_path: Path):
    (tmp_path / "licenses").mkdir()
    (tmp_path / "licenses" / "MIT.txt").write_text("MIT")
    check = _make_check(["licenses/"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"
