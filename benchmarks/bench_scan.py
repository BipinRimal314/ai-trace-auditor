"""Benchmark the codebase scanner against real repositories.

Establishes the baseline the Rust core (`aitrace-core`) has to beat, and
records a content fingerprint per corpus so the Rust port can be proven
equivalent rather than merely faster.

Usage:
    python benchmarks/bench_scan.py <corpus-dir> [<corpus-dir> ...]
    python benchmarks/bench_scan.py --repeat 5 --json results.json <dir>

Each corpus is scanned `--repeat` times; the reported figure is the minimum
wall time, not the mean. Minimum is the right statistic here because noise from
other processes on the machine can only ever make a run slower, so the fastest
observed run is the closest estimate of the true cost.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Allow running straight from a checkout without installing the package.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_trace_auditor.flow.detector import detect_flows  # noqa: E402
from ai_trace_auditor.scanner import native  # noqa: E402
from ai_trace_auditor.scanner.scan import scan_codebase, use_native_scanner  # noqa: E402
from fingerprint import fingerprint_code_scan, fingerprint_flow_scan  # noqa: E402


@dataclass
class PhaseResult:
    """Timing for one scan phase across all repetitions."""

    name: str
    times_s: list[float]
    file_count: int
    findings: int
    fingerprints: dict[str, str] = field(default_factory=dict)

    @property
    def best_s(self) -> float:
        return min(self.times_s)

    @property
    def median_s(self) -> float:
        return statistics.median(self.times_s)

    @property
    def files_per_s(self) -> float:
        return self.file_count / self.best_s if self.best_s > 0 else 0.0


@dataclass
class CorpusResult:
    """All phase results for a single corpus directory."""

    corpus: str
    source_files: int
    bytes_scanned: int
    phases: list[PhaseResult]


# Extensions the scanners actually dispatch on, used only to report corpus size.
_SOURCE_EXTS = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def measure_corpus(root: Path, repeat: int) -> CorpusResult:
    """Scan one corpus `repeat` times and collect timings and fingerprints."""
    source_files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in _SOURCE_EXTS:
            source_files += 1
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass

    phases: list[PhaseResult] = []

    # Phase 1: AI SDK / model / vector-DB detection (Python AST + JS regex).
    times: list[float] = []
    scan_result = None
    for _ in range(repeat):
        start = time.perf_counter()
        scan_result = scan_codebase(root)
        times.append(time.perf_counter() - start)
    assert scan_result is not None
    phases.append(
        PhaseResult(
            name="scan_codebase",
            times_s=times,
            file_count=scan_result.file_count,
            findings=(
                len(scan_result.ai_imports)
                + len(scan_result.model_references)
                + len(scan_result.vector_dbs)
                + len(scan_result.ai_endpoints)
            ),
            fingerprints=fingerprint_code_scan(scan_result, root),
        )
    )

    # Phase 2: data-flow / external-service detection. Fed the phase-1 result
    # the same way the CLI does, so the timing reflects real usage.
    times = []
    flow_result = None
    for _ in range(repeat):
        start = time.perf_counter()
        flow_result = detect_flows(root, scan_result)
        times.append(time.perf_counter() - start)
    assert flow_result is not None
    phases.append(
        PhaseResult(
            name="detect_flows",
            times_s=times,
            file_count=flow_result.file_count,
            findings=(
                len(flow_result.external_services)
                + len(flow_result.http_clients)
                + len(flow_result.databases)
                + len(flow_result.cloud_services)
                + len(flow_result.file_io)
            ),
            fingerprints=fingerprint_flow_scan(flow_result, root),
        )
    )

    return CorpusResult(
        corpus=str(root),
        source_files=source_files,
        bytes_scanned=total_bytes,
        phases=phases,
    )


def print_report(results: list[CorpusResult]) -> None:
    """Print a human-readable table of the benchmark results."""
    print()
    impl = "native (aitrace-core)" if use_native_scanner() else "pure Python"
    print(f"implementation: {impl}")
    print(f"{'corpus':<34} {'phase':<15} {'files':>7} {'best':>9} {'files/s':>9} {'found':>6}")
    print("-" * 84)
    for result in results:
        label = Path(result.corpus).name[:33]
        for phase in result.phases:
            print(
                f"{label:<34} {phase.name:<15} {phase.file_count:>7} "
                f"{phase.best_s * 1000:>8.0f}ms {phase.files_per_s:>9.0f} "
                f"{phase.findings:>6}"
            )
            label = ""
    print()

    total_best = sum(p.best_s for r in results for p in r.phases)
    total_files = sum(p.file_count for r in results for p in r.phases)
    print(f"Total: {total_files} file-scans in {total_best:.2f}s "
          f"({total_files / total_best:.0f} files/s aggregate)")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpora", nargs="+", type=Path, help="directories to scan")
    parser.add_argument("--repeat", type=int, default=3, help="repetitions per phase")
    parser.add_argument("--json", type=Path, help="write full results as JSON")
    args = parser.parse_args()

    results: list[CorpusResult] = []
    for corpus in args.corpora:
        if not corpus.is_dir():
            print(f"skipping {corpus}: not a directory", file=sys.stderr)
            continue
        print(f"scanning {corpus} ...", file=sys.stderr)
        results.append(measure_corpus(corpus, args.repeat))

    if not results:
        print("no corpora scanned", file=sys.stderr)
        return 1

    print_report(results)

    if args.json:
        payload = {
            "implementation": "native" if use_native_scanner() else "python",
            "native_version": native.version() if use_native_scanner() else None,
            "platform": {
                "python": platform.python_version(),
                "machine": platform.machine(),
                "system": platform.system(),
            },
            "repeat": args.repeat,
            "results": [asdict(r) for r in results],
        }
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"wrote {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
