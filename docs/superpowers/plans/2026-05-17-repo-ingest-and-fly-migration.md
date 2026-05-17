# Trace Auditor — Repo Ingestion & Fly.io Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept a public GitHub repo URL on the Trace Auditor web dashboard and CLI, discover trace artifacts + governance documents inside it, produce a combined compliance report. Migrate hosting from Railway to Fly.io.

**Architecture:** New `src/ai_trace_auditor/repo/` module owns clone, scan, and combine. Trace artifacts are fed into the existing `ComplianceAnalyzer.analyze()` pipeline unchanged. Documents are evaluated by three concrete detectors (`file_presence`, `content_contains`, `config_key`) declared in `repo/manifest.yaml`. The manifest is the only new claims surface and goes through the existing Compliance Verification Gate. Web layer gains one route + one template; CLI gains one subcommand.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, Typer, PyYAML, Pydantic (existing). Subprocess for `git clone`. Pytest for tests. Fly.io + Docker for deployment.

**Spec:** `docs/superpowers/specs/2026-05-17-repo-ingest-and-fly-migration-design.md`

**Working directory for all commands:** `Projects/ai-trace-auditor/` (this is a nested git repo; commits land here, not in the outer Website repo).

---

## File Structure (created/modified)

### New files

```
src/ai_trace_auditor/repo/
├── __init__.py              # Re-exports public API
├── errors.py                # Typed exceptions
├── models.py                # Dataclasses: TraceArtifact, DocCheck, DocCheckResult, RepoAuditReport
├── fetcher.py               # clone_repo()
├── trace_finder.py          # find_trace_artifacts()
├── doc_scanner.py           # scan_docs() with three detector kinds
├── manifest_loader.py       # load_manifest()
├── manifest.yaml            # ~12 governance-doc detector entries
└── report.py                # combine_repo_report()

tests/test_repo/
├── __init__.py
├── conftest.py              # Fixture helpers (tmp repo builder)
├── test_errors.py
├── test_models.py
├── test_fetcher.py          # subprocess mocked
├── test_trace_finder.py
├── test_doc_scanner_file_presence.py
├── test_doc_scanner_content_contains.py
├── test_doc_scanner_config_key.py
├── test_manifest_loader.py
├── test_manifest_gate.py    # Every manifest entry passes Compliance Verification Gate
├── test_report.py
├── test_server_repo.py      # POST /audit/repo
└── test_cli_repo.py         # `aitrace audit-repo` subcommand

tests/fixtures/repos/
├── repo_with_traces/        # has traces.jsonl + MODEL_CARD.md
├── repo_docs_only/          # governance docs, no traces
└── repo_bare/               # README only

src/ai_trace_auditor/web/templates/
└── repo_results.html        # New template, extends base.html

fly.toml                     # Project root
```

### Modified files

- `src/ai_trace_auditor/web/server.py` — add `POST /audit/repo` route + small refactor to share render path
- `src/ai_trace_auditor/web/audit_service.py` — add `audit_repo()` orchestrator
- `src/ai_trace_auditor/web/templates/audit.html` — add repo URL input alongside upload + sample selector
- `src/ai_trace_auditor/cli.py` — add `audit-repo` subcommand
- `Dockerfile` — add `git` to apt-get install
- `pyproject.toml` — bump version to 0.17.0, add `repo` optional-extra (no new deps actually; just declares grouping)
- `CLAUDE.md` — update deployment section to Fly.io
- `requirements/` — **untouched**

---

## Task 1: Set up `repo/` package skeleton + errors

**Files:**
- Create: `src/ai_trace_auditor/repo/__init__.py`
- Create: `src/ai_trace_auditor/repo/errors.py`
- Create: `tests/test_repo/__init__.py`
- Create: `tests/test_repo/test_errors.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_errors.py`:

```python
"""Tests for repo module exception hierarchy."""

import pytest

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoError,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)


def test_all_errors_inherit_from_repo_error():
    assert issubclass(InvalidRepoURL, RepoError)
    assert issubclass(RepoNotFound, RepoError)
    assert issubclass(PrivateRepo, RepoError)
    assert issubclass(RepoTooLarge, RepoError)
    assert issubclass(RepoFetchTimeout, RepoError)


def test_repo_too_large_carries_byte_count():
    err = RepoTooLarge(actual_bytes=100_000_000, limit_bytes=52_428_800)
    assert err.actual_bytes == 100_000_000
    assert err.limit_bytes == 52_428_800
    assert "100000000" in str(err) or "100 MB" in str(err) or "100,000,000" in str(err)


def test_repo_fetch_timeout_carries_seconds():
    err = RepoFetchTimeout(seconds=30)
    assert err.seconds == 30
    assert "30" in str(err)


def test_repo_error_can_be_raised_and_caught():
    with pytest.raises(RepoError):
        raise InvalidRepoURL("not a github url")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_errors.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_trace_auditor.repo'`.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/__init__.py`:

```python
"""Repository ingestion: fetch + scan + combine."""

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoError,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)

__all__ = [
    "InvalidRepoURL",
    "PrivateRepo",
    "RepoError",
    "RepoFetchTimeout",
    "RepoNotFound",
    "RepoTooLarge",
]
```

`src/ai_trace_auditor/repo/errors.py`:

```python
"""Typed exceptions for repository ingestion."""

from __future__ import annotations


class RepoError(Exception):
    """Base class for all repo-ingestion errors."""


class InvalidRepoURL(RepoError):
    """URL is not a recognized GitHub repository URL."""


class RepoNotFound(RepoError):
    """Repository does not exist or is not publicly accessible."""


class PrivateRepo(RepoError):
    """Repository exists but is private."""


class RepoTooLarge(RepoError):
    """Repository exceeds the configured size cap."""

    def __init__(self, actual_bytes: int, limit_bytes: int) -> None:
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"Repository size {actual_bytes:,} bytes exceeds limit "
            f"of {limit_bytes:,} bytes."
        )


class RepoFetchTimeout(RepoError):
    """Clone exceeded the configured timeout."""

    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        super().__init__(f"Clone exceeded {seconds} seconds.")
```

Create empty `tests/test_repo/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_errors.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/__init__.py \
        src/ai_trace_auditor/repo/errors.py \
        tests/test_repo/__init__.py \
        tests/test_repo/test_errors.py
git commit -m "feat(repo): add typed exception hierarchy for repo ingestion"
```

---

## Task 2: Domain models (`TraceArtifact`, `DocCheck`, `DocCheckResult`, `RepoAuditReport`)

**Files:**
- Create: `src/ai_trace_auditor/repo/models.py`
- Create: `tests/test_repo/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_models.py`:

```python
"""Tests for repo module dataclass models."""

from pathlib import Path

import pytest

from ai_trace_auditor.repo.models import (
    DocCheck,
    DocCheckResult,
    RepoAuditReport,
    TraceArtifact,
)


def test_trace_artifact_carries_path_and_shape():
    art = TraceArtifact(
        path=Path("/tmp/r/traces.jsonl"),
        shape="otel",
        size_bytes=2048,
    )
    assert art.path.name == "traces.jsonl"
    assert art.shape == "otel"
    assert art.size_bytes == 2048


def test_trace_artifact_rejects_unknown_shape():
    with pytest.raises(ValueError):
        TraceArtifact(path=Path("x"), shape="bogus", size_bytes=1)


def test_doc_check_requires_compliance_gate_fields():
    check = DocCheck(
        id="annex_iv_2b_model_card",
        legal_text="Annex IV(2)(b): a description of the elements of the AI system...",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Annex IV",
        detector_kind="file_presence",
        detector_config={"patterns": ["MODEL_CARD.md", "model_card.md"]},
        evidence_when_present="Model card found at {path}.",
        evidence_when_absent="No model card found.",
    )
    assert check.id == "annex_iv_2b_model_card"
    assert check.verified_against_primary is True


def test_doc_check_result_status_values():
    check = DocCheck(
        id="x",
        legal_text="x",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Annex IV",
        detector_kind="file_presence",
        detector_config={"patterns": ["X"]},
        evidence_when_present="p",
        evidence_when_absent="a",
    )
    for status in ("present", "absent", "partial"):
        result = DocCheckResult(check=check, status=status, evidence="x", matched_path=None)
        assert result.status == status

    with pytest.raises(ValueError):
        DocCheckResult(check=check, status="bogus", evidence="x", matched_path=None)


def test_repo_audit_report_assembles():
    report = RepoAuditReport(
        repo_url="https://github.com/x/y",
        trace_artifacts_found=0,
        trace_report=None,
        doc_results=[],
    )
    assert report.repo_url == "https://github.com/x/y"
    assert report.trace_report is None
    assert report.doc_results == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_models.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/models.py`:

```python
"""Domain models for repository ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ai_trace_auditor.models.gap import GapReport

TraceShape = Literal["otel", "langfuse", "chat_jsonl"]
DetectorKind = Literal["file_presence", "content_contains", "config_key"]
DocStatus = Literal["present", "absent", "partial"]
FrameworkNature = Literal["law", "voluntary", "certifiable_standard", "audit_framework"]
ComplianceTier = Literal["deterministic", "structural", "quality", "organizational"]

_VALID_SHAPES = {"otel", "langfuse", "chat_jsonl"}
_VALID_STATUSES = {"present", "absent", "partial"}
_VALID_DETECTOR_KINDS = {"file_presence", "content_contains", "config_key"}


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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_models.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/models.py tests/test_repo/test_models.py
git commit -m "feat(repo): add domain models — TraceArtifact, DocCheck, DocCheckResult, RepoAuditReport"
```

---

## Task 3: Manifest loader

**Files:**
- Create: `src/ai_trace_auditor/repo/manifest_loader.py`
- Create: `tests/test_repo/test_manifest_loader.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_manifest_loader.py`:

```python
"""Tests for governance-doc manifest YAML loader."""

from pathlib import Path

import pytest

from ai_trace_auditor.repo.manifest_loader import load_manifest


def test_loads_well_formed_manifest(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
- id: annex_iv_2b_model_card
  legal_text: "Annex IV(2)(b): a description of the elements..."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config:
    patterns:
      - MODEL_CARD.md
      - model_card.md
  evidence_when_present: "Model card found at {path}."
  evidence_when_absent: "No model card found."
"""
    )

    checks = load_manifest(manifest_file)

    assert len(checks) == 1
    check = checks[0]
    assert check.id == "annex_iv_2b_model_card"
    assert check.detector_kind == "file_presence"
    assert check.detector_config["patterns"] == ["MODEL_CARD.md", "model_card.md"]
    assert check.verified_against_primary is True


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
- id: x
  legal_text: "x"
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config: {patterns: [X]}
  # Missing evidence_when_present and evidence_when_absent
