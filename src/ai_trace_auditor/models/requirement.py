"""Regulatory requirement models.

These pydantic models are the in-memory representation of every entry in
``requirements/*.yaml``. They are intentionally permissive: old YAMLs that
pre-date the source-pinning + exact-quote gate still parse. The gate is
enforced at validation time by ``ai_trace_auditor.verification`` (a
development-time package), not at model construction time, so the runtime
auditor continues to work against legacy data while new YAMLs must satisfy
the stricter contract to pass CI.

Fields added as part of the post-v0.16 anti-fabrication work:

* ``Requirement.exact_quote`` — verbatim text from the pinned source
  document. Required for requirements in YAMLs that declare
  ``verified_against_primary: true``; not required for voluntary /
  unverified frameworks (e.g. ISO 42001 against a paid standard).
* ``EvidenceField.legal_basis`` — classifies *why* this trace field is
  being asked for. ``direct`` means the law literally names the field (or
  its trace-level equivalent), ``structural`` means the law requires a
  capability this field is a proxy for, ``product_inference`` means the
  field is ShieldGuard / AI Trace Auditor judgment, not a legal mandate.
* ``EvidenceField.source_quote`` — required when ``legal_basis == "direct"``
  and when ``required == True``; supplies the clause text that justifies
  treating the field as mandatory.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LegalBasis = Literal["direct", "structural", "product_inference"]


class EvidenceField(BaseModel):
    """Defines what trace data satisfies a regulatory requirement.

    The combination of ``legal_basis`` and ``required`` is the anti-
    fabrication gate: a field cannot be marked ``required=True`` unless its
    basis is ``direct`` and ``source_quote`` is populated. This rules out
    the class of bug that shipped in v0.14.0 — mandatory "model_used" or
    "tokens" fields attributed to EU AI Act Article 12, where no such
    clause exists.
    """

    field_path: str
    """Dotted path into the trace schema, e.g. ``spans[].start_time``."""

    description: str
    """Human-readable description of what the field carries."""

    required: bool = True
    """Whether absence of this field is a compliance failure."""

    check_type: str = "non_null"
    """How the field is checked: ``present``, ``non_null``, ``non_empty``, ``retention``."""

    check_params: dict[str, int | float | str] | None = None
    """Parameters for the check (e.g. ``{"min_days": 180}`` for retention)."""

    legal_basis: LegalBasis | None = None
    """Provenance of this field:

    * ``direct``: the law literally prescribes this field (or a trace
      equivalent) and ``source_quote`` is the verbatim clause.
    * ``structural``: the law requires a capability (e.g. "logs that
      enable identifying situations that may result in risk") and this
      field is a defensible proxy. Cannot be marked ``required``.
    * ``product_inference``: a ShieldGuard product judgment, not in the
      law. Cannot be marked ``required``.
    """

    source_quote: str | None = None
    """Verbatim clause text when ``legal_basis == "direct"``. Must appear
    in the pinned source document after normalization; the quote validator
    enforces this at CI time. ``None`` for ``structural`` / ``product_inference``.
    """

    note: str | None = None
    """Free-text clarification (e.g. "Implementation guidance — not a legal
    requirement, but a reasonable proxy for risk detection")."""


class Requirement(BaseModel):
    """A single regulatory requirement that can be checked against trace data."""

    id: str
    """Stable identifier, e.g. ``EU-AIA-12.1``, ``NIST-MEASURE-2.4``."""

    regulation: str
    """Human-readable regulation name."""

    article: str
    """Formal article / clause identifier, e.g. ``Article 12``."""

    title: str
    """Short requirement title."""

    description: str
    """Paraphrase of the requirement, safe to show in reports."""

    evidence_fields: list[EvidenceField]
    """Trace fields that together satisfy this requirement."""

    severity: str = "mandatory"
    """``mandatory``, ``recommended``, ``best_practice``."""

    applies_to: list[str] | None = None
    """Scope filters, e.g. ``["high_risk"]``, ``["high_risk", "biometric"]``."""

    legal_text: str | None = None
    """Clause reference for display, e.g. ``Article 12(2)(a)``."""

    exact_quote: str | None = None
    """Verbatim statute text. Required for entries in YAMLs that declare
    ``verified_against_primary: true``; the quote validator will reject
    the YAML at CI time if the quote does not appear as a substring of
    the pinned source document (after shared normalization).

    Authoring guidance: paste the clause byte-for-byte from the publisher's
    PDF. The normalizer handles whitespace, PDF ligatures, and smart quotes,
    so a plain-ASCII transcription of the rendered text is fine."""

    framework_nature: str | None = None
    """``law``, ``voluntary``, ``certifiable_standard``, ``audit_framework``."""

    check_type: str | None = None
    """``deterministic`` or ``organizational`` — organizational requirements
    cannot be verified by trace inspection alone."""

    verified_against_primary: bool = False
    """Whether this requirement has been verified against the pinned primary
    source. Set at the file level in the YAML header; surfaced on each
    requirement for convenience."""

    compliance_tier: str | None = None
    """``deterministic`` (law prescribes exactly), ``structural`` (law
    requires capability), ``quality`` (best practice), or ``None`` for
    organizational."""


class RequirementFile(BaseModel):
    """Top-level schema for a ``requirements/**/*.yaml`` file.

    Fields that matter for verification:

    * ``source`` — registry key for the pinned primary source document.
      Required when ``verified_against_primary`` is true.
    * ``verified_against_primary`` / ``verified_date`` / ``verified_by`` —
      audit provenance. ``verified_against_primary: true`` is a claim; the
      quote validator enforces it.
    """

    regulation: str
    article: str | None = None
    title: str
    legal_reference: str | None = None
    framework_nature: str | None = None

    source: str | None = None
    """Name of the pinned primary source in ``verification/registry.yaml``.
    Required for YAMLs that set ``verified_against_primary: true``."""

    verified_against_primary: bool = False
    verified_date: str | None = None
    verified_by: str | None = None

    requirements: list[Requirement] = Field(default_factory=list)
