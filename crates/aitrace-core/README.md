# aitrace-core

Native scanning core for [ai-trace-auditor](https://github.com/BipinRimal314/ai-trace-auditor).

This package is an optional accelerator. `ai-trace-auditor` runs correctly
without it; installing it makes codebase scanning faster and, for
JavaScript and TypeScript, more accurate.

```bash
pip install ai-trace-auditor[fast]   # pulls this in
```

## What it does

Walks a source tree in parallel and extracts three kinds of mechanical fact
from every Python, JavaScript, and TypeScript file:

- **imports** — every `import` / `from ... import` / `require()` / dynamic
  `import()` / re-export, reduced to the package it refers to
- **string literals** — the statically-knowable ones, so model identifiers and
  API URLs can be matched downstream
- **HTTP routes** — FastAPI/Flask decorators and Express-style registrations

## What it deliberately does not do

It does not know what any of that *means*. The tables that say
`@anthropic-ai/sdk` is an AI SDK, that `pinecone` is a vector database
requiring a DPA, or that `claude-opus-4` is a model identifier live in Python,
in `ai_trace_auditor.scanner.patterns`.

That split is deliberate. Those tables track a moving regulatory target and are
edited often; the parser is not. Compiling them into the extension would mean
rebuilding wheels for every platform to add a single provider.

Rust answers *what does this code do*. Python answers *does that matter under
the EU AI Act*.

## Why Rust rather than more Python

The JS/TS scanner it replaces matched imports with regular expressions, which
cannot tell an import from the same text inside a comment or a string, and
gives up entirely on a file with a syntax error. tree-sitter parses properly
and recovers from errors, so a file that fails to compile still yields findings.

Speed was the second reason, not the first. The walk is parallel across cores
with the GIL released, directories are pruned during traversal rather than
after, and an Aho-Corasick prefilter rejects the majority of files — the ones
mentioning none of the tracked identifiers — before a parser is ever started.

## Building from source

Requires a Rust toolchain (1.82+) and CPython 3.11+.

```bash
maturin develop --release            # build and install into the active venv
cargo test                           # Rust unit tests
cargo bench                          # criterion microbenchmarks
```

If the default `python3` on your `PATH` is older than 3.11, point pyo3 at a
newer interpreter explicitly:

```bash
PYO3_PYTHON=/path/to/python3.12 cargo test
```

Wheels are `abi3-py311`: one wheel per platform covers CPython 3.11 and every
version after it.

## License

Apache-2.0, matching the parent project.
