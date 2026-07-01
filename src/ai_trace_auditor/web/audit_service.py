"""Business logic layer for the web dashboard.

Wraps the existing CLI audit pipeline into functions suitable for web handlers.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ai_trace_auditor.analysis.dag_mermaid import generate_agent_dag_mermaid
from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.ingest.detect import ingest_file, parse_data
from ai_trace_auditor.models.gap import GapReport
from ai_trace_auditor.models.requirement import Requirement
from ai_trace_auditor.models.trace import NormalizedTrace
from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.repo import (
    clone_repo,
    combine_repo_report,
    find_trace_artifacts,
    load_manifest,
    scan_docs,
)
from ai_trace_auditor.repo.models import RepoAuditReport


def _get_fixtures_dir() -> Path:
    """Return the path to bundled test fixtures."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    return project_root / "tests" / "fixtures"


def load_registry() -> RequirementRegistry:
    """Load the requirement registry with all bundled regulations."""
    registry = RequirementRegistry()
    registry.load()
    return registry


def get_regulation_summary(registry: RequirementRegistry) -> list[dict[str, Any]]:
    """Build a summary of each regulation for the landing page."""
    regulation_meta = {
        "EU AI Act": {
            "icon": "scales",
            "nature": "Law",
            "description": "European Union regulation establishing harmonized rules on AI systems.",
            "status": "verified",
        },
        "NIST AI RMF": {
            "icon": "shield",
            "nature": "Voluntary Framework",
            "description": "US voluntary framework for managing risks in AI system design and deployment.",
            "status": "verified",
        },
        "ISO 42001": {
            "icon": "certificate",
            "nature": "Certifiable Standard (Beta)",
            "description": "International standard for AI management systems. Not verified against primary source (paid standard). Mappings are organizational guidance, not confirmed requirements.",
            "status": "beta",
        },
        "SOC 2 Trust Services Criteria": {
            "icon": "lock",
            "nature": "Audit Framework (Beta)",
            "description": "Trust services criteria with AI implementation guidance. There is no official AICPA AI addendum; these are our interpretive mappings of real TSC criteria to AI systems.",
            "status": "beta",
        },
        "LLM Observability Best Practices": {
            "icon": "eye",
            "nature": "Best Practices",
            "description": "Industry observability recommendations for production LLM systems.",
            "status": "verified",
        },
    }

    summaries = []
    for reg_name in registry.regulations:
        reqs = registry.get_by_regulation(reg_name)
        meta = regulation_meta.get(reg_name, {
            "icon": "file",
            "nature": "Unknown",
            "description": "",
        })
        summaries.append({
            "name": reg_name,
            "count": len(reqs),
            "icon": meta["icon"],
            "nature": meta["nature"],
            "description": meta["description"],
            "status": meta.get("status", "verified"),
            "mandatory": sum(1 for r in reqs if r.severity == "mandatory"),
            "recommended": sum(1 for r in reqs if r.severity == "recommended"),
            "best_practice": sum(1 for r in reqs if r.severity == "best_practice"),
        })

    return summaries


def get_sample_traces() -> list[dict[str, str]]:
    """List available sample trace files from test fixtures."""
    fixtures_dir = _get_fixtures_dir()
    if not fixtures_dir.is_dir():
        return []

    samples = []
    for path in sorted(fixtures_dir.glob("*.json")):
        name = path.stem.replace("_", " ").title()
        samples.append({"name": name, "filename": path.name})

    for path in sorted(fixtures_dir.glob("*.jsonl")):
        name = path.stem.replace("_", " ").title()
        samples.append({"name": name, "filename": path.name})

    return samples


