//! Native scanning core for `ai-trace-auditor`.
//!
//! # What lives here, and what deliberately does not
//!
//! This crate walks a source tree and extracts mechanical facts: imports,
//! string literals, HTTP routes. It has no idea which of those matter.
//!
//! The knowledge that `@anthropic-ai/sdk` is an AI SDK, that `pinecone` is a
//! vector database needing a DPA, or that `claude-opus-4` is a model identifier
//! stays in Python, in `ai_trace_auditor.scanner.patterns`. Those tables track
//! a moving regulatory target and get edited often; the parser does not. If the
//! tables were compiled in, adding one provider would mean rebuilding wheels
//! for every platform.
//!
//! So the split is: Rust answers "what does this code do", Python answers
//! "does that matter under the EU AI Act".

use std::path::PathBuf;

use pyo3::prelude::*;
use pyo3::types::PyDict;

pub mod extract;
pub mod matching;
pub mod walk;

use walk::{ScanOptions, ScanOutcome};

/// Facts extracted from a single source file, as seen from Python.
#[pyclass(module = "aitrace_core", frozen, get_all)]
pub struct FileScan {
    /// Absolute path to the scanned file.
    pub path: String,
    /// `(module, qualified_path, line)` for each import.
    pub imports: Vec<(String, String, usize)>,
    /// `(value, line)` for each statically-known string literal.
    pub strings: Vec<(String, usize)>,
    /// `(method, path, line)` for each HTTP route registration.
    pub routes: Vec<(String, String, usize)>,
    /// `(pattern_index, line, context)` for each line-pattern hit.
    pub line_matches: Vec<(usize, usize, String)>,
    /// `(pattern_index, matched_text, line, context)` for each literal hit.
    pub string_matches: Vec<(usize, String, usize, String)>,
    /// True when the file contained syntax errors and coverage is partial.
    pub had_parse_errors: bool,
}

#[pymethods]
impl FileScan {
    fn __repr__(&self) -> String {
        format!(
            "FileScan(path={:?}, imports={}, strings={}, routes={})",
            self.path,
            self.imports.len(),
            self.strings.len(),
            self.routes.len()
        )
    }
}

/// Aggregate coverage counters for a scan.
#[pyclass(module = "aitrace_core", frozen, get_all)]
pub struct ScanStats {
    pub files_considered: usize,
    pub files_parsed: usize,
    pub files_too_large: usize,
    pub files_unreadable: usize,
}

#[pymethods]
impl ScanStats {
    fn __repr__(&self) -> String {
        format!(
            "ScanStats(considered={}, parsed={}, too_large={}, unreadable={})",
            self.files_considered, self.files_parsed, self.files_too_large, self.files_unreadable
        )
    }
}

/// The full result of a scan.
#[pyclass(module = "aitrace_core", frozen, get_all)]
pub struct ScanResult {
    pub files: Vec<Py<FileScan>>,
    pub stats: Py<ScanStats>,
}

fn to_py(py: Python<'_>, outcome: ScanOutcome) -> PyResult<ScanResult> {
    let mut files = Vec::with_capacity(outcome.files.len());
    for scanned in outcome.files {
        let facts = scanned.facts;
        files.push(Py::new(
            py,
            FileScan {
                path: scanned.path.to_string_lossy().into_owned(),
                imports: facts
                    .imports
                    .into_iter()
                    .map(|i| (i.module, i.qualified, i.line))
                    .collect(),
                // The raw literals are intentionally not shipped across the
                // boundary: a large repository has millions of them and the
                // caller only ever wants the ones that matched a pattern.
                strings: Vec::new(),
                routes: facts
                    .routes
                    .into_iter()
                    .map(|r| (r.method, r.path, r.line))
                    .collect(),
                line_matches: scanned
                    .line_matches
                    .into_iter()
                    .map(|m| (m.pattern_index, m.line, m.context))
                    .collect(),
                string_matches: scanned
                    .string_matches
                    .into_iter()
                    .map(|m| (m.pattern_index, m.matched, m.line, m.context))
                    .collect(),
                had_parse_errors: facts.had_parse_errors,
            },
        )?);
    }

    let stats = Py::new(
        py,
        ScanStats {
            files_considered: outcome.counters.considered,
            files_parsed: outcome.counters.parsed,
            files_too_large: outcome.counters.too_large,
            files_unreadable: outcome.counters.unreadable,
        },
    )?;

    Ok(ScanResult { files, stats })
}

