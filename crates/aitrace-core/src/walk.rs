//! Parallel source-tree traversal and file reading.
//!
//! Replaces a single-threaded `Path.rglob("*")` that stat'd every file in the
//! tree — including the tens of thousands inside `node_modules` — before
//! discarding most of them by extension. Here directories are pruned during
//! traversal, so a skipped directory costs one check instead of one check per
//! file beneath it.

use std::path::{Path, PathBuf};
use std::sync::Mutex;

use aho_corasick::AhoCorasick;
use ignore::{DirEntry, WalkBuilder, WalkState};
use memmap2::Mmap;

use crate::extract::{Extractor, FileFacts, Language};
use crate::matching::{scan_lines, scan_string_literals, LineMatch, PatternGroup, StringMatch};

/// Files above this size are skipped entirely.
///
/// Nothing legitimate in a source tree is this large; what is are bundled
/// vendor blobs, minified builds, and checked-in datasets. Parsing them costs
/// seconds each and has never produced a true finding.
const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;

/// Below this size a plain read beats mapping.
///
/// Establishing a mapping costs a syscall plus page-table work; for a typical
/// 3 KB source file that overhead exceeds just copying the bytes. Mapping only
/// pays off on the large files where the copy would actually hurt.
const MMAP_THRESHOLD: u64 = 64 * 1024;

/// One file's extracted facts, tagged with where it came from.
pub struct ScannedFile {
    pub path: PathBuf,
    pub facts: FileFacts,
    /// Hits from the caller's line patterns.
    pub line_matches: Vec<LineMatch>,
    /// Hits from the caller's patterns inside string literals.
    pub string_matches: Vec<StringMatch>,
}

/// Coverage counters, reported so a scan can state what it did *not* look at
/// rather than presenting partial coverage as complete.
#[derive(Debug, Default, Clone, Copy)]
pub struct Counters {
    /// Files that matched a known source extension and were considered.
    pub considered: usize,
    /// Files actually parsed (survived the prefilter).
    pub parsed: usize,
    /// Files skipped for exceeding `MAX_FILE_BYTES`.
    pub too_large: usize,
    /// Files that could not be read or decoded as UTF-8.
    pub unreadable: usize,
}

impl Counters {
    fn merge(&mut self, other: &Counters) {
        self.considered += other.considered;
        self.parsed += other.parsed;
        self.too_large += other.too_large;
        self.unreadable += other.unreadable;
    }
}

/// Configuration for a scan.
#[derive(Default)]
pub struct ScanOptions {
    /// Directory names pruned during traversal (`node_modules`, `.venv`, ...).
    pub skip_dirs: Vec<String>,
    /// Literal substrings that make a file worth parsing. A file containing
    /// none of them cannot produce a finding, so it is never parsed.
    ///
    /// Note this gates *parsing* only. Line patterns still run against every
    /// considered file, because a file can match `accuracy_score` without
    /// mentioning any AI SDK the prefilter knows about.
    pub prefilter: Vec<String>,
    /// Regexes run against every source line. Supplied by the caller.
    pub line_patterns: Vec<String>,
    /// Regexes run against every string literal. Supplied by the caller.
    pub string_patterns: Vec<String>,
    /// Worker threads; 0 means one per available core.
    pub threads: usize,
    /// Honour `.gitignore` while walking.
    pub respect_gitignore: bool,
}

/// Outcome of a scan.
pub struct ScanOutcome {
    pub files: Vec<ScannedFile>,
    pub counters: Counters,
}

/// Read a file's contents, choosing the cheaper of mapping and reading.
///
/// Returns `None` for non-UTF-8 content: tree-sitter needs `&str`, and a source
/// file that is not valid UTF-8 is either binary or in an encoding this scanner
/// has no business guessing at.
fn read_source(path: &Path, size: u64) -> Option<String> {
    if size >= MMAP_THRESHOLD {
        let file = std::fs::File::open(path).ok()?;
        // SAFETY: the mapping is read-only and confined to this call. Another
        // process truncating the file mid-scan could fault, which is why the
        // bytes are copied into an owned String here rather than being handed
        // out with the mapping's lifetime attached.
        let mmap = unsafe { Mmap::map(&file) }.ok()?;
        std::str::from_utf8(&mmap).ok().map(str::to_owned)
    } else {
        std::fs::read_to_string(path).ok()
    }
}

