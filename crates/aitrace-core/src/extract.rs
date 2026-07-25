//! Language-agnostic fact extraction from source files.
//!
//! This module deliberately knows nothing about AI SDKs, vector databases, or
//! the EU AI Act. It answers three mechanical questions about a source file:
//!
//!   * which modules does it import,
//!   * which string literals does it contain,
//!   * which HTTP routes does it register,
//!
//! and hands the answers back. Deciding that `anthropic` is an AI SDK, or that
//! `claude-opus-4` is a model identifier, stays in Python where the compliance
//! pattern tables live and change often. Keeping that boundary means the
//! regulatory data has exactly one home and Rust never has to be rebuilt to
//! track a new provider.

use tree_sitter::{Node, Parser, Tree};

/// A module a source file pulls in, with the line the import appears on.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Import {
    pub module: String,
    pub line: usize,
    /// The full dotted/qualified path when the grammar exposes one
    /// (`anthropic.Anthropic`), otherwise identical to `module`.
    pub qualified: String,
}

/// A string literal, used downstream to spot model identifiers and API URLs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StringLiteral {
    pub value: String,
    pub line: usize,
}

/// An HTTP route registration (`@app.post("/chat")`, `app.get("/chat", ...)`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Route {
    pub method: String,
    pub path: String,
    pub line: usize,
}

/// Everything extracted from one file.
#[derive(Debug, Clone, Default)]
pub struct FileFacts {
    pub imports: Vec<Import>,
    pub strings: Vec<StringLiteral>,
    pub routes: Vec<Route>,
    /// Set when the file parsed with errors. The facts are still returned
    /// (tree-sitter recovers and keeps going), but the caller may want to know
    /// that coverage for this file is partial rather than silently trusting it.
    pub had_parse_errors: bool,
}

/// Source languages the extractor understands.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    Python,
    JavaScript,
    TypeScript,
    Tsx,
}

impl Language {
    /// Map a file extension to a language, or `None` if it is not source we scan.
    pub fn from_extension(ext: &str) -> Option<Self> {
        match ext {
            "py" | "pyi" => Some(Language::Python),
            "js" | "mjs" | "cjs" | "jsx" => Some(Language::JavaScript),
            "ts" | "mts" | "cts" => Some(Language::TypeScript),
            "tsx" => Some(Language::Tsx),
            _ => None,
        }
    }

    fn grammar(self) -> tree_sitter::Language {
        match self {
            Language::Python => tree_sitter_python::LANGUAGE.into(),
            Language::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
            Language::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
            Language::Tsx => tree_sitter_typescript::LANGUAGE_TSX.into(),
        }
    }
}

/// A reusable per-thread parser set.
///
/// Constructing a `Parser` and loading a grammar costs far more than parsing a
/// small file, so each worker thread builds one of these once and reuses it for
/// every file it handles.
pub struct Extractor {
    python: Parser,
    javascript: Parser,
    typescript: Parser,
    tsx: Parser,
}

impl Extractor {
    pub fn new() -> Result<Self, tree_sitter::LanguageError> {
        let make = |lang: Language| -> Result<Parser, tree_sitter::LanguageError> {
            let mut parser = Parser::new();
            parser.set_language(&lang.grammar())?;
            Ok(parser)
        };
        Ok(Self {
            python: make(Language::Python)?,
            javascript: make(Language::JavaScript)?,
            typescript: make(Language::TypeScript)?,
            tsx: make(Language::Tsx)?,
        })
    }

    fn parser_for(&mut self, lang: Language) -> &mut Parser {
        match lang {
            Language::Python => &mut self.python,
            Language::JavaScript => &mut self.javascript,
            Language::TypeScript => &mut self.typescript,
            Language::Tsx => &mut self.tsx,
        }
    }

