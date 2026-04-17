"""Tests for the primary-source quote validator.

These tests are the receipts that make the anti-fabrication gate credible.
They prove the validator:

1. Accepts every production YAML that claims primary-source verification.
2. Rejects each of the fabrication classes documented in
   ``docs/requirement-audit-2026-04-06.md``.

If any of these tests ever regress, the verification layer is compromised
and a new v0.14-style fabrication can slip through. The specific error
codes each adversarial fixture must produce are asserted so that a lax
validator change (e.g. downgrading an error to a warning) fails CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trace_auditor.verification.quote_validator import (
    Severity,
    validate_requirement_file,
)

# Project root: tests/test_verification/ -> tests -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_DIR = PROJECT_ROOT / "requirements"
ADVERSARIAL_DIR = Path(__file__).parent / "adversarial_fixtures"


# ---------------------------------------------------------------------------
# Positive case: every verified production YAML passes.
# ---------------------------------------------------------------------------

def _production_verified_yamls() -> list[Path]:
    """Enumerate every YAML in ``requirements/`` that claims primary-source verification.

    Walked rather than hard-coded so new verified YAMLs automatically enter
    CI without touching this test.
    """
    import yaml as _yaml

    out: list[Path] = []
    for path in REQUIREMENTS_DIR.rglob("*.yaml"):
        try:
            with open(path, encoding="utf-8") as fh:
                data = _yaml.safe_load(fh)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("verified_against_primary"):
            out.append(path)
    return out


@pytest.mark.parametrize(
    "yaml_path",
    _production_verified_yamls(),
    ids=lambda p: str(p.relative_to(PROJECT_ROOT)),
)
def test_production_verified_yamls_pass_validator(yaml_path: Path) -> None:
    """Every production YAML that claims primary verification must pass.

    A failure here means either:

    - A new requirement was added without a valid ``exact_quote``, or
    - The pinned source drifted and someone forgot to re-verify.

    The error message names every finding so the fix is obvious.
    """
    report = validate_requirement_file(yaml_path)
    if not report.ok:
        lines = [f"{yaml_path.name}: {len(report.errors)} error(s)"]
        for finding in report.errors:
            prefix = finding.requirement_id or "<file>"
            if finding.field_path:
                prefix = f"{prefix}:{finding.field_path}"
            lines.append(f"  [{finding.code}] {prefix}: {finding.message}")
        pytest.fail("\n".join(lines))


# ---------------------------------------------------------------------------
# Negative cases: each adversarial fixture must produce the specified error.
# ---------------------------------------------------------------------------

# Fixture filename -> expected error code
ADVERSARIAL_CASES: dict[str, str] = {
    "fabricated_exact_quote.yaml": "exact-quote-not-in-source",
    "paraphrased_as_verbatim.yaml": "exact-quote-not-in-source",
    "required_without_direct_basis.yaml": "required-without-direct-basis",
    "direct_without_source_quote.yaml": "direct-basis-missing-source-quote",
    "fabricated_source_quote.yaml": "source-quote-not-in-source",
    "verified_without_source.yaml": "verified-without-source",
    "verified_without_exact_quote.yaml": "missing-exact-quote",
}


@pytest.mark.parametrize(
    "fixture_name,expected_code",
    sorted(ADVERSARIAL_CASES.items()),
    ids=sorted(ADVERSARIAL_CASES),
)
def test_adversarial_fixtures_are_rejected(
    fixture_name: str,
    expected_code: str,
) -> None:
    """Each documented fabrication class must produce its specific error code.

    This is the structural proof that the validator catches the exact
    failure modes that shipped in v0.14.0. If a future change made the
    validator more lax (for example, downgrading a quote mismatch from
    error to warning), the corresponding fixture would no longer produce
    the expected code and this test would fail — a loud alarm rather than
    a silent regression.
    """
    path = ADVERSARIAL_DIR / fixture_name
    report = validate_requirement_file(path)

    codes = [f.code for f in report.errors]
    assert expected_code in codes, (
        f"{fixture_name}: expected error code {expected_code!r}, got {codes}. "
        "The adversarial fixture is supposed to reproduce a known fabrication "
        "pattern; if the validator no longer rejects it, the gate is broken."
    )


# ---------------------------------------------------------------------------
# Meta-test: the adversarial corpus is non-empty and matches filesystem.
# ---------------------------------------------------------------------------

def test_every_adversarial_fixture_has_an_assertion() -> None:
    """Protect against a fixture being added on disk but skipped in CI."""
    on_disk = {p.name for p in ADVERSARIAL_DIR.glob("*.yaml")}
    in_test = set(ADVERSARIAL_CASES)
    missing = on_disk - in_test
    stale = in_test - on_disk
    assert not missing, (
        f"Adversarial fixture(s) on disk without a test assertion: {sorted(missing)}. "
        "Every fixture in adversarial_fixtures/ must map to an expected error code in "
        "ADVERSARIAL_CASES; otherwise a fixture could be added but never checked."
    )
    assert not stale, (
        f"Test assertion for missing fixture(s): {sorted(stale)}. "
        "Fixture was removed but the test still expects it — remove from "
        "ADVERSARIAL_CASES."
    )