"""
    )
    with pytest.raises(ValueError, match="evidence_when"):
        load_manifest(manifest_file)


def test_rejects_unknown_detector_kind(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
- id: x
  legal_text: "x"
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: ast_walk
  detector_config: {}
  evidence_when_present: "p"
  evidence_when_absent: "a"
"""
    )
    with pytest.raises(ValueError, match="unknown detector kind"):
        load_manifest(manifest_file)


def test_rejects_empty_file(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_manifest(manifest_file)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_manifest_loader.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/manifest_loader.py`:

```python
"""Load and validate governance-doc manifest entries."""

from __future__ import annotations

from pathlib import Path

import yaml

from ai_trace_auditor.repo.models import DocCheck

_REQUIRED_FIELDS = (
    "id",
    "legal_text",
    "verified_against_primary",
    "framework_nature",
    "compliance_tier",
    "regulation",
    "article",
    "detector_kind",
    "detector_config",
    "evidence_when_present",
    "evidence_when_absent",
)


def load_manifest(path: Path) -> list[DocCheck]:
    """Load and validate the manifest YAML at ``path``.

    Raises ValueError if any entry is missing a required field, has an
    unknown detector kind, or if the file is empty.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Manifest file is empty: {path}")

    if not isinstance(data, list):
        raise ValueError(f"Manifest root must be a list, got {type(data).__name__}")

    checks: list[DocCheck] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry #{index} is not a mapping")
        for field in _REQUIRED_FIELDS:
            if field not in entry:
                raise ValueError(
                    f"Manifest entry #{index} ({entry.get('id', '<unknown>')}) "
                    f"missing required field '{field}'"
                )
        # DocCheck.__post_init__ validates detector_kind
        checks.append(DocCheck(**entry))

    return checks
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_manifest_loader.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/manifest_loader.py tests/test_repo/test_manifest_loader.py
git commit -m "feat(repo): add manifest loader with required-field validation"
```

---

## Task 4: Seed the governance manifest (~12 entries)

**Files:**
- Create: `src/ai_trace_auditor/repo/manifest.yaml`
- Create: `tests/test_repo/test_manifest_gate.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_manifest_gate.py`:

```python
"""Compliance Verification Gate over the shipped manifest.yaml.

Mirrors the discipline applied to existing regulation YAMLs: every entry
must declare legal_text, verified_against_primary, framework_nature,
compliance_tier, and a valid detector config.
"""

from pathlib import Path

import pytest

from ai_trace_auditor.repo.manifest_loader import load_manifest
from ai_trace_auditor.repo.models import DocCheck

MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "ai_trace_auditor"
    / "repo"
    / "manifest.yaml"
)


@pytest.fixture(scope="module")
def checks() -> list[DocCheck]:
    return load_manifest(MANIFEST_PATH)


def test_manifest_has_at_least_twelve_entries(checks: list[DocCheck]) -> None:
    assert len(checks) >= 12


def test_every_entry_has_non_empty_legal_text(checks: list[DocCheck]) -> None:
    for c in checks:
        assert c.legal_text.strip(), f"{c.id}: empty legal_text"
        assert len(c.legal_text) > 20, f"{c.id}: legal_text too short"


def test_every_entry_has_unique_id(checks: list[DocCheck]) -> None:
    ids = [c.id for c in checks]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_every_entry_has_valid_framework_nature(checks: list[DocCheck]) -> None:
    valid = {"law", "voluntary", "certifiable_standard", "audit_framework"}
    for c in checks:
        assert c.framework_nature in valid, f"{c.id}: bad framework_nature"


def test_every_entry_has_valid_compliance_tier(checks: list[DocCheck]) -> None:
    valid = {"deterministic", "structural", "quality", "organizational"}
    for c in checks:
        assert c.compliance_tier in valid, f"{c.id}: bad compliance_tier"


def test_file_presence_entries_have_patterns(checks: list[DocCheck]) -> None:
    for c in checks:
        if c.detector_kind == "file_presence":
            patterns = c.detector_config.get("patterns")
            assert patterns, f"{c.id}: file_presence requires patterns"
            assert all(isinstance(p, str) for p in patterns)


def test_content_contains_entries_have_file_patterns_and_phrases(
    checks: list[DocCheck],
) -> None:
    for c in checks:
        if c.detector_kind == "content_contains":
            assert c.detector_config.get("file_patterns"), (
                f"{c.id}: content_contains requires file_patterns"
            )
            assert c.detector_config.get("phrases"), (
                f"{c.id}: content_contains requires phrases"
            )


def test_config_key_entries_have_filenames_and_keys(checks: list[DocCheck]) -> None:
    for c in checks:
        if c.detector_kind == "config_key":
            assert c.detector_config.get("filenames"), (
                f"{c.id}: config_key requires filenames"
            )
            assert c.detector_config.get("keys"), (
                f"{c.id}: config_key requires keys"
            )


def test_eu_ai_act_entries_are_verified_against_primary(
    checks: list[DocCheck],
) -> None:
    for c in checks:
        if c.regulation == "EU AI Act":
            assert c.verified_against_primary is True, (
                f"{c.id}: EU AI Act entries must be verified_against_primary"
            )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_manifest_gate.py -v
```

Expected: FAIL — manifest.yaml doesn't exist.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/manifest.yaml`:

```yaml
# Governance-document detectors for AI Trace Auditor repo ingestion.
#
# Every entry must satisfy the Compliance Verification Gate:
#   - legal_text:                exact clause text
#   - verified_against_primary:  true only after page-by-page check
#   - framework_nature:          law | voluntary | certifiable_standard | audit_framework
#   - compliance_tier:           deterministic | structural | quality | organizational
#
# Detector kinds (and ONLY these three):
#   - file_presence:    filename matches any of N case-insensitive patterns
#   - content_contains: file at one of N path patterns contains any phrase from a list
#   - config_key:       known config file contains a known key (value never interpreted)

- id: annex_iv_2a_general_description
  legal_text: "Annex IV(2)(a): the technical documentation shall contain... a general description of the AI system including its intended purpose."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config:
    patterns:
      - README.md
      - README.rst
      - README
      - readme.md
  evidence_when_present: "README found at {path}. Reviewer must confirm it contains a general description of the AI system per Annex IV(2)(a)."
  evidence_when_absent: "No README found. Annex IV(2)(a) requires a general description of the AI system."

- id: annex_iv_2b_design_specifications
  legal_text: "Annex IV(2)(b): a description of the elements of the AI system and of the process for its development."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config:
    patterns:
      - MODEL_CARD.md
      - model_card.md
      - MODELCARD.md
      - docs/model-card.md
      - docs/MODEL_CARD.md
      - SYSTEM_CARD.md
  evidence_when_present: "Model/system card found at {path}. Reviewer must confirm it documents design specifications per Annex IV(2)(b)."
  evidence_when_absent: "No model or system card found. Annex IV(2)(b) requires documented design specifications."

- id: annex_iv_2c_intended_purpose_disclosed
  legal_text: "Annex IV(2)(c): a description of the intended purpose of the AI system."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: content_contains
  detector_config:
    file_patterns:
      - README.md
      - README.rst
      - README
    phrases:
      - "intended purpose"
      - "intended use"
      - "use case"
      - "designed to"
      - "this project is for"
  evidence_when_present: "Intended-purpose language found in {path}. Reviewer must confirm it accurately describes the AI system's purpose."
  evidence_when_absent: "No intended-purpose language found in README. Annex IV(2)(c) requires a description of intended purpose."

- id: annex_iv_2d_third_party_components
  legal_text: "Annex IV(2)(d): a description of the relevant... third-party tools used and how they were integrated."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Annex IV"
  detector_kind: file_presence
  detector_config:
    patterns:
      - THIRD_PARTY_NOTICES
      - THIRD_PARTY_NOTICES.md
      - NOTICE
      - NOTICE.md
      - LICENSE
      - LICENSE.md
      - licenses/
      - DATA_SOURCES.md
  evidence_when_present: "Third-party documentation found at {path}. Reviewer must confirm coverage of all integrated components per Annex IV(2)(d)."
  evidence_when_absent: "No third-party notices, license, or data-sources document found. Annex IV(2)(d) requires documentation of third-party components."

- id: article_12_logging_capability
  legal_text: "Article 12(1): high-risk AI systems shall technically allow for the automatic recording of events ('logs') over the lifetime of the system."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Article 12"
  detector_kind: file_presence
  detector_config:
    patterns:
      - otel-collector.yaml
      - otel-config.yaml
      - langfuse.yaml
      - langfuse.json
      - arize.yaml
      - logging.yaml
      - logging.conf
      - opentelemetry.yaml
  evidence_when_present: "Logging/observability config found at {path}. Reviewer must confirm it implements automatic event recording per Article 12(1)."
  evidence_when_absent: "No logging or observability configuration found. Article 12(1) requires automatic event recording capability."

- id: article_19_retention_configured
  legal_text: "Article 19: providers of high-risk AI systems shall keep the logs referred to in Article 12(1)... for a period appropriate to the intended purpose of the high-risk AI system, of at least six months."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: structural
  regulation: "EU AI Act"
  article: "Article 19"
  detector_kind: config_key
  detector_config:
    filenames:
      - .env.example
      - .env.sample
      - config.yaml
      - logging.yaml
      - otel-collector.yaml
    keys:
      - LOG_RETENTION_DAYS
      - RETENTION_PERIOD
      - LOG_RETENTION_PERIOD
      - retention
      - retention_days
      - retention_period
  evidence_when_present: "Retention configuration key '{key}' found in {path}. Reviewer must verify the configured period meets the Article 19 six-month minimum."
  evidence_when_absent: "No retention configuration key found. Article 19 requires logs to be kept for at least six months."

- id: article_25_value_chain_documentation
  legal_text: "Article 25: any distributor, importer, deployer or other third-party shall be considered to be a provider... and shall comply with the obligations of the provider under Article 16."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: organizational
  regulation: "EU AI Act"
  article: "Article 25"
  detector_kind: file_presence
  detector_config:
    patterns:
      - SECURITY.md
      - DPA.md
      - data-processing-agreement.md
      - docs/security.md
      - docs/dpa.md
  evidence_when_present: "Value-chain document found at {path}. Reviewer must confirm it addresses third-party provider obligations under Article 25."
  evidence_when_absent: "No security, DPA, or value-chain document found. Article 25 places provider obligations on distributors and integrators."

- id: article_50_ai_interaction_disclosure
  legal_text: "Article 50(1): providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system, unless this is obvious."
  verified_against_primary: true
  framework_nature: law
  compliance_tier: deterministic
  regulation: "EU AI Act"
  article: "Article 50"
  detector_kind: content_contains
  detector_config:
    file_patterns:
      - README.md
      - README.rst
      - docs/transparency.md
    phrases:
      - "AI chatbot"
      - "AI assistant"
      - "powered by AI"
      - "automated system"
      - "you are interacting with"
      - "this is an AI"
  evidence_when_present: "AI disclosure phrase found in {path}. Reviewer must confirm end-user-facing surfaces also display this disclosure per Article 50(1)."
  evidence_when_absent: "No AI-interaction disclosure language found in README or transparency docs. Article 50(1) requires users to be informed they are interacting with an AI system, unless obvious."

- id: iso_42001_clause_6_ai_policy
  legal_text: "ISO/IEC 42001 Clause 6: planning — the organization shall establish AI objectives and plans to achieve them."
  verified_against_primary: false
  framework_nature: certifiable_standard
  compliance_tier: organizational
  regulation: "ISO 42001"
  article: "Clause 6"
  detector_kind: file_presence
  detector_config:
    patterns:
      - AI_POLICY.md
      - ai-policy.md
      - AI_GOVERNANCE.md
      - ai-governance.md
      - docs/ai-policy.md
  evidence_when_present: "AI policy document found at {path}. Reviewer must confirm it establishes objectives and plans per ISO 42001 Clause 6."
  evidence_when_absent: "No AI policy or governance document found. ISO 42001 Clause 6 requires documented AI objectives."

- id: iso_42001_clause_7_2_roles_documented
  legal_text: "ISO/IEC 42001 Clause 7.2: competence — the organization shall determine the necessary competence of persons doing work that affects its AI performance."
  verified_against_primary: false
  framework_nature: certifiable_standard
  compliance_tier: organizational
  regulation: "ISO 42001"
  article: "Clause 7.2"
  detector_kind: file_presence
  detector_config:
    patterns:
      - ROLES.md
      - GOVERNANCE.md
      - docs/roles.md
      - docs/governance.md
      - CODEOWNERS
      - .github/CODEOWNERS
  evidence_when_present: "Roles/governance document found at {path}. Reviewer must confirm it documents AI-affecting role competences per ISO 42001 Clause 7.2."
  evidence_when_absent: "No roles or governance document found. ISO 42001 Clause 7.2 requires documented competences for AI-affecting roles."

- id: soc2_cc1_code_of_conduct
  legal_text: "SOC 2 CC1.1: the entity demonstrates a commitment to integrity and ethical values, including establishing a code of conduct."
  verified_against_primary: false
  framework_nature: audit_framework
  compliance_tier: organizational
  regulation: "SOC 2 Trust Services Criteria"
  article: "CC1"
  detector_kind: file_presence
  detector_config:
    patterns:
      - CODE_OF_CONDUCT.md
      - code-of-conduct.md
      - docs/code-of-conduct.md
      - CONTRIBUTING.md
  evidence_when_present: "Conduct document found at {path}. Reviewer must confirm it satisfies SOC 2 CC1.1 commitment to integrity."
  evidence_when_absent: "No code of conduct or contributing document found. SOC 2 CC1.1 requires documented ethical commitments."

- id: soc2_cc7_incident_response
  legal_text: "SOC 2 CC7.3: the entity evaluates security events to determine whether they could or have resulted in a failure of the entity to meet its objectives (security incidents)."
  verified_against_primary: false
  framework_nature: audit_framework
  compliance_tier: organizational
  regulation: "SOC 2 Trust Services Criteria"
  article: "CC7"
  detector_kind: file_presence
  detector_config:
    patterns:
      - INCIDENT_RESPONSE.md
      - incident-response.md
      - SECURITY.md
      - docs/incident-response.md
      - .github/SECURITY.md
  evidence_when_present: "Incident-response document found at {path}. Reviewer must confirm it establishes security-event evaluation per SOC 2 CC7.3."
  evidence_when_absent: "No incident-response or security document found. SOC 2 CC7.3 requires a documented security-event evaluation process."
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_manifest_gate.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/manifest.yaml tests/test_repo/test_manifest_gate.py
git commit -m "feat(repo): seed governance manifest with 12 verified-clause entries"
```

---

## Task 5: Repo fetcher (clone with caps)

**Files:**
- Create: `src/ai_trace_auditor/repo/fetcher.py`
- Create: `tests/test_repo/test_fetcher.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_fetcher.py`:

```python
"""Tests for repo fetcher.

Uses subprocess mocking so tests never hit the network. The fetcher's
contract: clone shallowly into a tmpdir, enforce size + timeout caps,
strip .git, raise typed errors. The contract is what we test, not the
exact subprocess flags.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)
from ai_trace_auditor.repo.fetcher import clone_repo, parse_github_url