    /// Parse `source` and extract every fact the caller cares about.
    ///
    /// Returns `None` only if tree-sitter refuses to produce a tree at all,
    /// which in practice means the file was not valid UTF-8 or exceeded the
    /// parser's limits. A file with syntax errors still yields facts.
    pub fn extract(&mut self, source: &str, lang: Language) -> Option<FileFacts> {
        let tree: Tree = self.parser_for(lang).parse(source, None)?;
        let mut facts = FileFacts {
            had_parse_errors: tree.root_node().has_error(),
            ..Default::default()
        };

        let bytes = source.as_bytes();
        let mut cursor = tree.root_node().walk();
        let mut stack = vec![tree.root_node()];

        // Explicit stack rather than recursion: deeply nested minified JS has
        // been known to blow a recursive walker's stack, and a scanner that
        // crashes on one input file fails the whole audit.
        while let Some(node) = stack.pop() {
            match lang {
                Language::Python => visit_python(node, bytes, &mut facts),
                _ => visit_javascript(node, bytes, &mut facts),
            }

            // Children are pushed in reverse so that popping yields them
            // left-to-right, making the walk a true pre-order DFS. Without
            // this the stack reverses each sibling group and findings come out
            // in scrambled order.
            cursor.reset(node);
            if cursor.goto_first_child() {
                let mark = stack.len();
                loop {
                    stack.push(cursor.node());
                    if !cursor.goto_next_sibling() {
                        break;
                    }
                }
                stack[mark..].reverse();
            }
        }

        // Pre-order DFS already visits in source order, but a grammar is free
        // to nest a node's children in an order that does not match their byte
        // offsets. Sorting by line makes "findings appear in file order" a
        // property of the output rather than an assumption about the grammar.
        // The sort is stable, so multiple findings on one line keep DFS order.
        facts.imports.sort_by_key(|i| i.line);
        facts.strings.sort_by_key(|s| s.line);
        facts.routes.sort_by_key(|r| r.line);

        Some(facts)
    }
}

/// Line number (1-indexed) of a node's start, matching Python's `ast` numbering.
fn line_of(node: Node) -> usize {
    node.start_position().row + 1
}

fn text<'a>(node: Node, bytes: &'a [u8]) -> &'a str {
    std::str::from_utf8(&bytes[node.byte_range()]).unwrap_or("")
}

/// Strip surrounding quotes from a string-literal node's raw text.
///
/// Returns `None` for f-strings and template literals containing
/// interpolation, whose runtime value is not knowable statically.
fn literal_value(node: Node, bytes: &[u8]) -> Option<String> {
    let raw = text(node, bytes);

    // Python prefixes (r, b, f, u, rb, ...) precede the quote.
    let quote_start = raw.find(['"', '\''])?;
    let prefix = &raw[..quote_start].to_ascii_lowercase();
    if prefix.contains('f') {
        return None;
    }

    let body = &raw[quote_start..];
    for delim in ["\"\"\"", "'''", "\"", "'"] {
        if let Some(inner) = body.strip_prefix(delim).and_then(|s| s.strip_suffix(delim)) {
            return Some(inner.to_string());
        }
    }
    None
}

fn visit_python(node: Node, bytes: &[u8], facts: &mut FileFacts) {
    match node.kind() {
        // `import anthropic`, `import anthropic.types as t`
        "import_statement" => {
            let mut cursor = node.walk();
            for child in node.named_children(&mut cursor) {
                match child.kind() {
                    "dotted_name" => {
                        let qualified = text(child, bytes).to_string();
                        facts.imports.push(Import {
                            module: root_module(&qualified),
                            qualified,
                            line: line_of(node),
                        });
                    }
                    "aliased_import" => {
                        if let Some(name) = child.child_by_field_name("name") {
                            let qualified = text(name, bytes).to_string();
                            facts.imports.push(Import {
                                module: root_module(&qualified),
                                qualified,
                                line: line_of(node),
                            });
                        }
                    }
                    _ => {}
                }
            }
        }
        // `from anthropic import Anthropic`
        //
        // One entry per statement, carrying the module being imported *from*
        // rather than one entry per imported name. This mirrors CPython's
        // `ast.ImportFrom`, which exposes the base as a single `module` field —
        // the scanner asks "which package does this file depend on", and
        // `from langchain.chains import A, B, C` is one answer, not three.
        "import_from_statement" => {
            let Some(module_node) = node.child_by_field_name("module_name") else {
                return;
            };
            let base = text(module_node, bytes).to_string();
            facts.imports.push(Import {
                module: root_module(&base),
                qualified: base,
                line: line_of(node),
            });
        }
        "string" => {
            if let Some(value) = literal_value(node, bytes) {
                facts.strings.push(StringLiteral {
                    value,
                    line: line_of(node),
                });
            }
        }
        // FastAPI/Flask decorators: `@app.post("/chat")`
        "decorator" => {
            if let Some(route) = python_route(node, bytes) {
                facts.routes.push(route);
            }
        }
        _ => {}
    }
}

