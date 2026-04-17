"""Validate every ``exact_quote`` in a requirement YAML against its pinned source.

The validator is the anti-fabrication gate. It runs at CI time and refuses
to let a YAML ship if any claimed quote fails to appear as a substring of
the pinned primary source document (after shared text normalization).

Design:

* **Scope.** A YAML is validated when it declares ``verified_against_primary:
  true`` AND ``source: <registry-name>``. Legacy YAMLs that have not
  claimed primary verification are skipped (their requirements are still
  loadable by the runtime CLI; they simply don't benefit from the gate).
* **Three checks per requirement.**

    1. If the YAML claims verification, every :class:`Requirement` must
       carry an ``exact_quote``.
    2. Every ``exact_quote`` must substring-match the normalized source
       text.
    3. Every :class:`EvidenceField` with ``legal_basis == "direct"`` must
       carry a ``source_quote`` that also substring-matches.

* **Findings, not exceptions.** The core
  :func:`validate_requirement_file` returns a structured
  :class:`ValidationReport` so that a CI runner can surface every failure
  at once, not just the first. A convenience helper
  :func:`assert_all_valid` raises when any finding is an error — suitable
  for a pytest assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from ..models.requirement import EvidenceField, Requirement, RequirementFile
from .sources import SourceDocument, SourceNotFoundError, get_source
from .text_normalize import normalize_for_substring_match


class Severity(str, Enum):
    """Severity of a validator finding."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Finding:
    """A single validator finding attached to a requirement or evidence field."""

    severity: Severity
    code: str
    message: str
    requirement_id: str | None = None
    field_path: str | None = None


@dataclass(slots=True)
class ValidationReport:
    """Structured report for a validated YAML file.

    Usage:

    >>> report = validate_requirement_file(Path("requirements/eu_ai_act/article_12.yaml"))
    >>> report.ok
    True
    >>> for f in report.errors:
    ...     print(f.code, f.message)
    """

    yaml_path: Path
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        requirement_id: str | None = None,
        field_path: str | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                code=code,
                message=message,
                requirement_id=requirement_id,
                field_path=field_path,
            )
        )

    @property
    def errors(self) -> list[Finding]:
        """Findings that must fail the build."""
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def ok(self) -> bool:
        """True when no ERROR findings were recorded."""
        return not self.errors


# --- Core validation --------------------------------------------------------


def _load_yaml(path: Path) -> RequirementFile:
    """Parse a requirement YAML into the pydantic model."""
    with open(path, encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path}: expected a top-level mapping, got {type(raw).__name__}"
        )
    # Hydrate each requirement's framework_nature from the file-level value
    # when the individual requirement doesn't supply one — otherwise legacy
    # YAMLs that only set it at file level fail model validation.
    file_nature = raw.get("framework_nature")
    file_verified = raw.get("verified_against_primary", False)
    file_regulation = raw.get("regulation", "")
    file_article = raw.get("article", "")
    for req in raw.get("requirements", []):
        if isinstance(req, dict):
            req.setdefault("framework_nature", file_nature)
            req.setdefault("verified_against_primary", file_verified)
            req.setdefault("regulation", file_regulation)
            req.setdefault("article", file_article)
    return RequirementFile.model_validate(raw)


def _validate_requirement(
    req: Requirement,
    source: SourceDocument,
    report: ValidationReport,
    *,
    file_claims_verified: bool,
) -> None:
    """Validate a single :class:`Requirement` against *source*.

    Two checks run regardless of ``check_type``:

    - If the file claims verification, an ``exact_quote`` is mandatory.
    - If an ``exact_quote`` is present, it must substring-match the pinned
      source.

    Organizational requirements (``check_type == "organizational"``) are
    still subject to quote verification — their claim about what the law
    says is just as much a fabrication surface as a technical requirement's.
    Only the evidence-field provenance check is skipped for organizational
    requirements, since they have no trace-level fields by definition.
    """
    rid = req.id

    if file_claims_verified and not req.exact_quote:
        report.add(
            Severity.ERROR,
            "missing-exact-quote",
            f"{rid}: YAML claims primary-source verification but this "
            "requirement has no `exact_quote`. Paste the verbatim clause "
            "text from the pinned source PDF.",
            requirement_id=rid,
        )
        # No quote to verify; the evidence-field checks are the only thing
        # left to do and they run below.

    if req.exact_quote is not None:
        if req.exact_quote.strip() == "":
            report.add(
                Severity.ERROR,
                "empty-exact-quote",
                f"{rid}: `exact_quote` is empty or whitespace-only.",
                requirement_id=rid,
            )
        else:
            normalized = normalize_for_substring_match(req.exact_quote)
            if normalized not in source.normalized_text:
                report.add(
                    Severity.ERROR,
                    "exact-quote-not-in-source",
                    f"{rid}: `exact_quote` does not appear in pinned source "
                    f"({source.name}, sha256 {source.sha256[:12]}...). "
                    "The quote is either fabricated, paraphrased, or the "
                    "source hash is stale.",
                    requirement_id=rid,
                )

    # Organizational requirements have no trace-level evidence fields by
    # definition; skip the provenance checks for them but keep the quote
    # verification above in force.
    if req.check_type == "organizational":
        return

    _validate_evidence_fields(req, source, report)