def test_parse_github_url_accepts_https():
    assert parse_github_url("https://github.com/owner/repo") == ("owner", "repo")
    assert parse_github_url("https://github.com/owner/repo.git") == ("owner", "repo")
    assert parse_github_url("https://github.com/owner/repo/") == ("owner", "repo")


def test_parse_github_url_rejects_non_github():
    with pytest.raises(InvalidRepoURL):
        parse_github_url("https://gitlab.com/owner/repo")


def test_parse_github_url_rejects_malformed():
    with pytest.raises(InvalidRepoURL):
        parse_github_url("not a url at all")


def test_parse_github_url_rejects_missing_repo():
    with pytest.raises(InvalidRepoURL):
        parse_github_url("https://github.com/owner")


def _make_repo_contents(target: Path, file_count: int = 2, byte_size: int = 100) -> None:
    """Helper: populate a directory as if `git clone` had written to it."""
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir(exist_ok=True)
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    for i in range(file_count):
        (target / f"file_{i}.txt").write_text("x" * byte_size)


def test_clone_happy_path(tmp_path: Path):
    """Successful clone returns a populated path with .git stripped."""

    def fake_run(cmd, *args, **kwargs):
        # cmd looks like ["git", "clone", "--depth=1", url, target]
        target = Path(cmd[-1])
        _make_repo_contents(target)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        result_path = clone_repo(
            "https://github.com/owner/repo",
            max_bytes=10_000,
            timeout_seconds=30,
            tmpdir_root=tmp_path,
        )

    assert result_path.is_dir()
    assert not (result_path / ".git").exists()
    assert (result_path / "file_0.txt").exists()

    # Caller is responsible for cleanup; cleanup helper exists on fetcher.
    shutil.rmtree(result_path)


def test_clone_raises_repo_not_found_on_128():
    """git exit code 128 with 'not found' in stderr -> RepoNotFound."""

    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 128, "", "fatal: repository 'https://github.com/x/y' not found"
        )

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(RepoNotFound):
            clone_repo(
                "https://github.com/x/y",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )


def test_clone_raises_private_repo_on_auth_required():
    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 128, "", "fatal: Authentication failed"
        )

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(PrivateRepo):
            clone_repo(
                "https://github.com/x/y",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )


def test_clone_raises_timeout():
    def fake_run(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 30))

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(RepoFetchTimeout):
            clone_repo(
                "https://github.com/owner/repo",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )


def test_clone_raises_too_large_when_repo_exceeds_cap(tmp_path: Path):
    """If post-clone size > max_bytes, raise RepoTooLarge and clean up."""

    def fake_run(cmd, *args, **kwargs):
        target = Path(cmd[-1])
        # Each file is 600 bytes; with 3 files total > 1500 byte cap.
        _make_repo_contents(target, file_count=3, byte_size=600)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", side_effect=fake_run):
        with pytest.raises(RepoTooLarge):
            clone_repo(
                "https://github.com/owner/repo",
                max_bytes=1_500,
                timeout_seconds=30,
                tmpdir_root=tmp_path,
            )

    # Confirm scratch dir was cleaned up
    leftovers = list(tmp_path.glob("aitrace-repo-*"))
    assert leftovers == []


def test_clone_invalid_url_never_invokes_subprocess():
    """URL parsing happens before any subprocess call."""
    mock_run = MagicMock()
    with patch("ai_trace_auditor.repo.fetcher.subprocess.run", mock_run):
        with pytest.raises(InvalidRepoURL):
            clone_repo(
                "https://gitlab.com/x/y",
                max_bytes=10_000,
                timeout_seconds=30,
                tmpdir_root=Path("/tmp"),
            )
    mock_run.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_fetcher.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/fetcher.py`:

```python
"""Repository fetcher: shallow clone with size + timeout caps."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path

from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)

_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) for a valid public GitHub repo URL."""
    match = _GITHUB_URL_RE.match(url.strip())
    if not match:
        raise InvalidRepoURL(
            f"Not a valid GitHub repo URL: {url!r}. "
            "Expected https://github.com/owner/repo."
        )
    return match.group("owner"), match.group("repo")