/// Per-worker accumulator that flushes into the shared result on drop.
///
/// Taking the shared lock once per *thread* instead of once per *file* is the
/// difference between the workers running in parallel and queueing behind a
/// single mutex. `ignore` gives no end-of-thread callback, so the flush hangs
/// off `Drop`: the boxed visitor closure owns this struct and is dropped when
/// its worker finishes.
struct ThreadSink<'a> {
    local: Vec<ScannedFile>,
    counts: Counters,
    shared_files: &'a Mutex<Vec<ScannedFile>>,
    shared_counts: &'a Mutex<Counters>,
}

impl Drop for ThreadSink<'_> {
    fn drop(&mut self) {
        if !self.local.is_empty() {
            self.shared_files
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .append(&mut self.local);
        }
        self.shared_counts
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .merge(&self.counts);
    }
}

/// Walk `root` and extract facts from every source file, in parallel.
///
/// Returns an error if the caller's patterns fail to compile, naming the
/// offending pattern.
pub fn scan_tree(root: &Path, options: &ScanOptions) -> Result<ScanOutcome, String> {
    // Compiled once and shared across workers; `Regex` and `RegexSet` are both
    // `Sync`, and compilation is far more expensive than matching.
    let line_patterns = PatternGroup::new(&options.line_patterns)?;
    let string_patterns = PatternGroup::new(&options.string_patterns)?;
    let line_patterns = &line_patterns;
    let string_patterns = &string_patterns;

    let prefilter = if options.prefilter.is_empty() {
        None
    } else {
        // ASCII-case-insensitive so `OpenAI` and `openai` both survive the
        // prefilter; exact casing is decided later by the real matcher.
        AhoCorasick::builder()
            .ascii_case_insensitive(true)
            .build(&options.prefilter)
            .ok()
    };

    let shared_files: Mutex<Vec<ScannedFile>> = Mutex::new(Vec::new());
    let shared_counts: Mutex<Counters> = Mutex::new(Counters::default());
    let skip_dirs = &options.skip_dirs;
    let prefilter = &prefilter;

    let threads = if options.threads == 0 {
        std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(4)
    } else {
        options.threads
    };

    let mut builder = WalkBuilder::new(root);
    builder
        .threads(threads)
        .hidden(false)
        .follow_links(false)
        .git_ignore(options.respect_gitignore)
        .git_global(options.respect_gitignore)
        .git_exclude(options.respect_gitignore)
        .parents(options.respect_gitignore);

    // Prune skipped directories during traversal: the closure is consulted for
    // a directory before descending, so an excluded tree is never entered.
    let skip_for_filter = options.skip_dirs.clone();
    builder.filter_entry(move |entry: &DirEntry| {
        // Depth 0 is the scan root. The caller named it explicitly, so it is
        // scanned even when it is called `examples` or `fixtures` — otherwise
        // pointing the scanner at such a directory would silently return
        // nothing at all.
        if entry.depth() == 0 {
            return true;
        }
        if entry.file_type().map(|t| t.is_dir()) != Some(true) {
            return true;
        }
        match entry.file_name().to_str() {
            Some(name) => !skip_for_filter.iter().any(|skip| skip == name),
            None => true,
        }
    });

    builder.build_parallel().run(|| {
        // One parser set per worker thread, built once and reused. Loading the
        // tree-sitter grammars per file would dominate the runtime.
        let mut extractor = match Extractor::new() {
            Ok(e) => e,
            Err(_) => return Box::new(|_| WalkState::Quit),
        };
        let mut sink = ThreadSink {
            local: Vec::new(),
            counts: Counters::default(),
            shared_files: &shared_files,
            shared_counts: &shared_counts,
        };

        Box::new(move |entry| {
            let Ok(entry) = entry else {
                return WalkState::Continue;
            };
            if entry.file_type().map(|t| t.is_file()) != Some(true) {
                return WalkState::Continue;
            }

            let path = entry.path();

            // Defence in depth for paths reached via a symlink, which
            // `filter_entry` does not prune.
            //
            // Only components *below the scan root* are considered. Checking
            // the absolute path would make the scan depend on where the tree
            // happens to live: pointing the scanner directly at, say,
            // `tests/fixtures/sample_codebase` would skip every file in it
            // because two ancestors are named in `skip_dirs`. The caller asked
            // for that directory, so its own name is not a reason to refuse.
            let below_root = path.strip_prefix(root).unwrap_or(path);
            if below_root
                .parent()
                .map(|parent| {
                    parent
                        .components()
                        .any(|c| skip_dirs.iter().any(|s| c.as_os_str() == s.as_str()))
                })
                .unwrap_or(false)
            {
                return WalkState::Continue;
            }

            let Some(ext) = path.extension().and_then(|e| e.to_str()) else {
                return WalkState::Continue;
            };
            let Some(lang) = Language::from_extension(&ext.to_ascii_lowercase()) else {
                return WalkState::Continue;
            };

            let Ok(meta) = entry.metadata() else {
                return WalkState::Continue;
            };
            let size = meta.len();

            sink.counts.considered += 1;

            if size > MAX_FILE_BYTES {
                sink.counts.too_large += 1;
                return WalkState::Continue;
            }

            let Some(source) = read_source(path, size) else {
                sink.counts.unreadable += 1;
                return WalkState::Continue;
            };

            // Line patterns run against every considered file, before the
            // prefilter. A file can legitimately match `accuracy_score` while
            // mentioning no AI SDK the prefilter knows about, and skipping it
            // here would silently drop findings the Python code reports.
            let line_matches = scan_lines(&source, line_patterns);

            // Cheap literal rejection before the expensive parse. Most files in
            // a real repository mention none of the tracked identifiers.
            let worth_parsing = match prefilter {
                Some(ac) => ac.is_match(source.as_str()),
                None => true,
            };

            let (facts, string_matches) = if worth_parsing {
                sink.counts.parsed += 1;
                match extractor.extract(&source, lang) {
                    Some(facts) => {
                        let lines: Vec<&str> = source.lines().collect();
                        let literals: Vec<(String, usize)> = facts
                            .strings
                            .iter()
                            .map(|s| (s.value.clone(), s.line))
                            .collect();
                        let matches = scan_string_literals(&literals, &lines, string_patterns);
                        (facts, matches)
                    }
                    None => (FileFacts::default(), Vec::new()),
                }
            } else {
                (FileFacts::default(), Vec::new())
            };

            // Files with nothing to report are dropped here rather than
            // crossing the FFI boundary. On a large repository that is tens of
            // thousands of empty objects the caller would only discard.
            if !facts.imports.is_empty()
                || !facts.routes.is_empty()
                || !line_matches.is_empty()
                || !string_matches.is_empty()
            {
                sink.local.push(ScannedFile {
                    path: path.to_path_buf(),
                    facts,
                    line_matches,
                    string_matches,
                });
            }

            WalkState::Continue
        })
    });

    let counters = *shared_counts.lock().unwrap_or_else(|e| e.into_inner());
    let mut files = shared_files.into_inner().unwrap_or_else(|e| e.into_inner());

    // The parallel walk yields files in nondeterministic order. Sorting makes
    // the scanner's output reproducible run to run, which matters for a tool
    // whose output is filed as regulatory evidence.
    files.sort_by(|a, b| a.path.cmp(&b.path));

    Ok(ScanOutcome { files, counters })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn fixture() -> TempDir {
        let dir = TempDir::new().unwrap();
        let root = dir.path();
        fs::write(root.join("app.py"), "import anthropic\n").unwrap();
        fs::write(root.join("client.ts"), "import x from 'openai';\n").unwrap();
        fs::write(root.join("notes.md"), "import anthropic\n").unwrap();
        fs::create_dir_all(root.join("node_modules/pkg")).unwrap();
        fs::write(
            root.join("node_modules/pkg/index.js"),
            "require('anthropic');\n",
        )
        .unwrap();
        dir
    }

    fn names(outcome: &ScanOutcome) -> Vec<String> {
        outcome
            .files
            .iter()
            .map(|f| f.path.file_name().unwrap().to_string_lossy().into_owned())
            .collect()
    }

    #[test]
    fn skips_excluded_directories_and_unknown_extensions() {
        let dir = fixture();
        let options = ScanOptions {
            skip_dirs: vec!["node_modules".to_string()],
            ..Default::default()
        };
        let outcome = scan_tree(dir.path(), &options).unwrap();

        assert_eq!(names(&outcome), ["app.py", "client.ts"]);
        assert_eq!(outcome.counters.considered, 2);
    }

    #[test]
    fn prefilter_skips_files_that_cannot_match() {
        let dir = fixture();
        let options = ScanOptions {
            skip_dirs: vec!["node_modules".to_string()],
            prefilter: vec!["anthropic".to_string()],
            ..Default::default()
        };
        let outcome = scan_tree(dir.path(), &options).unwrap();

        // Both files are considered; only app.py contains the literal.
        assert_eq!(outcome.counters.considered, 2);
        assert_eq!(outcome.counters.parsed, 1);
        assert_eq!(names(&outcome), ["app.py"]);
    }

    #[test]
    fn a_root_named_like_a_skipped_directory_is_still_scanned() {
        // The caller pointing at `.../fixtures/sample_codebase` is asking for
        // that tree. Neither the root's own name nor its ancestors' names may
        // prune it — only directories *below* it.
        let dir = TempDir::new().unwrap();
        let root = dir.path().join("fixtures").join("sample_codebase");
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("app.py"), "import anthropic\n").unwrap();
        fs::create_dir_all(root.join("node_modules")).unwrap();
        fs::write(root.join("node_modules/dep.py"), "import openai\n").unwrap();

        let outcome = scan_tree(
            &root,
            &ScanOptions {
                skip_dirs: vec![
                    "fixtures".to_string(),
                    "sample_codebase".to_string(),
                    "node_modules".to_string(),
                ],
                ..Default::default()
            },
        )
        .unwrap();

        assert_eq!(names(&outcome), ["app.py"]);
        assert_eq!(outcome.counters.considered, 1);
    }

    #[test]
    fn output_order_is_deterministic_across_thread_counts() {
        let dir = fixture();
        let single = scan_tree(
            dir.path(),
            &ScanOptions {
                skip_dirs: vec!["node_modules".to_string()],
                threads: 1,
                ..Default::default()
            },
        )
        .unwrap();
        let many = scan_tree(
            dir.path(),
            &ScanOptions {
                skip_dirs: vec!["node_modules".to_string()],
                threads: 8,
                ..Default::default()
            },
        )
        .unwrap();
        assert_eq!(names(&single), names(&many));
    }

    #[test]
    fn every_worker_result_survives_the_flush() {
        // Guards the Drop-based merge: with many files spread over many
        // threads, a lost sink would show up as a short result list.
        let dir = TempDir::new().unwrap();
        for i in 0..500 {
            fs::write(dir.path().join(format!("mod_{i}.py")), "import anthropic\n").unwrap();
        }
        let outcome = scan_tree(
            dir.path(),
            &ScanOptions {
                threads: 8,
                ..Default::default()
            },
        )
        .unwrap();
        assert_eq!(outcome.files.len(), 500);
        assert_eq!(outcome.counters.considered, 500);
        assert_eq!(outcome.counters.parsed, 500);
    }
}
