"""Tests for the content_contains detector kind."""

from pathlib import Path

from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.models import DocCheck


def _make_check(file_patterns: list[str], phrases: list[str]) -> DocCheck:
    return DocCheck(
        id="cc_check",
        legal_text="A clause requiring disclosure language.",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="deterministic",
        regulation="EU AI Act",
        article="Article 50",
        detector_kind="content_contains",
        detector_config={"file_patterns": file_patterns, "phrases": phrases},
        evidence_when_present="Phrase found in {path}.",
        evidence_when_absent="No phrase found.",
    )


def test_present_when_phrase_in_file(tmp_path: Path):
    (tmp_path / "README.md").write_text("This is an AI chatbot that helps you.")
    check = _make_check(["README.md"], ["AI chatbot", "automated system"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"
    assert "README.md" in results[0].evidence


def test_phrase_match_is_case_insensitive(tmp_path: Path):
    (tmp_path / "README.md").write_text("Powered by ai under the hood.")
    check = _make_check(["README.md"], ["Powered by AI"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"


def test_partial_when_file_present_but_no_phrase(tmp_path: Path):
    (tmp_path / "README.md").write_text("Just a plain readme with nothing relevant.")
    check = _make_check(["README.md"], ["AI chatbot"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "partial"
    assert "README.md" in results[0].evidence
    assert "phrase" in results[0].evidence.lower()


def test_absent_when_no_matching_file(tmp_path: Path):
    check = _make_check(["README.md"], ["AI chatbot"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "absent"


def test_first_matching_file_wins(tmp_path: Path):
    (tmp_path / "README.md").write_text("AI chatbot is here.")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "transparency.md").write_text("AI chatbot is here too.")
    check = _make_check(
        ["README.md", "docs/transparency.md"], ["AI chatbot"]
    )

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"
    assert results[0].matched_path is not None
