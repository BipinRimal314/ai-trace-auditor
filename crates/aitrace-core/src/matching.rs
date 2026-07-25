//! Regex matching over source lines and string literals.
//!
//! The pattern *text* is supplied by Python on every call and never compiled
//! into this crate — see the module docs in `lib.rs` for why. What lives here
//! is only the execution strategy.
//!
//! The strategy matters: the Python implementation ran every pattern against
//! every line independently, which on one mid-sized repository worked out to
//! 13.5 million individual regex searches. A `RegexSet` answers "which of these
//! patterns match this line" in a single pass over the line, and an
//! Aho-Corasick prefilter over the patterns' literal anchors rejects the
//! overwhelming majority of lines before any regex engine runs at all.

use regex::{Regex, RegexSet};

/// Python's `str.strip()[:120]`, applied to a source line for display context.
///
/// Truncation counts characters, not bytes: slicing a UTF-8 string at byte 120
/// can land inside a multi-byte character, and the Python code this mirrors
/// counts characters.
pub fn context_snippet(line: &str) -> String {
    line.trim().chars().take(120).collect()
}

/// A group of patterns evaluated together against the same input.
#[derive(Debug)]
pub struct PatternGroup {
    set: RegexSet,
    /// Individual compiled patterns, needed when the caller wants the matched
    /// text rather than just "something matched".
    individual: Vec<Regex>,
}

impl PatternGroup {
    /// Compile `patterns`, reporting the offending pattern on failure.
    ///
    /// Errors name the pattern rather than just the regex-syntax problem, so a
    /// bad entry in the Python tables is traceable back to its source.
    pub fn new(patterns: &[String]) -> Result<Self, String> {
        let set = RegexSet::new(patterns)
            .map_err(|e| format!("failed to compile pattern set: {e}"))?;
        let individual = patterns
            .iter()
            .map(|p| Regex::new(p).map_err(|e| format!("failed to compile {p:?}: {e}")))
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self { set, individual })
    }

    pub fn is_empty(&self) -> bool {
        self.individual.is_empty()
    }

    /// Indices of every pattern matching `haystack`, in ascending order.
    pub fn matching_indices(&self, haystack: &str) -> Vec<usize> {
        if self.individual.is_empty() {
            return Vec::new();
        }
        self.set.matches(haystack).into_iter().collect()
    }

    /// The first pattern to match, with the text it matched.
    ///
    /// "First" means lowest pattern index, matching the Python loop that
    /// iterates the pattern list in order and breaks on the first hit.
    pub fn first_match<'h>(&self, haystack: &'h str) -> Option<(usize, &'h str)> {
        let idx = self.set.matches(haystack).into_iter().next()?;
        let m = self.individual[idx].find(haystack)?;
        Some((idx, m.as_str()))
    }
}

/// One pattern hit on one source line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineMatch {
    /// Index into the pattern list the caller supplied.
    pub pattern_index: usize,
    /// 1-indexed line number, matching Python's `enumerate(lines, 1)`.
    pub line: usize,
    /// The line, stripped and truncated for display.
    pub context: String,
}

/// One pattern hit inside a string literal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StringMatch {
    pub pattern_index: usize,
    /// The substring the pattern actually matched (e.g. `claude-opus-4`).
    pub matched: String,
    pub line: usize,
    /// The source line the literal appeared on, stripped and truncated.
    pub context: String,
}

/// Run `patterns` against every line of `source`.
///
/// Returns every (pattern, line) pair that matches. Callers reproduce their own
/// aggregation on top — first-match-wins, unique-names-only, and so on — so the
/// semantics of the Python code being replaced stay in Python.
pub fn scan_lines(source: &str, patterns: &PatternGroup) -> Vec<LineMatch> {
    if patterns.is_empty() {
        return Vec::new();
    }

    let mut out = Vec::new();
    for (number, line) in source.lines().enumerate() {
        // `matches` short-circuits internally on a literal prefilter, so lines
        // that cannot match cost little more than a memchr scan.
        for pattern_index in patterns.matching_indices(line) {
            out.push(LineMatch {
                pattern_index,
                line: number + 1,
                context: context_snippet(line),
            });
        }
    }
    out
}