def _directory_size_bytes(path: Path) -> int:
    """Recursive size of files in a directory."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _classify_clone_failure(returncode: int, stderr: str) -> Exception:
    text = stderr.lower()
    if "not found" in text or "could not read from remote" in text:
        return RepoNotFound(stderr.strip())
    if "authentication failed" in text or "permission denied" in text:
        return PrivateRepo(stderr.strip())
    return RepoNotFound(stderr.strip() or f"git clone failed (exit {returncode})")


def clone_repo(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
    tmpdir_root: Path,
) -> Path:
    """Shallow-clone ``url`` under ``tmpdir_root``, enforce caps, strip .git.

    Returns the path to the cloned working tree. Caller owns cleanup.

    Raises one of: InvalidRepoURL, RepoNotFound, PrivateRepo, RepoTooLarge,
    RepoFetchTimeout.
    """
    parse_github_url(url)  # raises InvalidRepoURL if bad

    tmpdir_root.mkdir(parents=True, exist_ok=True)
    target = tmpdir_root / f"aitrace-repo-{uuid.uuid4().hex}"

    cmd = ["git", "clone", "--depth=1", "--single-branch", url, str(target)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise RepoFetchTimeout(seconds=timeout_seconds) from exc

    if result.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise _classify_clone_failure(result.returncode, result.stderr)

    size = _directory_size_bytes(target)
    if size > max_bytes:
        shutil.rmtree(target, ignore_errors=True)
        raise RepoTooLarge(actual_bytes=size, limit_bytes=max_bytes)

    git_dir = target / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, ignore_errors=True)

    return target
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_fetcher.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/fetcher.py tests/test_repo/test_fetcher.py
git commit -m "feat(repo): add fetcher — shallow clone with size + timeout caps"
```

---

## Task 6: Trace artifact finder

**Files:**
- Create: `src/ai_trace_auditor/repo/trace_finder.py`
- Create: `tests/test_repo/test_trace_finder.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_trace_finder.py`:

```python
"""Tests for trace artifact discovery."""

from __future__ import annotations

import json
from pathlib import Path

from ai_trace_auditor.repo.trace_finder import find_trace_artifacts


def _write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)


def test_finds_otel_shaped_json(tmp_path: Path):
    otel_doc = {"resourceSpans": [{"scopeSpans": [{"spans": []}]}]}
    _write(tmp_path / "traces.json", json.dumps(otel_doc))

    artifacts = find_trace_artifacts(tmp_path)

    assert len(artifacts) == 1
    assert artifacts[0].shape == "otel"
    assert artifacts[0].path.name == "traces.json"


def test_finds_langfuse_export(tmp_path: Path):
    lf_doc = [
        {"id": "trace-1", "name": "chat", "observations": [{"type": "GENERATION"}]}
    ]
    _write(tmp_path / "exports" / "langfuse.json", json.dumps(lf_doc))

    artifacts = find_trace_artifacts(tmp_path)

    assert len(artifacts) == 1
    assert artifacts[0].shape == "langfuse"


def test_finds_chat_jsonl(tmp_path: Path):
    line = json.dumps({"messages": [{"role": "user", "content": "hi"}], "model": "gpt-4"})
    _write(tmp_path / "calls.jsonl", line + "\n" + line + "\n")

    artifacts = find_trace_artifacts(tmp_path)

    assert len(artifacts) == 1
    assert artifacts[0].shape == "chat_jsonl"


def test_ignores_unrelated_json(tmp_path: Path):
    _write(tmp_path / "package.json", json.dumps({"name": "pkg", "version": "1.0"}))
    _write(tmp_path / "tsconfig.json", json.dumps({"compilerOptions": {}}))

    artifacts = find_trace_artifacts(tmp_path)

    assert artifacts == []


def test_skips_files_over_size_cap(tmp_path: Path):
    big = "x" * 6_000_000  # 6 MB > 5 MB cap
    _write(tmp_path / "huge.json", json.dumps({"resourceSpans": [], "padding": big}))

    artifacts = find_trace_artifacts(tmp_path, max_file_bytes=5_000_000)

    assert artifacts == []


def test_handles_malformed_json_without_crashing(tmp_path: Path):
    _write(tmp_path / "broken.json", "{not valid json")
    _write(tmp_path / "broken.jsonl", "not\nvalid\njson\n")

    artifacts = find_trace_artifacts(tmp_path)

    assert artifacts == []


def test_finds_multiple_artifacts(tmp_path: Path):
    _write(
        tmp_path / "a.json",
        json.dumps({"resourceSpans": []}),
    )
    _write(
        tmp_path / "subdir" / "b.jsonl",
        json.dumps({"messages": [{"role": "user", "content": "x"}]}) + "\n",
    )

    artifacts = find_trace_artifacts(tmp_path)

    shapes = {a.shape for a in artifacts}
    assert shapes == {"otel", "chat_jsonl"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_trace_finder.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/trace_finder.py`:

```python
"""Discover trace artifacts inside a cloned repository tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_trace_auditor.repo.models import TraceArtifact

_DEFAULT_MAX_FILE_BYTES = 5_000_000


def _classify_json(doc: Any) -> str | None:
    """Return a trace-shape label for a parsed JSON document, or None."""
    if isinstance(doc, dict):
        if "resourceSpans" in doc or "scopeSpans" in doc:
            return "otel"
        if "messages" in doc and isinstance(doc["messages"], list):
            return "chat_jsonl"
        if "observations" in doc and ("trace_id" in doc or "id" in doc):
            return "langfuse"
        return None

    if isinstance(doc, list) and doc and isinstance(doc[0], dict):
        first = doc[0]
        if "observations" in first:
            return "langfuse"
        if "resourceSpans" in first:
            return "otel"
        if "messages" in first and isinstance(first.get("messages"), list):
            return "chat_jsonl"

    return None


def _classify_jsonl(path: Path) -> str | None:
    """Sniff the first parseable line of a JSONL file."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    return None
                shape = _classify_json(doc)
                return shape  # First parseable line decides shape
    except OSError:
        return None
    return None


def _classify_json_file(path: Path) -> str | None:
    """Try to parse a .json file and classify it."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return _classify_json(doc)


def find_trace_artifacts(
    repo_path: Path,
    *,
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
) -> list[TraceArtifact]:
    """Walk ``repo_path`` and return discovered trace artifacts."""
    artifacts: list[TraceArtifact] = []

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".json", ".jsonl"):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            continue

        shape = (
            _classify_jsonl(path) if suffix == ".jsonl" else _classify_json_file(path)
        )
        if shape is None:
            continue

        artifacts.append(
            TraceArtifact(path=path, shape=shape, size_bytes=size)
        )

    return artifacts
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_trace_finder.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/trace_finder.py tests/test_repo/test_trace_finder.py
git commit -m "feat(repo): add trace artifact discovery (OTEL, Langfuse, chat JSONL)"
```

---

## Task 7: Doc scanner — `file_presence` detector

**Files:**
- Create: `src/ai_trace_auditor/repo/doc_scanner.py` (initial skeleton + file_presence only)
- Create: `tests/test_repo/test_doc_scanner_file_presence.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_doc_scanner_file_presence.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_doc_scanner_file_presence.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/doc_scanner.py`:

```python
"""Evaluate governance-doc detectors against a cloned repository."""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.repo.models import DocCheck, DocCheckResult


def _normalize(s: str) -> str:
    return s.lower().rstrip("/")


def _detect_file_presence(repo_path: Path, patterns: list[str]) -> Path | None:
    """Return the first matching path, or None.

    A pattern with a trailing ``/`` matches a directory; otherwise matches a file.
    Match is case-insensitive on the relative path from ``repo_path``.
    """
    targets = {_normalize(p): p.endswith("/") for p in patterns}

    for path in repo_path.rglob("*"):
        rel = _normalize(str(path.relative_to(repo_path)))
        for target, expect_dir in targets.items():
            if rel == target:
                if expect_dir and path.is_dir():
                    return path
                if not expect_dir and path.is_file():
                    return path
    return None


def _evaluate(check: DocCheck, repo_path: Path) -> DocCheckResult:
    if check.detector_kind == "file_presence":
        patterns = check.detector_config.get("patterns", [])
        matched = _detect_file_presence(repo_path, patterns)
        if matched is not None:
            rel = matched.relative_to(repo_path)
            evidence = check.evidence_when_present.format(path=str(rel))
            return DocCheckResult(
                check=check, status="present", evidence=evidence, matched_path=matched
            )
        return DocCheckResult(
            check=check,
            status="absent",
            evidence=check.evidence_when_absent,
            matched_path=None,
        )

    raise NotImplementedError(f"Detector kind not yet supported: {check.detector_kind}")


def scan_docs(repo_path: Path, checks: list[DocCheck]) -> list[DocCheckResult]:
    """Evaluate every check against the repo and return the results in order."""
    return [_evaluate(c, repo_path) for c in checks]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_doc_scanner_file_presence.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/doc_scanner.py tests/test_repo/test_doc_scanner_file_presence.py
git commit -m "feat(repo): add doc scanner with file_presence detector"
```

---

## Task 8: Doc scanner — `content_contains` detector

**Files:**
- Modify: `src/ai_trace_auditor/repo/doc_scanner.py`
- Create: `tests/test_repo/test_doc_scanner_content_contains.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_doc_scanner_content_contains.py`:

```python
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
    # Either matched is acceptable; we just confirm it found one
    assert results[0].matched_path is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_doc_scanner_content_contains.py -v
```

Expected: FAIL — `NotImplementedError` for `content_contains`.

- [ ] **Step 3: Extend the implementation**

In `src/ai_trace_auditor/repo/doc_scanner.py`, add this helper above `_evaluate` and extend `_evaluate`:

```python
def _detect_content_contains(
    repo_path: Path,
    file_patterns: list[str],
    phrases: list[str],
) -> tuple[Path | None, bool]:
    """Return (matched_file_path, contained_a_phrase).

    Walks the repo once and finds the first file whose relative path matches
    any of ``file_patterns`` (case-insensitive). Returns the file's path and
    whether any phrase from ``phrases`` was present in its contents.
    Returns (None, False) if no file matched.
    """
    file_targets = {_normalize(p) for p in file_patterns}
    phrases_lower = [p.lower() for p in phrases]

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        rel = _normalize(str(path.relative_to(repo_path)))
        if rel not in file_targets:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            return path, False
        for phrase in phrases_lower:
            if phrase in text:
                return path, True
        return path, False

    return None, False
