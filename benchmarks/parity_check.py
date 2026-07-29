"""Differential check: native core vs pure-Python scanners.

Runs both implementations over the same corpora and compares their findings
category by category using the fingerprints in `fingerprint.py`.

The two paths are held to different standards on purpose:

* **Python files** must agree exactly. Both parse a real AST, so any difference
  is a bug.
* **JavaScript/TypeScript files** are expected to differ. The implementation
  being replaced matched imports with regexes applied line by line and could
  not tell code from a comment. Differences there are reported as a diff for
  inspection rather than as failures — see `native.KNOWN_DIVERGENCES`.

Usage:
    python benchmarks/parity_check.py benchmarks/corpora/*
    python benchmarks/parity_check.py --lang py <dir>     # exact-match subset
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Runner script executed in a subprocess so each implementation gets a clean
# interpreter. `AITRACE_NO_NATIVE` is read at call time, but the pattern tables
# and the native module are bound at import time, so switching inside one
# process would compare two half-initialized states.
_RUNNER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, {src!r})
sys.path.insert(0, {bench!r})
from ai_trace_auditor.scanner.scan import scan_codebase, use_native_scanner
from fingerprint import fingerprint_code_scan

root = Path(sys.argv[1])
only = sys.argv[2] if len(sys.argv) > 2 else ""
result = scan_codebase(root)

if only:
    exts = {{".py", ".pyi"}} if only == "py" else {{".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}}
    def keep(items):
        return [i for i in items if Path(getattr(i, "file_path", "")).suffix.lower() in exts]
    result = result.model_copy(update={{
        "ai_imports": keep(result.ai_imports),
        "model_references": keep(result.model_references),
        "vector_dbs": keep(result.vector_dbs),
        "training_data_refs": keep(result.training_data_refs),
        "eval_scripts": keep(result.eval_scripts),
        "ai_endpoints": keep(result.ai_endpoints),
    }})

counts = {{
    "ai_imports": len(result.ai_imports),
    "model_references": len(result.model_references),
    "vector_dbs": len(result.vector_dbs),
    "training_data_refs": len(result.training_data_refs),
    "eval_scripts": len(result.eval_scripts),
    "ai_endpoints": len(result.ai_endpoints),
}}
print(json.dumps({{
    "native": use_native_scanner(),
    "fingerprints": fingerprint_code_scan(result, root),
    "counts": counts,
}}))
"""


def run_scan(root: Path, native: bool, only: str = "") -> dict:
    """Run one scan in a subprocess and return its fingerprints and counts."""
    import json

    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT / "src")
    if not native:
        env["AITRACE_NO_NATIVE"] = "1"
    else:
        env.pop("AITRACE_NO_NATIVE", None)

    code = _RUNNER.format(src=str(_ROOT / "src"), bench=str(Path(__file__).resolve().parent))
    proc = subprocess.run(
        [sys.executable, "-c", code, str(root), only],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"scan failed ({'native' if native else 'python'}):\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def compare(root: Path, only: str) -> tuple[bool, list[str]]:
    """Compare both implementations on one corpus. Returns (agreed, notes)."""
    from fingerprint import diff_fingerprints

    py = run_scan(root, native=False, only=only)
    rs = run_scan(root, native=True, only=only)

    if not rs["native"]:
        raise RuntimeError("native core not installed; nothing to compare")
    if py["native"]:
        raise RuntimeError("AITRACE_NO_NATIVE did not disable the native path")

    mismatched = diff_fingerprints(py["fingerprints"], rs["fingerprints"])
    notes = []
    for category in mismatched:
        notes.append(
            f"    {category}: python={py['counts'][category]} native={rs['counts'][category]}"
        )
    return not mismatched, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpora", nargs="+", type=Path)
    parser.add_argument(
        "--lang",
        choices=["py", "js", "all"],
        default="all",
        help="restrict comparison to one language (py must match exactly)",
    )
    args = parser.parse_args()

    only = "" if args.lang == "all" else args.lang
    strict = args.lang == "py"

    failures = 0
    for corpus in args.corpora:
        if not corpus.is_dir():
            continue
        agreed, notes = compare(corpus, only)
        status = "MATCH" if agreed else "DIFF "
        print(f"[{status}] {corpus.name} ({args.lang})")
        for note in notes:
            print(note)
        if not agreed and strict:
            failures += 1

    print()
    if strict:
        if failures:
            print(f"FAIL: {failures} corpus/corpora diverged on Python files")
            return 1
        print("PASS: native and pure-Python agree exactly on all Python files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
