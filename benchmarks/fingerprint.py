"""Order-independent content fingerprints for scan results.

The Rust core must produce byte-identical findings to the Python scanners it
replaces. Wall-clock benchmarks are meaningless if the faster implementation
quietly finds different things, so every benchmark run also emits a
fingerprint: a hash over the normalized, sorted findings with paths made
relative to the scan root.

Two implementations agree iff their fingerprints match.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai_trace_auditor.models.docs import CodeScanResult
from ai_trace_auditor.models.flow import FlowScanResult

# Fields excluded from every fingerprint: they record how long the scan took or
# where it ran, not what it found.
_VOLATILE_FIELDS = {"scan_duration_ms", "scanned_dir", "file_count"}


def _rel(path: str, root: Path) -> str:
    """Make a finding's file path relative to the scan root, POSIX-normalized.

    Absolute paths differ between machines and between a Python and a Rust
    walker that resolve symlinks differently; the relative path is the part
    that actually identifies the finding.
    """
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # Outside the scan root (symlink escape) — keep the basename only.
        return Path(path).name


def _normalize(item: Any, root: Path) -> Any:
    """Recursively normalize a finding into a canonical, comparable form."""
    if isinstance(item, dict):
        out = {}
        for key, value in item.items():
            if key in _VOLATILE_FIELDS:
                continue
            if key == "file_path" and isinstance(value, str):
                out[key] = _rel(value, root)
            else:
                out[key] = _normalize(value, root)
        return out
    if isinstance(item, list):
        return [_normalize(v, root) for v in item]
    return item


def _hash_collection(items: list[Any], root: Path) -> str:
    """Hash a list of findings independent of the order they were produced in.

    A parallel walker returns files in nondeterministic order. That is a
    legitimate implementation difference, not a behavioral one, so each finding
    is serialized and the serializations are sorted before hashing.
    """
    encoded = sorted(
        json.dumps(_normalize(item, root), sort_keys=True, separators=(",", ":"))
        for item in items
    )
    digest = hashlib.blake2b(digest_size=16)
    for line in encoded:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def fingerprint_code_scan(result: CodeScanResult, root: Path) -> dict[str, str]:
    """Per-category fingerprints for a CodeScanResult.

    Per-category rather than one combined hash so that a mismatch points at
    which detector diverged instead of just reporting "different".
    """
    dumped = result.model_dump(mode="json")
    return {
        category: _hash_collection(dumped.get(category, []), root)
        for category in (
            "ai_imports",
            "model_references",
            "vector_dbs",
            "training_data_refs",
            "eval_scripts",
            "deployment_configs",
            "ai_endpoints",
        )
    }


def fingerprint_flow_scan(result: FlowScanResult, root: Path) -> dict[str, str]:
    """Per-category fingerprints for a FlowScanResult."""
    dumped = result.model_dump(mode="json")
    return {
        category: _hash_collection(dumped.get(category, []), root)
        for category in (
            "external_services",
            "data_flows",
            "http_clients",
            "databases",
            "file_io",
            "cloud_services",
        )
    }


def diff_fingerprints(
    expected: dict[str, str], actual: dict[str, str]
) -> list[str]:
    """Return the categories whose fingerprints disagree."""
    return sorted(
        category
        for category in expected.keys() | actual.keys()
        if expected.get(category) != actual.get(category)
    )