/// Run `patterns` against each string literal, keeping the first hit per literal.
///
/// One match per literal mirrors the Python loop's `break`: a literal that
/// looks like two different model identifiers is reported once, as the first.
pub fn scan_string_literals(
    literals: &[(String, usize)],
    lines: &[&str],
    patterns: &PatternGroup,
) -> Vec<StringMatch> {
    if patterns.is_empty() {
        return Vec::new();
    }

    let mut out = Vec::new();
    for (value, line) in literals {
        if let Some((pattern_index, matched)) = patterns.first_match(value) {
            out.push(StringMatch {
                pattern_index,
                matched: matched.to_string(),
                line: *line,
                // Python indexes `lines[lineno - 1]`; a literal spanning lines
                // reports the line it starts on, which may be past the end for
                // a trailing construct, hence the bounds check.
                context: lines
                    .get(line.saturating_sub(1))
                    .map(|l| context_snippet(l))
                    .unwrap_or_default(),
            });
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn group(patterns: &[&str]) -> PatternGroup {
        PatternGroup::new(&patterns.iter().map(|s| s.to_string()).collect::<Vec<_>>()).unwrap()
    }

    #[test]
    fn first_match_follows_pattern_order() {
        // Both patterns match; the lower index must win, as Python's loop does.
        let g = group(&[r"gpt-4[\w.-]*", r"gpt-[\w.-]*"]);
        let (idx, text) = g.first_match("gpt-4o-mini").unwrap();
        assert_eq!(idx, 0);
        assert_eq!(text, "gpt-4o-mini");
    }

    #[test]
    fn line_scan_reports_every_matching_pattern() {
        let g = group(&[r"accuracy_score", r"f1_score"]);
        let matches = scan_lines("from sklearn import accuracy_score, f1_score\n", &g);
        assert_eq!(matches.len(), 2);
        assert_eq!(matches[0].line, 1);
        assert_eq!(
            matches.iter().map(|m| m.pattern_index).collect::<Vec<_>>(),
            [0, 1]
        );
    }

    #[test]
    fn line_numbers_are_one_indexed() {
        let g = group(&[r"load_dataset\s*\("]);
        let matches = scan_lines("import x\n\nload_dataset(\"c4\")\n", &g);
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].line, 3);
    }

    #[test]
    fn context_is_stripped_and_char_truncated() {
        // 200 non-ASCII characters: truncating at 120 *bytes* would both cut
        // the wrong amount and risk splitting a character.
        let line = format!("   {}   ", "é".repeat(200));
        let snippet = context_snippet(&line);
        assert_eq!(snippet.chars().count(), 120);
        assert!(snippet.starts_with('é'));
    }

    #[test]
    fn string_literal_scan_uses_the_declaring_line_for_context() {
        let g = group(&[r"claude-(?:\d|opus|sonnet)[\w.-]*"]);
        let source_lines = vec!["x = 1", "MODEL = \"claude-opus-4\"", "y = 2"];
        let literals = vec![("claude-opus-4".to_string(), 2)];
        let matches = scan_string_literals(&literals, &source_lines, &g);
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].matched, "claude-opus-4");
        assert_eq!(matches[0].context, "MODEL = \"claude-opus-4\"");
    }

    #[test]
    fn empty_group_matches_nothing() {
        let g = PatternGroup::new(&[]).unwrap();
        assert!(g.is_empty());
        assert!(scan_lines("anything at all", &g).is_empty());
    }

    #[test]
    fn invalid_pattern_names_itself() {
        let err = PatternGroup::new(&["valid".to_string(), "((unclosed".to_string()]).unwrap_err();
        assert!(err.contains("unclosed"), "error should name the pattern: {err}");
    }
}