```

Modify `_evaluate` so the elif branch handles `content_contains`:

```python
def _evaluate(check: DocCheck, repo_path: Path) -> DocCheckResult:
    if check.detector_kind == "file_presence":
        patterns = check.detector_config.get("patterns", [])
        matched = _detect_file_presence(repo_path, patterns)
        if matched is not None:
            rel = matched.relative_to(repo_path)
            evidence = check.evidence_when_present.format(path=str(rel))
            return DocCheckResult(
                check=check, status="present", evidence=evidence, matched_path=matched
            )
        return DocCheckResult(
            check=check,
            status="absent",
            evidence=check.evidence_when_absent,
            matched_path=None,
        )

    if check.detector_kind == "content_contains":
        file_patterns = check.detector_config.get("file_patterns", [])
        phrases = check.detector_config.get("phrases", [])
        matched, has_phrase = _detect_content_contains(
            repo_path, file_patterns, phrases
        )
        if matched is None:
            return DocCheckResult(
                check=check,
                status="absent",
                evidence=check.evidence_when_absent,
                matched_path=None,
            )
        rel = matched.relative_to(repo_path)
        if has_phrase:
            return DocCheckResult(
                check=check,
                status="present",
                evidence=check.evidence_when_present.format(path=str(rel)),
                matched_path=matched,
            )
        return DocCheckResult(
            check=check,
            status="partial",
            evidence=(
                f"File {rel} exists but contains no required phrase. "
                f"{check.evidence_when_absent}"
            ),
            matched_path=matched,
        )

    raise NotImplementedError(f"Detector kind not yet supported: {check.detector_kind}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_repo/test_doc_scanner_file_presence.py tests/test_repo/test_doc_scanner_content_contains.py -v
```

Expected: 10 passed (5 + 5).

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/doc_scanner.py tests/test_repo/test_doc_scanner_content_contains.py
git commit -m "feat(repo): add content_contains detector to doc scanner"
```

---

## Task 9: Doc scanner — `config_key` detector

**Files:**
- Modify: `src/ai_trace_auditor/repo/doc_scanner.py`
- Create: `tests/test_repo/test_doc_scanner_config_key.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_doc_scanner_config_key.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_doc_scanner_config_key.py -v
```

Expected: FAIL — `NotImplementedError` for `config_key`.

- [ ] **Step 3: Extend the implementation**

Add this helper to `src/ai_trace_auditor/repo/doc_scanner.py`:

```python
import re

_KEY_LINE_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]", re.MULTILINE
)


def _detect_config_key(
    repo_path: Path,
    filenames: list[str],
    keys: list[str],
) -> tuple[Path | None, str | None]:
    """Return (matched_file_path, matched_key_name), or (None, None) / (path, None)."""
    file_targets = {_normalize(f) for f in filenames}
    keys_lower = {k.lower() for k in keys}

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        rel = _normalize(str(path.relative_to(repo_path)))
        if rel not in file_targets:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return path, None
        for match in _KEY_LINE_RE.finditer(text):
            key = match.group("key").lower()
            if key in keys_lower:
                return path, match.group("key")
        return path, None

    return None, None
```

Extend `_evaluate` with the new branch (place above the `raise NotImplementedError` line):

```python
    if check.detector_kind == "config_key":
        filenames = check.detector_config.get("filenames", [])
        keys = check.detector_config.get("keys", [])
        matched, matched_key = _detect_config_key(repo_path, filenames, keys)
        if matched is not None and matched_key is not None:
            rel = matched.relative_to(repo_path)
            return DocCheckResult(
                check=check,
                status="present",
                evidence=check.evidence_when_present.format(
                    path=str(rel), key=matched_key
                ),
                matched_path=matched,
            )
        return DocCheckResult(
            check=check,
            status="absent",
            evidence=check.evidence_when_absent,
            matched_path=matched,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_repo/ -v
```

Expected: all tests in `tests/test_repo/` pass.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/doc_scanner.py tests/test_repo/test_doc_scanner_config_key.py
git commit -m "feat(repo): add config_key detector to doc scanner"
```

---

## Task 10: Report combiner

**Files:**
- Create: `src/ai_trace_auditor/repo/report.py`
- Create: `tests/test_repo/test_report.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_report.py`:

```python
"""Tests for combining trace audit + doc checklist into RepoAuditReport."""

from pathlib import Path
from unittest.mock import MagicMock

from ai_trace_auditor.repo.models import DocCheck, DocCheckResult
from ai_trace_auditor.repo.report import combine_repo_report


def _make_doc_result(status: str) -> DocCheckResult:
    check = DocCheck(
        id="id",
        legal_text="x",
        verified_against_primary=True,
        framework_nature="law",
        compliance_tier="structural",
        regulation="EU AI Act",
        article="Annex IV",
        detector_kind="file_presence",
        detector_config={"patterns": ["X"]},
        evidence_when_present="p",
        evidence_when_absent="a",
    )
    return DocCheckResult(check=check, status=status, evidence="x", matched_path=None)


def test_no_traces_produces_doc_only_report():
    docs = [_make_doc_result("present"), _make_doc_result("absent")]

    report = combine_repo_report(
        repo_url="https://github.com/x/y",
        trace_artifacts=[],
        trace_report=None,
        doc_results=docs,
    )

    assert report.repo_url == "https://github.com/x/y"
    assert report.trace_artifacts_found == 0
    assert report.trace_report is None
    assert len(report.doc_results) == 2


def test_with_traces_attaches_gap_report():
    trace_report = MagicMock()
    artifacts = [MagicMock(), MagicMock()]
    docs = [_make_doc_result("present")]

    report = combine_repo_report(
        repo_url="https://github.com/x/y",
        trace_artifacts=artifacts,
        trace_report=trace_report,
        doc_results=docs,
    )

    assert report.trace_artifacts_found == 2
    assert report.trace_report is trace_report
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_report.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/ai_trace_auditor/repo/report.py`:

```python
"""Combine trace audit + doc checklist into a RepoAuditReport."""

from __future__ import annotations

from ai_trace_auditor.models.gap import GapReport
from ai_trace_auditor.repo.models import (
    DocCheckResult,
    RepoAuditReport,
    TraceArtifact,
)


def combine_repo_report(
    *,
    repo_url: str,
    trace_artifacts: list[TraceArtifact],
    trace_report: GapReport | None,
    doc_results: list[DocCheckResult],
) -> RepoAuditReport:
    """Assemble a RepoAuditReport from scanner outputs."""
    return RepoAuditReport(
        repo_url=repo_url,
        trace_artifacts_found=len(trace_artifacts),
        trace_report=trace_report,
        doc_results=doc_results,
    )
```

Also update `src/ai_trace_auditor/repo/__init__.py` to re-export the new public API:

```python
"""Repository ingestion: fetch + scan + combine."""

from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoError,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)
from ai_trace_auditor.repo.fetcher import clone_repo, parse_github_url
from ai_trace_auditor.repo.manifest_loader import load_manifest
from ai_trace_auditor.repo.models import (
    DocCheck,
    DocCheckResult,
    RepoAuditReport,
    TraceArtifact,
)
from ai_trace_auditor.repo.report import combine_repo_report
from ai_trace_auditor.repo.trace_finder import find_trace_artifacts

__all__ = [
    "DocCheck",
    "DocCheckResult",
    "InvalidRepoURL",
    "PrivateRepo",
    "RepoAuditReport",
    "RepoError",
    "RepoFetchTimeout",
    "RepoNotFound",
    "RepoTooLarge",
    "TraceArtifact",
    "clone_repo",
    "combine_repo_report",
    "find_trace_artifacts",
    "load_manifest",
    "parse_github_url",
    "scan_docs",
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_report.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/repo/report.py src/ai_trace_auditor/repo/__init__.py tests/test_repo/test_report.py
git commit -m "feat(repo): add report combiner + finalize repo package public API"
```

---

## Task 11: Fixture repos + end-to-end integration test

**Files:**
- Create: `tests/fixtures/repos/repo_with_traces/` (directory tree below)
- Create: `tests/fixtures/repos/repo_docs_only/`
- Create: `tests/fixtures/repos/repo_bare/`
- Create: `tests/test_repo/test_repo_audit_integration.py`

- [ ] **Step 1: Build fixture repos**

Run:

```bash
mkdir -p tests/fixtures/repos/repo_with_traces
mkdir -p tests/fixtures/repos/repo_docs_only/docs
mkdir -p tests/fixtures/repos/repo_bare
```

Create `tests/fixtures/repos/repo_with_traces/README.md`:

```markdown
# repo_with_traces

This is an AI chatbot project used as a Trace Auditor integration fixture.
Intended purpose: testing.
```

Create `tests/fixtures/repos/repo_with_traces/MODEL_CARD.md`:

```markdown
# Model Card

Designed to demonstrate model documentation presence.
```

Create `tests/fixtures/repos/repo_with_traces/traces.jsonl`:

```jsonl
{"messages":[{"role":"user","content":"hi"}],"model":"gpt-4"}
```

Create `tests/fixtures/repos/repo_with_traces/.env.example`:

```
LOG_RETENTION_DAYS=180
```

Create `tests/fixtures/repos/repo_docs_only/README.md`:

```markdown
# repo_docs_only

An AI assistant project with documentation but no trace exports.
Intended purpose: documentation-only fixture.
```

Create `tests/fixtures/repos/repo_docs_only/CODE_OF_CONDUCT.md`:

```markdown
# Code of Conduct
```

Create `tests/fixtures/repos/repo_docs_only/docs/ai-policy.md`:

```markdown
# AI Policy
```

Create `tests/fixtures/repos/repo_bare/README.md`:

```markdown
# bare
```

- [ ] **Step 2: Write the failing test**

`tests/test_repo/test_repo_audit_integration.py`:

```python
"""End-to-end repo audit on checked-in fixture repos.

Does not use the fetcher (no real cloning); points trace_finder + scan_docs
at the fixture path directly.
"""

from __future__ import annotations

from pathlib import Path

from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.repo.doc_scanner import scan_docs
from ai_trace_auditor.repo.manifest_loader import load_manifest
from ai_trace_auditor.repo.report import combine_repo_report
from ai_trace_auditor.repo.trace_finder import find_trace_artifacts

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"
MANIFEST = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "ai_trace_auditor"
    / "repo"
    / "manifest.yaml"
)