/// Extract `@app.post("/chat")`-style route registrations.
fn python_route(node: Node, bytes: &[u8]) -> Option<Route> {
    let mut cursor = node.walk();
    let call = node
        .named_children(&mut cursor)
        .find(|c| c.kind() == "call")?;

    let function = call.child_by_field_name("function")?;
    if function.kind() != "attribute" {
        return None;
    }
    let method = text(function.child_by_field_name("attribute")?, bytes).to_ascii_lowercase();
    if !matches!(
        method.as_str(),
        "get" | "post" | "put" | "delete" | "patch" | "route" | "websocket"
    ) {
        return None;
    }

    let args = call.child_by_field_name("arguments")?;
    let mut arg_cursor = args.walk();
    let path = args
        .named_children(&mut arg_cursor)
        .find(|c| c.kind() == "string")
        .and_then(|c| literal_value(c, bytes))?;

    Some(Route {
        method,
        path,
        line: line_of(node),
    })
}

fn visit_javascript(node: Node, bytes: &[u8], facts: &mut FileFacts) {
    match node.kind() {
        // `import { Anthropic } from "@anthropic-ai/sdk"` and bare `import "x"`
        "import_statement" => {
            if let Some(source) = node.child_by_field_name("source") {
                if let Some(module) = literal_value(source, bytes) {
                    facts.imports.push(Import {
                        module: package_root(&module),
                        qualified: module,
                        line: line_of(node),
                    });
                }
            }
        }
        // `export { x } from "y"` pulls in a module just as an import does.
        "export_statement" => {
            if let Some(source) = node.child_by_field_name("source") {
                if let Some(module) = literal_value(source, bytes) {
                    facts.imports.push(Import {
                        module: package_root(&module),
                        qualified: module,
                        line: line_of(node),
                    });
                }
            }
        }
        // `require("x")` and dynamic `import("x")`
        "call_expression" => {
            if let Some(import) = js_require(node, bytes) {
                facts.imports.push(import);
            }
            if let Some(route) = js_route(node, bytes) {
                facts.routes.push(route);
            }
        }
        "string" => {
            if let Some(value) = literal_value(node, bytes) {
                facts.strings.push(StringLiteral {
                    value,
                    line: line_of(node),
                });
            }
        }
        // Template literals with no substitutions are ordinary strings; ones
        // with `${}` have no static value and are skipped.
        "template_string" => {
            let mut cursor = node.walk();
            let has_substitution = node
                .named_children(&mut cursor)
                .any(|c| c.kind() == "template_substitution");
            if !has_substitution {
                let raw = text(node, bytes);
                if let Some(inner) = raw.strip_prefix('`').and_then(|s| s.strip_suffix('`')) {
                    facts.strings.push(StringLiteral {
                        value: inner.to_string(),
                        line: line_of(node),
                    });
                }
            }
        }
        _ => {}
    }
}

fn js_require(node: Node, bytes: &[u8]) -> Option<Import> {
    let function = node.child_by_field_name("function")?;
    let name = text(function, bytes);
    if name != "require" && function.kind() != "import" {
        return None;
    }

    let args = node.child_by_field_name("arguments")?;
    let mut cursor = args.walk();
    let module = args
        .named_children(&mut cursor)
        .find(|c| c.kind() == "string")
        .and_then(|c| literal_value(c, bytes))?;

    Some(Import {
        module: package_root(&module),
        qualified: module,
        line: line_of(node),
    })
}

/// Extract `app.get("/chat", handler)` Express-style routes.
fn js_route(node: Node, bytes: &[u8]) -> Option<Route> {
    let function = node.child_by_field_name("function")?;
    if function.kind() != "member_expression" {
        return None;
    }

    let object = text(function.child_by_field_name("object")?, bytes);
    if !matches!(object, "app" | "router" | "server") {
        return None;
    }

    let method = text(function.child_by_field_name("property")?, bytes).to_ascii_lowercase();
    if !matches!(
        method.as_str(),
        "get" | "post" | "put" | "delete" | "patch" | "all" | "use"
    ) {
        return None;
    }

    let args = node.child_by_field_name("arguments")?;
    let mut cursor = args.walk();
    let path = args
        .named_children(&mut cursor)
        .find(|c| c.kind() == "string")
        .and_then(|c| literal_value(c, bytes))?;

    Some(Route {
        method,
        path,
        line: line_of(node),
    })
}

/// `anthropic.types.beta` -> `anthropic`
///
/// Relative imports (`.`, `..`, `.sibling`) are returned unchanged. Splitting
/// them on `.` would yield an empty string, which reads as "no module" and
/// would make every relative import in a package look like a parse failure.
fn root_module(dotted: &str) -> String {
    if dotted.starts_with('.') {
        return dotted.to_string();
    }
    dotted.split('.').next().unwrap_or(dotted).to_string()
}

