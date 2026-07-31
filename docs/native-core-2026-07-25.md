# The native scanning core: what it changed and what it found

*2026-07-25 — `aitrace-core` v0.1.0*

The codebase scanner now has an optional native implementation. `ai-trace-auditor`
works exactly as before without it; installing `aitrace-core` makes scanning
about ten times faster and fixes two defects that had been quietly affecting
audit output.

The bugs are the more important half of this. They were not found by reading
the code — they were found by building a second implementation and making the
two disagree in public.

## Results

Scanning four public AI codebases (14,876 source files), best of three runs,
M4 Pro, 12 cores:

| corpus    | files  | pure Python | native  | speedup |
|-----------|--------|-------------|---------|---------|
| dify      | 10,519 | 9,764 ms    | 1,108 ms| 8.8×    |
| langchain | 2,534  | 2,690 ms    | 241 ms  | 11.2×   |
| crewai    | 1,272  | 2,698 ms    | 188 ms  | 14.3×   |
| haystack  | 551    | 1,261 ms    | 88 ms   | 14.3×   |
| **total** | 14,876 | **16,413 ms**| **1,626 ms** | **10.1×** |

Reproduce with:

```bash
benchmarks/fetch_corpora.sh                       # pinned public repos
python benchmarks/bench_scan.py benchmarks/corpora/*
AITRACE_NO_NATIVE=1 python benchmarks/bench_scan.py benchmarks/corpora/*
```

Data flow detection (`flow/detector.py`) is **not** ported and shows no
improvement — it remains the dominant cost of a full audit, at roughly 8
seconds on Dify. The headline figure above is the codebase scan alone, not an
end-to-end audit.

## The two defects

### 1. Relative imports counted as third-party SDK usage

`from .openai import LocalGenerator` imports a *local submodule*. CPython's
`ast` module splits the leading dots off into a separate `level` field, so
`ImportFrom.module` is the bare string `"openai"` — indistinguishable, to the
scanner, from `from openai import OpenAI`.

Every package whose own submodule shares a name with a tracked SDK was
affected. Haystack is a real case: `haystack/components/generators/chat/__init__.py`
was reported as OpenAI SDK usage on the strength of `from .openai import ...`.
On Dify this removed 3 of 7 reported Python AI imports.

This matters beyond a miscount. The scanner's output feeds Annex IV technical
documentation and GDPR processor classification. A phantom OpenAI dependency
means a phantom "processor, PII likely" entry in a compliance document.

tree-sitter keeps the dots in the module path, so relative imports no longer
match. Absolute imports are unaffected, which the test suite pins explicitly.

### 2. A syntax error silently disabled import detection

`python_scanner.scan_python_file` wrapped `ast.parse` in a `try`, and on
`SyntaxError` fell back to `_scan_lines` — a regex pass that detects training
data and eval metrics but has **no import detection at all**. A file that
failed to parse therefore reported zero imports, with no warning.

CrewAI ships Jinja-templated `.py` files ({% raw %}`class {{crew_name}}():`{% endraw %}) that are
not valid Python. Three of them import `crewai` on line 1 and were entirely
invisible to the scanner.

This is the failure mode that matters most for a compliance tool: it is silent,
and it fails toward "nothing to declare". tree-sitter recovers from syntax
errors and keeps parsing, so those imports are now found.

### Why regex-vs-parser matters for JS/TS

The JavaScript and TypeScript scanner matched imports with regular expressions
applied one line at a time. That cannot distinguish code from a comment or a
string literal, and it misses any import spanning multiple lines — which is
most of them in formatted TypeScript. Both are fixed by parsing properly, and
both are pinned by tests.

## How equivalence was established

Wall-clock numbers are worthless if the faster implementation quietly finds
different things. Two mechanisms guard against that.

**Fingerprints.** `benchmarks/fingerprint.py` hashes the normalized, sorted
findings per category, with paths made relative and timing fields excluded.
`benchmarks/parity_check.py` runs both implementations over the same corpus in
separate interpreters and diffs the hashes. That is how both bugs surfaced:
as unexplained hash mismatches on real repositories, which then had to be
explained one at a time.

**A divergence registry.** `native.KNOWN_DIVERGENCES` documents every intended
difference, and `tests/test_scanner/test_native_parity.py` has one test per
entry plus a meta-test asserting the two sets match exactly. A behaviour change
cannot ship without either a test or an admission that it is undocumented.

## Design: what is in Rust and what is not

The Rust crate walks the tree, reads files, parses them, and runs regexes. It
does not know what any of it means.

Every table encoding compliance knowledge — which packages are AI SDKs, which
are vector databases, what a model identifier looks like — stays in
`scanner/patterns.py` and is passed across the boundary on each call. Results
come back as indices into the caller's own lists.

That split is deliberate. The pattern tables track a moving regulatory target
and are edited often; the parser is not. Compiling the tables into the
extension would mean rebuilding wheels for every platform to add one provider.

Where the speed comes from, in rough order of contribution:

- **Parallelism.** The walk runs one worker per core with the GIL released.
- **Pruning during traversal.** The Python walker called `rglob("*")` and
  stat'd every file in the tree — including all of `node_modules` — before
  discarding most by extension. Directories are now pruned before descending.
- **One traversal instead of two.** `scan_python_file` ran `ast.walk` twice per
  file, once for imports and once for string literals.
- **`RegexSet` instead of a loop.** Running every line pattern against every
  line independently worked out to 13.5 million regex searches on LangChain
  alone. A `RegexSet` answers "which of these match" in one pass.
- **An Aho-Corasick prefilter** rejects files mentioning none of the tracked
  identifiers before a parser is started.

## A performance trap worth recording

Endpoint detection stayed in Python: it needs a two-line lookahead and has
framework-specific fallbacks, and reimplementing it in Rust would have risked
divergence for little gain.

The first version re-ran the full Python scanner on every file that imported an
AI SDK. On a repository like LangChain that is most of the codebase, and the
speedup collapsed from 11× to 1.08× — the native pass was doing all its work,
then Python redid it. Gating the fallback on a route-declaration hint, gathered
during the native pass, restored it.

The general lesson: when accelerating part of a pipeline, measure what fraction
of the input still reaches the slow path. A fallback taken by 60% of files is
not a fallback.

## Installing

```bash
pip install ai-trace-auditor[fast]
```

Wheels are `abi3-py311`: one per platform covers CPython 3.11 and every later
version. `AITRACE_NO_NATIVE=1` forces the pure-Python path.

## Still to do

- Port `flow/detector.py`, now the dominant cost of an audit.
- Publish `aitrace-core` to PyPI and add a `maturin` wheel-building CI matrix.
- Add a CI job that runs the test suite with `AITRACE_NO_NATIVE=1` so the
  pure-Python path cannot rot.
- Decide whether the two fixed defects warrant re-running any audits already
  filed as evidence.