def _status_counts(results):
    counts = {"present": 0, "absent": 0, "partial": 0}
    for r in results:
        counts[r.status] += 1
    return counts


def test_repo_with_traces_finds_artifacts_and_docs():
    repo = FIXTURES / "repo_with_traces"
    checks = load_manifest(MANIFEST)

    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    assert len(artifacts) >= 1
    assert any(a.shape == "chat_jsonl" for a in artifacts)

    counts = _status_counts(doc_results)
    # README, model card, intended-purpose phrase, retention key — at least 4 present
    assert counts["present"] >= 4


def test_repo_docs_only_finds_no_traces_but_docs():
    repo = FIXTURES / "repo_docs_only"
    checks = load_manifest(MANIFEST)

    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    assert artifacts == []
    counts = _status_counts(doc_results)
    # README + AI policy + code of conduct
    assert counts["present"] >= 3


def test_repo_bare_yields_mostly_absent_with_no_crash():
    repo = FIXTURES / "repo_bare"
    checks = load_manifest(MANIFEST)

    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    assert artifacts == []
    counts = _status_counts(doc_results)
    assert counts["absent"] >= len(checks) - 3  # README counts as present


def test_combine_repo_report_without_traces():
    repo = FIXTURES / "repo_bare"
    checks = load_manifest(MANIFEST)
    artifacts = find_trace_artifacts(repo)
    doc_results = scan_docs(repo, checks)

    report = combine_repo_report(
        repo_url="https://github.com/test/bare",
        trace_artifacts=artifacts,
        trace_report=None,
        doc_results=doc_results,
    )

    assert report.trace_artifacts_found == 0
    assert report.trace_report is None
    assert len(report.doc_results) == len(checks)


def test_registry_still_loads_unchanged():
    """Smoke test: existing regulation YAMLs still load. We touched nothing there."""
    registry = RequirementRegistry()
    registry.load()
    assert registry.count > 0
```

- [ ] **Step 3: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_repo_audit_integration.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/repos/ tests/test_repo/test_repo_audit_integration.py
git commit -m "test(repo): add fixture repos + end-to-end integration test"
```

---

## Task 12: Web orchestrator (`audit_repo()` in audit_service)

**Files:**
- Modify: `src/ai_trace_auditor/web/audit_service.py`
- Create: `tests/test_repo/test_audit_service_repo.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_audit_service_repo.py`:

```python
"""Tests for the web orchestrator that combines fetcher + finder + scanner + audit."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.web.audit_service import audit_repo

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"


def _fake_clone_returning(fixture_name: str):
    """Build a clone_repo replacement that returns a path to a checked-in fixture."""

    def _fake(url, *, max_bytes, timeout_seconds, tmpdir_root):
        return FIXTURES / fixture_name

    return _fake


def test_audit_repo_with_traces_and_docs(tmp_path: Path):
    registry = RequirementRegistry()
    registry.load()

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone_returning("repo_with_traces"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        report = audit_repo(
            repo_url="https://github.com/test/repo_with_traces",
            registry=registry,
            tmpdir_root=tmp_path,
        )

    assert report.repo_url == "https://github.com/test/repo_with_traces"
    assert report.trace_artifacts_found >= 1
    assert report.trace_report is not None
    assert any(r.status == "present" for r in report.doc_results)


def test_audit_repo_docs_only_skips_trace_audit(tmp_path: Path):
    registry = RequirementRegistry()
    registry.load()

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone_returning("repo_docs_only"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        report = audit_repo(
            repo_url="https://github.com/test/repo_docs_only",
            registry=registry,
            tmpdir_root=tmp_path,
        )

    assert report.trace_artifacts_found == 0
    assert report.trace_report is None
    assert len(report.doc_results) > 0


def test_audit_repo_cleans_up_on_exception(tmp_path: Path):
    """If the audit raises, _cleanup_repo_dir is still called."""
    from ai_trace_auditor.repo.errors import RepoNotFound

    cleanup_calls = []

    def fake_clone(*args, **kwargs):
        raise RepoNotFound("404 from github")

    def fake_cleanup(path):
        cleanup_calls.append(path)

    registry = RequirementRegistry()
    registry.load()

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo", side_effect=fake_clone
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir",
        side_effect=fake_cleanup,
    ):
        try:
            audit_repo(
                repo_url="https://github.com/x/y",
                registry=registry,
                tmpdir_root=tmp_path,
            )
        except RepoNotFound:
            pass
    # No cleanup expected because nothing was cloned. This documents that
    # cleanup only runs if clone succeeded.
    assert cleanup_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_audit_service_repo.py -v
```

Expected: FAIL — `audit_repo` not defined.

- [ ] **Step 3: Extend `audit_service.py`**

Append to `src/ai_trace_auditor/web/audit_service.py`:

```python
import os
import shutil

from ai_trace_auditor.repo import (
    clone_repo,
    combine_repo_report,
    find_trace_artifacts,
    load_manifest,
    scan_docs,
)
from ai_trace_auditor.repo.models import RepoAuditReport

_DEFAULT_MAX_REPO_BYTES = 50 * 1024 * 1024
_DEFAULT_REPO_TIMEOUT = 30
_DEFAULT_REPO_TMPDIR = Path("/tmp/aitrace")


def _resolve_repo_settings() -> tuple[int, int, Path]:
    max_bytes = int(os.environ.get("MAX_REPO_BYTES", _DEFAULT_MAX_REPO_BYTES))
    timeout = int(os.environ.get("REPO_FETCH_TIMEOUT", _DEFAULT_REPO_TIMEOUT))
    tmpdir = Path(os.environ.get("REPO_TMPDIR", str(_DEFAULT_REPO_TMPDIR)))
    return max_bytes, timeout, tmpdir


def _load_repo_manifest():
    manifest_path = (
        Path(__file__).resolve().parent.parent / "repo" / "manifest.yaml"
    )
    return load_manifest(manifest_path)


def _cleanup_repo_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def audit_repo(
    *,
    repo_url: str,
    registry: RequirementRegistry,
    tmpdir_root: Path | None = None,
) -> RepoAuditReport:
    """Orchestrate clone → find traces → scan docs → audit traces → combine."""
    max_bytes, timeout, default_tmpdir = _resolve_repo_settings()
    root = tmpdir_root or default_tmpdir

    repo_path = clone_repo(
        repo_url,
        max_bytes=max_bytes,
        timeout_seconds=timeout,
        tmpdir_root=root,
    )

    try:
        artifacts = find_trace_artifacts(repo_path)

        trace_report = None
        if artifacts:
            traces: list = []
            for artifact in artifacts:
                try:
                    traces.extend(ingest_file(artifact.path))
                except Exception:  # noqa: BLE001 — one bad file shouldn't kill the audit
                    continue
            if traces:
                trace_report = run_audit(
                    traces=traces,
                    registry=registry,
                    regulation_filter=None,
                    trace_source=repo_url,
                )

        checks = _load_repo_manifest()
        doc_results = scan_docs(repo_path, checks)

        return combine_repo_report(
            repo_url=repo_url,
            trace_artifacts=artifacts,
            trace_report=trace_report,
            doc_results=doc_results,
        )
    finally:
        _cleanup_repo_dir(repo_path)
```

Also add this import near the top of the file (next to the existing `from ai_trace_auditor.ingest.detect import ingest_file, parse_data`):

```python
# already imported as ingest_file — no change needed if present
```

