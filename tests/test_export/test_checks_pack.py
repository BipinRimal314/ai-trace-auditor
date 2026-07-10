"""Tests for the checks pack export (spec/checks-pack-v1.json)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_trace_auditor.cli import app
from ai_trace_auditor.export.checks_pack import build_checks_pack, write_checks_pack
from ai_trace_auditor.regulations.registry import RequirementRegistry

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _loaded_registry() -> RequirementRegistry:
    registry = RequirementRegistry()
    registry.load()
    return registry


def test_pack_covers_full_registry():
    registry = _loaded_registry()
    pack = build_checks_pack(registry)
    assert pack["total_checks"] == registry.count
    assert pack["checks_pack_version"] == 1
    assert sum(pack["frameworks"].values()) == registry.count


def test_pack_is_deterministic():
    registry = _loaded_registry()
    assert build_checks_pack(registry) == build_checks_pack(registry)
    ids = [c["id"] for c in build_checks_pack(registry)["checks"]]
    assert ids == sorted(ids)


def test_every_check_has_citation_fields():
    pack = build_checks_pack(_loaded_registry())
    for check in pack["checks"]:
        assert check["id"]
        assert check["framework"]
        assert check["article"]
        assert check["severity"]
        assert isinstance(check["what_we_look_for"], list)


def test_verified_count_matches_flags():
    pack = build_checks_pack(_loaded_registry())
    assert pack["verified_against_primary_count"] == sum(
        1 for c in pack["checks"] if c["verified_against_primary"]
    )
    # The EU AI Act pack is primary-source verified; this is a headline claim.
    assert pack["verified_against_primary_count"] > 0


def test_write_checks_pack_round_trips(tmp_path):
    out = tmp_path / "pack.json"
    pack = write_checks_pack(_loaded_registry(), out)
    assert json.loads(out.read_text(encoding="utf-8")) == pack


def test_cli_export_checks(tmp_path):
    out = tmp_path / "checks.json"
    runner = CliRunner()
    result = runner.invoke(app, ["export-checks", "-o", str(out)])
    assert result.exit_code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["total_checks"] == len(doc["checks"])


def test_committed_pack_is_current():
    """spec/checks-pack-v1.json must be regenerated when requirements change."""
    committed_path = PROJECT_ROOT / "spec" / "checks-pack-v1.json"
    assert committed_path.is_file(), "run: aitrace export-checks"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    current = build_checks_pack(_loaded_registry())
    # Compare everything except the generator version string.
    committed.pop("generated_by", None)
    current.pop("generated_by", None)
    assert committed == current, "stale checks pack — run: aitrace export-checks"