def load_traces_from_upload(content: bytes, filename: str) -> list[NormalizedTrace]:
    """Parse uploaded trace file content into normalized traces."""
    with tempfile.NamedTemporaryFile(
        suffix=Path(filename).suffix, delete=False, mode="wb"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        return ingest_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def load_traces_from_sample(filename: str) -> list[NormalizedTrace]:
    """Load traces from a bundled sample fixture file."""
    fixtures_dir = _get_fixtures_dir()
    path = fixtures_dir / filename

    if not path.exists():
        raise FileNotFoundError(f"Sample trace not found: {filename}")

    # Reject path traversal
    if not path.resolve().is_relative_to(fixtures_dir.resolve()):
        raise ValueError("Invalid filename")

    return ingest_file(path)


def run_audit(
    traces: list[NormalizedTrace],
    registry: RequirementRegistry,
    regulation_filter: str | None = None,
    trace_source: str = "web_upload",
) -> GapReport:
    """Run compliance audit on traces and return the gap report."""
    analyzer = ComplianceAnalyzer(registry)
    regulations = [regulation_filter] if regulation_filter else None
    return analyzer.analyze(
        traces,
        regulations=regulations,
        trace_source=trace_source,
    )


def build_results_context(
    report: GapReport,
    traces: list[NormalizedTrace],
) -> dict[str, Any]:
    """Transform a GapReport into template-friendly context data."""
    results_by_status: dict[str, list[dict[str, Any]]] = {
        "satisfied": [],
        "partial": [],
        "missing": [],
        "not_applicable": [],
    }

    for rr in report.requirement_results:
        entry = {
            "id": rr.requirement.id,
            "title": rr.requirement.title,
            "regulation": rr.requirement.regulation,
            "article": rr.requirement.article,
            "description": rr.requirement.description,
            "legal_text": rr.requirement.legal_text or "N/A",
            "severity": rr.requirement.severity,
            "compliance_tier": rr.requirement.compliance_tier or "untiered",
            "status": rr.status,
            "score": round(rr.coverage_score * 100, 1),
            "gaps": [
                {
                    "field": g.field_path,
                    "description": g.description,
                    "impact": g.impact,
                    "recommendation": g.recommendation,
                }
                for g in rr.gaps
            ],
            "evidence": [
                {
                    "field": e.field_path,
                    "coverage": round(e.coverage_pct * 100, 1),
                    "present": e.present_count,
                    "total": e.population,
                }
                for e in rr.evidence
            ],
        }
        results_by_status[rr.status].append(entry)

    # Build Mermaid DAG for multi-agent traces
    mermaid_diagram = None
    is_multi_agent = any(t.is_multi_agent for t in traces)
    if is_multi_agent:
        for trace in traces:
            if trace.is_multi_agent:
                mermaid_diagram = generate_agent_dag_mermaid(
                    trace, report.agent_scores
                )
                if mermaid_diagram:
                    break

    return {
        "score": round(report.overall_score * 100, 1),
        "trace_count": report.trace_count,
        "span_count": report.span_count,
        "regulations_checked": report.regulations_checked,
        "summary": {
            "satisfied": report.summary.satisfied,
            "partial": report.summary.partial,
            "missing": report.summary.missing,
            "not_applicable": report.summary.not_applicable,
            "total": (
                report.summary.satisfied
                + report.summary.partial
                + report.summary.missing
            ),
            "top_gaps": report.summary.top_gaps,
        },
        "tiered_scores": [
            {
                "tier": ts.tier,
                "label": ts.label,
                "score": round(ts.score * 100, 1),
                "count": ts.requirement_count,
                "satisfied": ts.satisfied,
                "gaps": ts.gaps,
            }
            for ts in report.tiered_scores
        ],
        "results_by_status": results_by_status,
        "agent_scores": (
            {k: round(v * 100, 1) for k, v in report.agent_scores.items()}
            if report.agent_scores
            else None
        ),
        "mermaid_diagram": mermaid_diagram,
        "is_multi_agent": is_multi_agent,
    }


def get_regulations_detail(
    registry: RequirementRegistry,
) -> list[dict[str, Any]]:
    """Build detailed regulation data for the regulations browser."""
    grouped: dict[str, list[Requirement]] = {}
    for req in registry.get_all():
        grouped.setdefault(req.regulation, []).append(req)

    beta_frameworks = {"ISO 42001", "SOC 2 Trust Services Criteria"}

    result = []
    for reg_name in sorted(grouped.keys()):
        reqs = grouped[reg_name]
        articles: dict[str, list[dict[str, Any]]] = {}
        for req in reqs:
            article_reqs = articles.setdefault(req.article, [])
            article_reqs.append({
                "id": req.id,
                "title": req.title,
                "description": req.description,
                "legal_text": req.legal_text or "N/A",
                "severity": req.severity,
                "compliance_tier": req.compliance_tier or "untiered",
                "check_type": req.check_type or "trace",
                "verified": req.verified_against_primary,
            })

        result.append({
            "name": reg_name,
            "total": len(reqs),
            "is_beta": reg_name in beta_frameworks,
            "articles": [
                {"name": article, "requirements": reqs_list}
                for article, reqs_list in articles.items()
            ],
        })

    return result


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
    """Orchestrate clone -> find traces -> scan docs -> audit traces -> combine."""
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
