"""Domain models for repository ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args

from ai_trace_auditor.models.gap import GapReport

TraceShape = Literal["otel", "langfuse", "chat_jsonl"]
DetectorKind = Literal["file_presence", "content_contains", "config_key"]
DocStatus = Literal["present", "absent", "partial"]
FrameworkNature = Literal["law", "voluntary", "certifiable_standard", "audit_framework"]
ComplianceTier = Literal["deterministic", "structural", "quality", "organizational"]

_VALID_SHAPES = set(get_args(TraceShape))
_VALID_STATUSES = set(get_args(DocStatus))
_VALID_DETECTOR_KINDS = set(get_args(DetectorKind))


@dataclass(frozen=True)
class TraceArtifact:
    """A trace file discovered inside a cloned repository."""

    path: Path
    shape: TraceShape
    size_bytes: int

    def __post_init__(self) -> None:
        if self.shape not in _VALID_SHAPES:
            raise ValueError(f"unknown trace shape: {self.shape}")


@dataclass(frozen=True)
class DocCheck:
    """A single governance-document detector entry from manifest.yaml."""

    id: str
    legal_text: str
    verified_against_primary: bool
    framework_nature: FrameworkNature
    compliance_tier: ComplianceTier
    regulation: str
    article: str
    detector_kind: DetectorKind
    detector_config: dict[str, Any]
    evidence_when_present: str
    evidence_when_absent: str

    def __post_init__(self) -> None:
        if self.detector_kind not in _VALID_DETECTOR_KINDS:
            raise ValueError(f"unknown detector kind: {self.detector_kind}")


@dataclass(frozen=True)
class DocCheckResult:
    """Outcome of evaluating one DocCheck against a repo."""

    check: DocCheck
    status: DocStatus
    evidence: str
    matched_path: Path | None

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unknown status: {self.status}")


@dataclass
class RepoAuditReport:
    """Combined result of scanning a cloned repository."""

    repo_url: str
    trace_artifacts_found: int
    trace_report: GapReport | None
    doc_results: list[DocCheckResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.trace_artifacts_found < 0:
            raise ValueError(
                f"trace_artifacts_found must be >= 0, got {self.trace_artifacts_found}"
            )
        if self.trace_report is not None and self.trace_artifacts_found == 0:
            raise ValueError(
                "trace_report is set but trace_artifacts_found is 0"
            )