/// Walk `root` and extract imports, routes, and pattern matches.
///
/// `skip_dirs` are directory names pruned during traversal. `prefilter` is a
/// list of literal substrings; a file containing none of them is never parsed,
/// so callers should pass every identifier their import tables can match. An
/// empty `prefilter` disables the optimization and parses everything.
///
/// `line_patterns` are matched against every source line and `string_patterns`
/// against every string literal. Both are reported as indices back into the
/// lists the caller passed, so the caller keeps ownership of what they mean.
///
/// Only files with at least one finding are returned; use `stats` for coverage.
#[pyfunction]
#[pyo3(signature = (
    root,
    skip_dirs=None,
    prefilter=None,
    line_patterns=None,
    string_patterns=None,
    threads=0,
    respect_gitignore=false,
))]
#[allow(clippy::too_many_arguments)]
fn scan_tree(
    py: Python<'_>,
    root: PathBuf,
    skip_dirs: Option<Vec<String>>,
    prefilter: Option<Vec<String>>,
    line_patterns: Option<Vec<String>>,
    string_patterns: Option<Vec<String>>,
    threads: usize,
    respect_gitignore: bool,
) -> PyResult<ScanResult> {
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyNotADirectoryError::new_err(format!(
            "not a directory: {}",
            root.display()
        )));
    }

    let options = ScanOptions {
        skip_dirs: skip_dirs.unwrap_or_default(),
        prefilter: prefilter.unwrap_or_default(),
        line_patterns: line_patterns.unwrap_or_default(),
        string_patterns: string_patterns.unwrap_or_default(),
        threads,
        respect_gitignore,
    };

    // Release the GIL for the walk. The workers touch no Python objects, so
    // holding it would serialize them against each other and against any other
    // Python thread for the entire scan.
    let outcome = py
        .detach(move || walk::scan_tree(&root, &options))
        // A pattern the Rust engine cannot compile is a caller error, not an
        // internal fault: surface it as ValueError naming the pattern.
        .map_err(pyo3::exceptions::PyValueError::new_err)?;

    to_py(py, outcome)
}

/// Extract facts from a single in-memory source string.
///
/// Exists for the differential tests, which feed identical source to the Rust
/// and Python implementations without touching the filesystem.
#[pyfunction]
fn extract_source(py: Python<'_>, source: &str, extension: &str) -> PyResult<Option<FileScan>> {
    let Some(lang) = extract::Language::from_extension(&extension.to_ascii_lowercase()) else {
        return Ok(None);
    };

    let owned = source.to_owned();
    let result = py.detach(move || {
        let mut extractor = extract::Extractor::new().ok()?;
        extractor.extract(&owned, lang)
    });

    Ok(result.map(|facts| FileScan {
        path: String::new(),
        imports: facts
            .imports
            .into_iter()
            .map(|i| (i.module, i.qualified, i.line))
            .collect(),
        // Unlike `scan_tree`, the single-file entry point does return every
        // literal: it exists for the differential tests, which need to compare
        // exactly what each implementation saw.
        strings: facts
            .strings
            .into_iter()
            .map(|s| (s.value, s.line))
            .collect(),
        routes: facts
            .routes
            .into_iter()
            .map(|r| (r.method, r.path, r.line))
            .collect(),
        line_matches: Vec::new(),
        string_matches: Vec::new(),
        had_parse_errors: facts.had_parse_errors,
    }))
}

/// Languages this build can parse, so Python can fall back for the rest.
#[pyfunction]
fn supported_extensions() -> Vec<String> {
    [
        "py", "pyi", "js", "mjs", "cjs", "jsx", "ts", "mts", "cts", "tsx",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect()
}

#[pymodule]
fn aitrace_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<FileScan>()?;
    m.add_class::<ScanStats>()?;
    m.add_class::<ScanResult>()?;
    m.add_function(wrap_pyfunction!(scan_tree, m)?)?;
    m.add_function(wrap_pyfunction!(extract_source, m)?)?;
    m.add_function(wrap_pyfunction!(supported_extensions, m)?)?;

    // Expose the build's thread default so the Python side can report it.
    let meta = PyDict::new(m.py());
    meta.set_item(
        "available_parallelism",
        std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(0),
    )?;
    m.add("build_info", meta)?;
    Ok(())
}