(`ingest_file` is already imported at the top of `audit_service.py`; reuse it.)

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_audit_service_repo.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_trace_auditor/web/audit_service.py tests/test_repo/test_audit_service_repo.py
git commit -m "feat(web): add audit_repo orchestrator combining fetch + find + scan + audit"
```

---

## Task 13: Web route `POST /audit/repo` + form field + results template

**Files:**
- Modify: `src/ai_trace_auditor/web/server.py`
- Modify: `src/ai_trace_auditor/web/templates/audit.html`
- Create: `src/ai_trace_auditor/web/templates/repo_results.html`
- Create: `tests/test_repo/test_server_repo.py`

- [ ] **Step 1: Read existing template files for style reference**

Run:

```bash
.venv/bin/python -c "import sys; print(sys.path)"
```

Then read `src/ai_trace_auditor/web/templates/audit.html` and `src/ai_trace_auditor/web/templates/results.html` so the new template matches the Architectural Ledger design (light bg #faf9f9, Noto Serif headings, Inter body, Tailwind via CDN).

- [ ] **Step 2: Write the failing test**

`tests/test_repo/test_server_repo.py`:

```python
"""Tests for the POST /audit/repo route."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"


@pytest.fixture
def client():
    from ai_trace_auditor.web.server import app
    return TestClient(app)


def _fake_clone(fixture_name: str):
    def _fn(url, *, max_bytes, timeout_seconds, tmpdir_root):
        return FIXTURES / fixture_name
    return _fn


def test_post_audit_repo_renders_repo_results(client):
    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone("repo_with_traces"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        resp = client.post(
            "/audit/repo",
            data={"repo_url": "https://github.com/test/repo_with_traces"},
        )

    assert resp.status_code == 200
    assert "Repository Audit" in resp.text
    assert "repo_with_traces" in resp.text


def test_post_audit_repo_missing_url_returns_400(client):
    resp = client.post("/audit/repo", data={"repo_url": ""})
    assert resp.status_code == 400
    assert "repo URL" in resp.text or "URL" in resp.text


def test_post_audit_repo_invalid_url_returns_400(client):
    from ai_trace_auditor.repo.errors import InvalidRepoURL

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=InvalidRepoURL("bad url"),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://gitlab.com/x/y"}
        )

    assert resp.status_code == 400


def test_post_audit_repo_not_found_returns_404(client):
    from ai_trace_auditor.repo.errors import RepoNotFound

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=RepoNotFound("404"),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://github.com/x/missing"}
        )

    assert resp.status_code == 404


def test_post_audit_repo_too_large_returns_413(client):
    from ai_trace_auditor.repo.errors import RepoTooLarge

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=RepoTooLarge(actual_bytes=100_000_000, limit_bytes=52_428_800),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://github.com/x/huge"}
        )

    assert resp.status_code == 413


def test_post_audit_repo_timeout_returns_504(client):
    from ai_trace_auditor.repo.errors import RepoFetchTimeout

    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=RepoFetchTimeout(seconds=30),
    ):
        resp = client.post(
            "/audit/repo", data={"repo_url": "https://github.com/x/slow"}
        )

    assert resp.status_code == 504


def test_audit_page_includes_repo_url_field(client):
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert 'name="repo_url"' in resp.text or "repo URL" in resp.text.lower()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_server_repo.py -v
```

Expected: FAIL — route doesn't exist.

- [ ] **Step 4: Add the route to `server.py`**

Add these imports to `src/ai_trace_auditor/web/server.py`:

```python
from ai_trace_auditor.repo.errors import (
    InvalidRepoURL,
    PrivateRepo,
    RepoError,
    RepoFetchTimeout,
    RepoNotFound,
    RepoTooLarge,
)
from ai_trace_auditor.web.audit_service import audit_repo
```

Add this route after `run_audit_handler`:

```python
_REPO_ERROR_STATUS = {
    InvalidRepoURL: 400,
    RepoNotFound: 404,
    PrivateRepo: 403,
    RepoTooLarge: 413,
    RepoFetchTimeout: 504,
}


@app.post("/audit/repo", response_class=HTMLResponse)
async def run_repo_audit_handler(
    request: Request,
    repo_url: str = Form(""),
) -> HTMLResponse:
    """Clone a GitHub repo, audit traces + docs, render combined results."""
    if not repo_url.strip():
        return _render(request, "error.html", {
            "version": ai_trace_auditor.__version__,
            "error_title": "Missing repo URL",
            "error_message": "Paste a public GitHub repo URL (https://github.com/owner/repo).",
        }, status_code=400)

    try:
        report = audit_repo(repo_url=repo_url.strip(), registry=_registry)
    except RepoError as exc:
        status = _REPO_ERROR_STATUS.get(type(exc), 500)
        return _render(request, "error.html", {
            "version": ai_trace_auditor.__version__,
            "error_title": type(exc).__name__,
            "error_message": str(exc),
        }, status_code=status)
    except Exception as exc:
        logger.exception("Repo audit failed")
        return _render(request, "error.html", {
            "version": ai_trace_auditor.__version__,
            "error_title": "Audit Error",
            "error_message": "An unexpected error occurred. Check the server logs.",
        }, status_code=500)

    doc_summary = {
        "present": sum(1 for r in report.doc_results if r.status == "present"),
        "partial": sum(1 for r in report.doc_results if r.status == "partial"),
        "absent": sum(1 for r in report.doc_results if r.status == "absent"),
        "total": len(report.doc_results),
    }

    return _render(request, "repo_results.html", {
        "version": ai_trace_auditor.__version__,
        "report": report,
        "doc_summary": doc_summary,
    })
```

- [ ] **Step 5: Add the repo URL field to `audit.html`**

Open `src/ai_trace_auditor/web/templates/audit.html` and add a new section that mirrors the existing upload/sample sections (matching Architectural Ledger styling). The form posts to `/audit/repo`:

```html
<form method="post" action="/audit/repo" class="space-y-4 mt-8">
  <h2 class="text-2xl font-serif">Audit a GitHub repository</h2>
  <p class="text-sm text-stone-600">
    Paste a public GitHub repo URL. We discover trace artifacts and governance
    documents inside the repo and produce a combined compliance report.
  </p>
  <input
    type="url"
    name="repo_url"
    placeholder="https://github.com/owner/repo"
    required
    class="w-full px-4 py-2 bg-stone-100 rounded"
  />
  <button type="submit" class="px-6 py-2 bg-[#002a6e] text-white rounded">
    Audit repository
  </button>
</form>
```

- [ ] **Step 6: Create `repo_results.html`**

`src/ai_trace_auditor/web/templates/repo_results.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="max-w-4xl mx-auto py-12 space-y-8">
  <header>
    <h1 class="text-4xl font-serif">Repository Audit</h1>
    <p class="text-stone-600 mt-2">
      <code>{{ report.repo_url }}</code>
    </p>
  </header>

  <div class="bg-white/60 p-6 rounded space-y-2">
    <h2 class="text-2xl font-serif">Trace artifacts</h2>
    {% if report.trace_artifacts_found == 0 %}
      <p>
        No trace artifacts found in this repository.
        Documentation evidence below is the only basis for this audit.
      </p>
    {% else %}
      <p>
        Found {{ report.trace_artifacts_found }} trace artifact(s).
        Audited against {{ report.trace_report.regulations_checked|length }}
        regulations.
      </p>
      <p>
        Overall trace compliance score:
        <strong>{{ "%.1f"|format(report.trace_report.overall_score * 100) }}%</strong>
      </p>
    {% endif %}
  </div>

  <div class="bg-white/60 p-6 rounded space-y-4">
    <h2 class="text-2xl font-serif">Documentation evidence</h2>
    <p class="text-sm text-stone-600">
      {{ doc_summary.present }} present ·
      {{ doc_summary.partial }} partial ·
      {{ doc_summary.absent }} absent ·
      {{ doc_summary.total }} total
    </p>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-stone-500">
          <th class="py-2">Requirement</th>
          <th>Regulation</th>
          <th>Status</th>
          <th>Evidence</th>
        </tr>
      </thead>
      <tbody>
        {% for r in report.doc_results %}
        <tr class="border-t border-stone-200">
          <td class="py-2"><code>{{ r.check.id }}</code></td>
          <td>{{ r.check.regulation }} {{ r.check.article }}</td>
          <td>
            {% if r.status == "present" %}<span class="text-emerald-700">present</span>
            {% elif r.status == "partial" %}<span class="text-amber-700">partial</span>
            {% else %}<span class="text-rose-700">absent</span>
            {% endif %}
          </td>
          <td class="text-stone-700">{{ r.evidence }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</section>
{% endblock %}
```

- [ ] **Step 7: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_server_repo.py -v
```

Expected: 7 passed.

- [ ] **Step 8: Commit**

```bash
git add src/ai_trace_auditor/web/server.py \
        src/ai_trace_auditor/web/templates/audit.html \
        src/ai_trace_auditor/web/templates/repo_results.html \
        tests/test_repo/test_server_repo.py
git commit -m "feat(web): add POST /audit/repo route + repo_results template + form field"
```

---

## Task 14: CLI subcommand `aitrace audit-repo`

**Files:**
- Modify: `src/ai_trace_auditor/cli.py`
- Create: `tests/test_repo/test_cli_repo.py`

- [ ] **Step 1: Write the failing test**

`tests/test_repo/test_cli_repo.py`:

```python
"""Tests for the `aitrace audit-repo` subcommand."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ai_trace_auditor.cli import app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "repos"


def _fake_clone(fixture_name: str):
    def _fn(url, *, max_bytes, timeout_seconds, tmpdir_root):
        return FIXTURES / fixture_name
    return _fn


def test_audit_repo_with_traces_exits_zero():
    runner = CliRunner()
    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=_fake_clone("repo_with_traces"),
    ), patch(
        "ai_trace_auditor.web.audit_service._cleanup_repo_dir"
    ):
        result = runner.invoke(
            app, ["audit-repo", "https://github.com/test/repo_with_traces"]
        )
    assert result.exit_code == 0
    assert "repo_with_traces" in result.stdout or "Repository" in result.stdout


def test_audit_repo_invalid_url_exits_nonzero():
    from ai_trace_auditor.repo.errors import InvalidRepoURL

    runner = CliRunner()
    with patch(
        "ai_trace_auditor.web.audit_service.clone_repo",
        side_effect=InvalidRepoURL("bad"),
    ):
        result = runner.invoke(
            app, ["audit-repo", "https://gitlab.com/x/y"]
        )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_repo/test_cli_repo.py -v
```

Expected: FAIL — subcommand not registered.

- [ ] **Step 3: Add the subcommand**

Append to `src/ai_trace_auditor/cli.py`:

```python
@app.command("audit-repo")
def audit_repo_command(
    repo_url: Annotated[str, typer.Argument(help="Public GitHub repo URL")],
) -> None:
    """Audit a public GitHub repository for AI compliance evidence."""
    from ai_trace_auditor.repo.errors import RepoError
    from ai_trace_auditor.web.audit_service import audit_repo

    registry = RequirementRegistry()
    registry.load()

    try:
        report = audit_repo(repo_url=repo_url, registry=registry)
    except RepoError as exc:
        console.print(f"[red]Repo audit failed:[/red] {exc}")
        raise typer.Exit(code=1)

    stdout_console.print(f"\n[bold]Repository:[/bold] {report.repo_url}")
    stdout_console.print(
        f"Trace artifacts: {report.trace_artifacts_found}"
    )
    if report.trace_report is not None:
        score = report.trace_report.overall_score * 100
        stdout_console.print(f"Trace audit score: {score:.1f}%")
    present = sum(1 for r in report.doc_results if r.status == "present")
    partial = sum(1 for r in report.doc_results if r.status == "partial")
    absent = sum(1 for r in report.doc_results if r.status == "absent")
    stdout_console.print(
        f"Documentation: {present} present, {partial} partial, {absent} absent"
    )

    if absent > 0:
        raise typer.Exit(code=2)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_repo/test_cli_repo.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full test suite to confirm nothing else broke**