def _validate_evidence_fields(
    req: Requirement,
    source: SourceDocument,
    report: ValidationReport,
) -> None:
    """Enforce provenance rules on each evidence field of *req*."""
    for ef in req.evidence_fields:
        _validate_evidence_field(req.id, ef, source, report)


def _validate_evidence_field(
    requirement_id: str,
    ef: EvidenceField,
    source: SourceDocument,
    report: ValidationReport,
) -> None:
    """Enforce provenance rules on a single :class:`EvidenceField`."""
    # Legacy fields without legal_basis are allowed for now, but any field
    # that claims required=True must declare a basis.
    if ef.legal_basis is None:
        if ef.required:
            report.add(
                Severity.WARNING,
                "missing-legal-basis",
                f"{requirement_id}:{ef.field_path}: field is `required=True` "
                "but has no `legal_basis`. Mark as `direct` with a "
                "`source_quote`, or `structural`/`product_inference` and "
                "drop `required`.",
                requirement_id=requirement_id,
                field_path=ef.field_path,
            )
        return

    # required=True is only allowed for direct-provenance fields.
    if ef.required and ef.legal_basis != "direct":
        report.add(
            Severity.ERROR,
            "required-without-direct-basis",
            f"{requirement_id}:{ef.field_path}: `required=True` is only "
            f"permitted when `legal_basis=direct`. Current basis: "
            f"{ef.legal_basis}. Either downgrade to optional (the field is "
            "a proxy, not a mandate) or supply the exact clause that names "
            "this field.",
            requirement_id=requirement_id,
            field_path=ef.field_path,
        )

    # direct requires source_quote that substring-matches.
    if ef.legal_basis == "direct":
        if not ef.source_quote:
            report.add(
                Severity.ERROR,
                "direct-basis-missing-source-quote",
                f"{requirement_id}:{ef.field_path}: `legal_basis=direct` "
                "but `source_quote` is empty. Paste the verbatim clause "
                "that names this field.",
                requirement_id=requirement_id,
                field_path=ef.field_path,
            )
        else:
            normalized = normalize_for_substring_match(ef.source_quote)
            if normalized not in source.normalized_text:
                report.add(
                    Severity.ERROR,
                    "source-quote-not-in-source",
                    f"{requirement_id}:{ef.field_path}: `source_quote` does "
                    f"not appear in pinned source ({source.name}). The "
                    "field is classified as `direct` but the quote can't be "
                    "located — likely a paraphrase or fabrication.",
                    requirement_id=requirement_id,
                    field_path=ef.field_path,
                )


# --- Public API -------------------------------------------------------------


def validate_requirement_file(yaml_path: Path) -> ValidationReport:
    """Validate every requirement in *yaml_path* against its pinned source.

    Returns a :class:`ValidationReport` even for legacy YAMLs — if the YAML
    doesn't claim primary-source verification, the report will simply be
    empty (``ok == True``). The function only raises for structural errors
    like "registry name not found" or "source file missing".
    """
    report = ValidationReport(yaml_path=yaml_path)
    rf = _load_yaml(yaml_path)

    if not rf.verified_against_primary:
        # Legacy / unverified frameworks (ISO 42001, SOC 2 against paid
        # standards, best-practice guidance): we cannot validate against a
        # primary source we don't own. Skip silently — the gate is opt-in
        # at the file level.
        return report

    if not rf.source:
        report.add(
            Severity.ERROR,
            "verified-without-source",
            f"{yaml_path.name}: `verified_against_primary: true` requires a "
            "`source:` field pointing to a registered primary-source "
            "document (see verification/registry.yaml).",
        )
        return report

    try:
        source = get_source(rf.source)
    except SourceNotFoundError as exc:
        report.add(
            Severity.ERROR,
            "unknown-source",
            f"{yaml_path.name}: {exc}",
        )
        return report
    # Hash-mismatch and file-missing are fatal; let the caller handle them.

    for req in rf.requirements:
        _validate_requirement(
            req, source, report, file_claims_verified=rf.verified_against_primary
        )

    return report


def assert_all_valid(yaml_path: Path) -> None:
    """Raise :class:`AssertionError` if *yaml_path* produces ERROR findings.

    Designed for use inside a pytest test body. The raised message lists
    every error finding so one pytest failure surfaces every issue.
    """
    report = validate_requirement_file(yaml_path)
    if report.ok:
        return
    lines = [f"{yaml_path.name}: {len(report.errors)} verification error(s)"]
    for f in report.errors:
        prefix = f.requirement_id or "<file>"
        if f.field_path:
            prefix = f"{prefix}:{f.field_path}"
        lines.append(f"  [{f.code}] {prefix}: {f.message}")
    raise AssertionError("\n".join(lines))
