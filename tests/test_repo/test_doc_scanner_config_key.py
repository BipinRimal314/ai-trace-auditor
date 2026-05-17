"""Tests for the config_key detector kind."""

from pathlib import Path

from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.models import DocCheck


def _make_check(filenames: list[str], keys: list[str]) -> DocCheck:
    return DocCheck(
        id="ck_check",
        legal_text="Some clause requiring a retention config.",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Article 19",
        detector_kind="config_key",
        detector_config={"filenames": filenames, "keys": keys},
        evidence_when_present="Key '{key}' found in {path}.",
        evidence_when_absent="No key found.",
    )


def test_present_when_key_in_env_file(tmp_path: Path):
    (tmp_path / ".env.example").write_text(
        "DATABASE_URL=postgres://x\nLOG_RETENTION_DAYS=180\n"
    )
    check = _make_check([".env.example"], ["LOG_RETENTION_DAYS", "RETENTION_PERIOD"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"
    assert "LOG_RETENTION_DAYS" in results[0].evidence


def test_present_when_key_in_yaml(tmp_path: Path):
    (tmp_path / "config.yaml").write_text("retention_days: 365\nname: test\n")
    check = _make_check(["config.yaml"], ["retention_days"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"


def test_key_match_is_case_insensitive(tmp_path: Path):
    (tmp_path / ".env.example").write_text("retention_period=365\n")
    check = _make_check([".env.example"], ["RETENTION_PERIOD"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"


def test_absent_when_no_config_file(tmp_path: Path):
    check = _make_check([".env.example"], ["LOG_RETENTION_DAYS"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "absent"


def test_absent_when_file_present_but_no_key(tmp_path: Path):
    (tmp_path / ".env.example").write_text("DATABASE_URL=x\nLOG_LEVEL=info\n")
    check = _make_check([".env.example"], ["LOG_RETENTION_DAYS"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "absent"


def test_value_is_never_interpreted(tmp_path: Path):
    """Presence-only — a value of 0 still counts as the key being present."""
    (tmp_path / ".env.example").write_text("LOG_RETENTION_DAYS=0\n")
    check = _make_check([".env.example"], ["LOG_RETENTION_DAYS"])

    results = scan_docs(tmp_path, [check])

    assert results[0].status == "present"