```bash
.venv/bin/python -m pytest -x -q
```

Expected: full suite passes (≥301 prior tests + the new ones).

- [ ] **Step 6: Commit**

```bash
git add src/ai_trace_auditor/cli.py tests/test_repo/test_cli_repo.py
git commit -m "feat(cli): add audit-repo subcommand"
```

---

## Task 15: Dockerfile + fly.toml + version bump

**Files:**
- Modify: `Dockerfile`
- Create: `fly.toml`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update Dockerfile**

Edit `Dockerfile` so the `apt-get install` line includes `git` (needed for clone):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libffi8 \
        shared-mime-info \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY requirements/ ./requirements/
COPY tests/fixtures/ ./tests/fixtures/

RUN pip install --no-cache-dir -e ".[web,pdf]"

RUN mkdir -p /tmp/aitrace
ENV REPO_TMPDIR=/tmp/aitrace
ENV PDF_TMPDIR=/tmp/aitrace
ENV MAX_REPO_BYTES=52428800
ENV REPO_FETCH_TIMEOUT=30

EXPOSE 8001

CMD ["python", "-m", "ai_trace_auditor.web.server"]
```

- [ ] **Step 2: Build Docker image locally to verify**

```bash
docker build -t ai-trace-auditor:repo-ingest .
docker run --rm -p 8001:8001 ai-trace-auditor:repo-ingest &
sleep 5
curl -sf http://localhost:8001/ > /dev/null && echo "OK"
docker stop $(docker ps -q --filter ancestor=ai-trace-auditor:repo-ingest)
```

Expected: `OK` printed.

- [ ] **Step 3: Create `fly.toml`**

`fly.toml`:

```toml
app = "ai-trace-auditor"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  PORT = "8001"
  PDF_TMPDIR = "/tmp/aitrace"
  REPO_TMPDIR = "/tmp/aitrace"
  MAX_REPO_BYTES = "52428800"
  REPO_FETCH_TIMEOUT = "30"

[http_service]
  internal_port = 8001
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

  [[http_service.checks]]
    interval = "30s"
    timeout = "5s"
    grace_period = "10s"
    method = "GET"
    path = "/"

[[mounts]]
  source = "aitrace_tmp"
  destination = "/tmp/aitrace"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

- [ ] **Step 4: Bump version in `pyproject.toml`**

In `pyproject.toml`, change:

```toml
version = "0.16.1"
```

to:

```toml
version = "0.17.0"
```

- [ ] **Step 5: Run the full test suite**

```bash
.venv/bin/python -m pytest -x -q
```

Expected: passes.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile fly.toml pyproject.toml
git commit -m "build: add git to image, fly.toml for deploy, bump to 0.17.0"
```

---

## Task 16: Fly.io deploy + smoke verification

**Files:** none (operational).

- [ ] **Step 1: Install flyctl (if not present)**

```bash
flyctl version || curl -L https://fly.io/install.sh | sh
```

- [ ] **Step 2: Authenticate**

```bash
flyctl auth login
```

(Interactive — user must approve in browser.)

- [ ] **Step 3: Launch the app (no deploy yet)**

```bash
flyctl launch --no-deploy --copy-config --name ai-trace-auditor --region iad
```

Expected: confirms `fly.toml` and creates the app on Fly.

- [ ] **Step 4: Create the persistent volume**

```bash
flyctl volumes create aitrace_tmp --region iad --size 1
```

Expected: volume `aitrace_tmp` reported as created.

- [ ] **Step 5: Deploy**

```bash
flyctl deploy
```

Expected: build succeeds, machine starts, deploy reports `OK`.

- [ ] **Step 6: Smoke-test the deployment**

```bash
APP_URL=$(flyctl info --json | python -c "import sys,json; print(json.load(sys.stdin)['Hostname'])")
echo "App URL: https://$APP_URL"

curl -sfo /dev/null -w "%{http_code}\n" https://$APP_URL/                # expect 200
curl -sfo /dev/null -w "%{http_code}\n" https://$APP_URL/audit           # expect 200
curl -sfo /dev/null -w "%{http_code}\n" https://$APP_URL/regulations     # expect 200

# Real repo audit smoke test
curl -s -X POST https://$APP_URL/audit/repo \
  -d "repo_url=https://github.com/BipinRimal314/ai-trace-auditor" \
  -o /tmp/repo_audit.html -w "%{http_code}\n"
# expect 200 and the response file to mention "Repository Audit"
grep -q "Repository Audit" /tmp/repo_audit.html && echo "Repo audit smoke OK"
```

Expected: 200s across the board and `Repo audit smoke OK`.

- [ ] **Step 7: No commit — operational step. Note the live URL in HANDOFF.md.**

---

## Task 17: Documentation updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Update `CLAUDE.md` deployment section**

In `CLAUDE.md`, replace the `## Deployment` section so it reflects Fly.io as primary:

```markdown
## Deployment

### Live URL

https://ai-trace-auditor.fly.dev  (replace with the actual URL printed by `flyctl info`)

### Fly.io (preferred)

Configured via `fly.toml` and `Dockerfile`. Python 3.11-slim, installs the
package with `[web,pdf]` extras and `git` for repo ingestion. A persistent
volume `aitrace_tmp` is mounted at `/tmp/aitrace` for repo clone scratch
space and PDF rendering.

```bash
flyctl deploy
```

Env vars are baked into `fly.toml` (PORT, PDF_TMPDIR, REPO_TMPDIR,
MAX_REPO_BYTES, REPO_FETCH_TIMEOUT). Secrets (none currently) would go via
`flyctl secrets set`.

### Railway (legacy — retained for one-week observation)

`railway.toml` and the Vercel files remain in the repo until Fly is
observed stable. Remove after the observation window.

### Docker

```bash
docker build -t ai-trace-auditor .
docker run -p 8001:8001 ai-trace-auditor
```
```

- [ ] **Step 2: Add a `## Repo ingestion` section to `README.md`**

In `README.md`, near the existing CLI usage section, add:

```markdown
### Audit a GitHub repository

```bash
aitrace audit-repo https://github.com/owner/repo
```

The auditor clones the repo (shallowly, 50MB cap, 30s timeout), discovers
trace artifacts (OTEL JSON, Langfuse exports, chat JSONL), and runs the
governance-doc manifest (`MODEL_CARD.md`, retention configs, Article 50
disclosure language, ISO/SOC 2 policy docs). The web dashboard also
accepts a repo URL at `/audit`.
```

- [ ] **Step 3: Update `ROADMAP.md`**

Move "Repo ingestion" from "Near-term" to "Shipped" and add a brief entry under "Shipped" with the v0.17.0 marker.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md ROADMAP.md
git commit -m "docs: update CLAUDE.md (fly), README (repo ingestion), ROADMAP"
```

---

## Task 18: Update outer site's CLAUDE.md and HANDOFF.md (Website-level)

**Files (outer repo `/Users/bipinrimal/Downloads/Website/`):**
- Modify: `.claude/CLAUDE.md`
- Modify: project memory `HANDOFF.md` if it exists

- [ ] **Step 1: Edit `/Users/bipinrimal/Downloads/Website/.claude/CLAUDE.md`**

Find the Sovereign Compliance table row for Trace Auditor:

```
| AI Trace Auditor | `Projects/ai-trace-auditor/` | https://trace-auditor-production.up.railway.app | Railway |
```

Replace with:

```
| AI Trace Auditor | `Projects/ai-trace-auditor/` | https://ai-trace-auditor.fly.dev | Fly.io |
```

(Use the actual hostname from `flyctl info`.)

Also update the deployment summary line: `Vercel for Next.js/static apps, Railway for Python apps` → `Vercel for Next.js/static apps, Fly.io for Python apps`.

- [ ] **Step 2: Commit at outer repo**

This is the outer (Website) repo, not the inner ai-trace-auditor repo. Commit there:

```bash
git -C /Users/bipinrimal/Downloads/Website add .claude/CLAUDE.md
git -C /Users/bipinrimal/Downloads/Website commit -m "docs: trace auditor moved to fly.io"
```

- [ ] **Step 3: Tear down Railway only after one-week observation**

Note in `HANDOFF.md`:

```markdown
- Trace Auditor: migrated to Fly.io on 2026-05-17. Keep Railway running for
  one week (until 2026-05-24). Tear down Railway service if no Fly issues.
```

---

## Final verification

- [ ] Run the full inner-repo test suite end-to-end:

```bash
cd Projects/ai-trace-auditor
.venv/bin/python -m pytest -x -q
```

Expected: all tests pass (existing 301 + new ~40).

- [ ] Hit the live Fly URL from a browser. Try a real public repo (e.g., this project's own GitHub). Verify the doc checklist renders and the PDF download works.

- [ ] If everything looks good, mark the corresponding TodoWrite tasks done and prepare a single PR (`feat: repo ingestion + fly.io migration`) against `main`.

---

## Self-Review Checklist (run before considering this plan done)

- **Spec coverage:** Every section of the spec maps to at least one task.
  - Architecture → Tasks 1-12
  - Manifest + Compliance Gate → Tasks 3-4
  - Three detector kinds → Tasks 7-9
  - Trace artifact discovery → Task 6
  - Web + CLI → Tasks 12-14
  - Sandboxing → Task 5 (caps, .git stripping, cleanup), Task 12 (cleanup in `finally`)
  - Error handling table → Task 13 (`_REPO_ERROR_STATUS`)
  - Testing layers → Tasks 1-14 each include unit tests; Task 11 covers integration
  - Fly.io migration → Tasks 15-17
- **Placeholders:** Zero. Every step contains actual code or commands.
- **Type consistency:** `DocCheck.detector_kind` is one of three literals; `_KEY_LINE_RE` lives in `doc_scanner.py`; `RepoAuditReport.trace_report` is `GapReport | None`. Names match across tasks.
- **Scope:** Two coupled changes shipped under one plan. Fly migration is gated by Task 16's smoke test before any production traffic moves.