/// Reduce a JS specifier to the package it refers to.
///
/// Scoped packages keep two segments (`@anthropic-ai/sdk`), unscoped keep one
/// (`openai/resources` -> `openai`), and relative paths are returned unchanged
/// so the caller can tell local modules from dependencies.
fn package_root(specifier: &str) -> String {
    if specifier.starts_with('.') || specifier.starts_with('/') {
        return specifier.to_string();
    }
    let mut parts = specifier.split('/');
    let first = parts.next().unwrap_or(specifier);
    if first.starts_with('@') {
        match parts.next() {
            Some(second) => format!("{first}/{second}"),
            None => first.to_string(),
        }
    } else {
        first.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts(source: &str, lang: Language) -> FileFacts {
        Extractor::new().unwrap().extract(source, lang).unwrap()
    }

    fn modules(f: &FileFacts) -> Vec<&str> {
        f.imports.iter().map(|i| i.module.as_str()).collect()
    }

    #[test]
    fn python_import_forms() {
        let f = facts(
            "import anthropic\n\
             import openai.types as t\n\
             from langchain.chains import LLMChain\n\
             from . import local\n",
            Language::Python,
        );
        assert_eq!(modules(&f), ["anthropic", "openai", "langchain", "."]);
        // The base module, not the imported name — see the extractor comment.
        assert_eq!(f.imports[2].qualified, "langchain.chains");
        assert_eq!(f.imports[2].line, 3);
        // `import openai.types as t` records the aliased target, not the alias.
        assert_eq!(f.imports[1].qualified, "openai.types");
    }

    #[test]
    fn js_import_forms() {
        let f = facts(
            "import Anthropic from '@anthropic-ai/sdk';\n\
             const OpenAI = require('openai');\n\
             import('cohere-ai/resources');\n\
             export { x } from '@pinecone-database/pinecone';\n",
            Language::JavaScript,
        );
        let mut got = modules(&f);
        got.sort_unstable();
        assert_eq!(
            got,
            [
                "@anthropic-ai/sdk",
                "@pinecone-database/pinecone",
                "cohere-ai",
                "openai"
            ]
        );
    }

    #[test]
    fn typescript_type_imports_are_found() {
        let f = facts(
            "import type { Message } from '@anthropic-ai/sdk';\n",
            Language::TypeScript,
        );
        assert_eq!(modules(&f), ["@anthropic-ai/sdk"]);
    }

    #[test]
    fn fstrings_and_templates_have_no_static_value() {
        let py = facts(
            "x = f\"claude-{version}\"\ny = \"claude-opus-4\"\n",
            Language::Python,
        );
        let values: Vec<_> = py.strings.iter().map(|s| s.value.as_str()).collect();
        assert_eq!(values, ["claude-opus-4"]);

        let js = facts(
            "const a = `gpt-${n}`; const b = `gpt-4o`;",
            Language::JavaScript,
        );
        let values: Vec<_> = js.strings.iter().map(|s| s.value.as_str()).collect();
        assert_eq!(values, ["gpt-4o"]);
    }

    #[test]
    fn routes_are_extracted() {
        let py = facts("@app.post(\"/chat\")\ndef chat(): ...\n", Language::Python);
        assert_eq!(py.routes.len(), 1);
        assert_eq!(py.routes[0].method, "post");
        assert_eq!(py.routes[0].path, "/chat");

        let js = facts("app.get('/api/chat', handler);", Language::JavaScript);
        assert_eq!(js.routes.len(), 1);
        assert_eq!(js.routes[0].path, "/api/chat");
    }

    #[test]
    fn syntax_errors_still_yield_facts() {
        // A regex scanner sees nothing useful here; tree-sitter recovers.
        let f = facts(
            "import anthropic\ndef broken(:\n    pass\nimport openai\n",
            Language::Python,
        );
        assert!(f.had_parse_errors);
        assert!(modules(&f).contains(&"anthropic"));
        assert!(modules(&f).contains(&"openai"));
    }

    #[test]
    fn commented_imports_are_not_reported() {
        // The regex scanner this replaces matched inside comments and strings.
        let f = facts(
            "# import anthropic\ns = \"require('openai')\"\n",
            Language::Python,
        );
        assert!(f.imports.is_empty());
    }

    #[test]
    fn package_roots() {
        assert_eq!(
            package_root("@anthropic-ai/sdk/resources"),
            "@anthropic-ai/sdk"
        );
        assert_eq!(package_root("openai/resources/chat"), "openai");
        assert_eq!(package_root("./local/module"), "./local/module");
    }
}
