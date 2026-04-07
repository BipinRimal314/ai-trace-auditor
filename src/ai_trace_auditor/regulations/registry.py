"""Requirement registry: loads YAML requirement definitions and provides queries."""

from __future__ import annotations

from pathlib import Path

import yaml

from ai_trace_auditor.models.requirement import EvidenceField, Requirement


def _get_bundled_requirements_dir() -> Path:
    """Return the path to the bundled requirements YAML files."""
    # Walk up from this file to find the project root requirements/ dir
    current = Path(__file__).resolve()
    # src/ai_trace_auditor/regulations/registry.py -> project root
    project_root = current.parent.parent.parent.parent
    return project_root / "requirements"


class RequirementRegistry:
    """Loads and queries regulatory requirement definitions from YAML files."""

    def __init__(self) -> None:
        self._requirements: list[Requirement] = []

    def load(
        self,
        requirements_dir: Path | None = None,
        extra_dirs: list[Path] | None = None,
    ) -> None:
        """Load all YAML requirement files from a directory tree.

        Args:
            requirements_dir: Primary requirements directory (defaults to bundled).
            extra_dirs: Additional directories to load (custom requirement packs).
        """
        if requirements_dir is None:
            requirements_dir = _get_bundled_requirements_dir()

        self._requirements = []
        for yaml_path in sorted(requirements_dir.rglob("*.yaml")):
            self._load_file(yaml_path)

        if extra_dirs:
            for extra in extra_dirs:
                self.load_additional(extra)

    def load_additional(self, extra_dir: Path) -> None:
        """Load requirements from an additional directory without clearing existing ones."""
        if not extra_dir.is_dir():
            return
        for yaml_path in sorted(extra_dir.rglob("*.yaml")):
            self._load_file(yaml_path)

    def _load_file(self, path: Path) -> None:
        """Load requirements from a single YAML file."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "requirements" not in data:
            return

        regulation = data.get("regulation", "Unknown")
        article = data.get("article", "Unknown")
        framework_nature = data.get("framework_nature")
        file_verified = data.get("verified_against_primary", False)

        for req_data in data["requirements"]:
            ef_raw = req_data.get("evidence_fields", [])
            evidence_fields = [EvidenceField(**ef) for ef in ef_raw] if ef_raw else []
            self._requirements.append(
                Requirement(
                    id=req_data["id"],
                    regulation=regulation,
                    article=req_data.get("article", article),
                    title=req_data["title"],
                    description=req_data["description"],
                    evidence_fields=evidence_fields,
                    severity=req_data.get("severity", "mandatory"),
                    applies_to=req_data.get("applies_to"),
                    legal_text=req_data.get("legal_text"),
                    framework_nature=framework_nature,
                    check_type=req_data.get("check_type"),
                    verified_against_primary=req_data.get(
                        "verified_against_primary", file_verified
                    ),
                    compliance_tier=req_data.get("compliance_tier"),
                )
            )

    def get_all(self) -> list[Requirement]:
        return list(self._requirements)

    def get_by_regulation(self, regulation: str) -> list[Requirement]:
        return [r for r in self._requirements if r.regulation == regulation]

    def get_by_id(self, req_id: str) -> Requirement | None:
        for r in self._requirements:
            if r.id == req_id:
                return r
        return None

    def get_by_severity(self, severity: str) -> list[Requirement]:
        return [r for r in self._requirements if r.severity == severity]

    def get_applicable(self, risk_level: str = "high_risk") -> list[Requirement]:
        """Filter requirements that apply to the given risk level."""
        return [
            r
            for r in self._requirements
            if r.applies_to is None or risk_level in r.applies_to or "all" in r.applies_to
        ]

    def get_applicable_for_trace(
        self, risk_level: str = "high_risk", is_multi_agent: bool = False
    ) -> list[Requirement]:
        """Filter requirements based on risk level and multi-agent status.

        Requirements tagged with "multi_agent_only" are excluded for
        single-agent traces to avoid false-positive gaps.
        """
        base = self.get_applicable(risk_level)
        if is_multi_agent:
            return base
        return [
            r
            for r in base
            if r.applies_to is None or "multi_agent_only" not in r.applies_to
        ]

    @property
    def regulations(self) -> list[str]:
        return sorted({r.regulation for r in self._requirements})

    @property
    def count(self) -> int:
        return len(self._requirements)
