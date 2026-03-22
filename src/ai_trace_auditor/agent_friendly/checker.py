"""Agent-friendly documentation checker.

Evaluates whether Markdown compliance documentation can be effectively
consumed by AI coding agents. Checks are derived from the Agent-Friendly
Documentation Spec (agentdocsspec.com) adapted for compliance documents.

Each check produces a pass/warn/fail result with a rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CheckResult:
    """Result of a single agent-friendly check."""

    check_id: str
    title: str
    status: str  # "pass", "warn", "fail"
    detail: str
    value: str = ""  # numeric or descriptive value for display


@dataclass(frozen=True)
class AgentFriendlyReport:
    """Aggregated results of all agent-friendly checks."""

    checks: tuple[CheckResult, ...]
    total_chars: int
    total_sections: int

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def score_pct(self) -> float:
        if not self.checks:
            return 0.0
        weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
        total = sum(weights.get(c.status, 0) for c in self.checks)
        return (total / len(self.checks)) * 100


def check_agent_friendly(markdown: str) -> AgentFriendlyReport:
    """Run all agent-friendly checks against a Markdown document.

    Args:
        markdown: The rendered Markdown content to evaluate.

    Returns:
        An AgentFriendlyReport with individual check results.
    """
    checks = (
        _check_document_size(markdown),
        _check_content_start(markdown),
        _check_section_headers(markdown),
        _check_code_fences(markdown),
        _check_table_structure(markdown),
        _check_link_format(markdown),
        _check_placeholder_density(markdown),
        _check_information_density(markdown),
        _check_line_length(markdown),
        _check_llms_txt_extractable(markdown),
    )

    sections = len(re.findall(r"^#{1,3}\s", markdown, re.MULTILINE))

    return AgentFriendlyReport(
        checks=checks,
        total_chars=len(markdown),
        total_sections=sections,
    )


def _check_document_size(md: str) -> CheckResult:
    """AF-01: Document size must be under agent fetch limits.

    Claude Code truncates at ~100K chars, MCP Fetch at ~5K chars.
    Compliance docs should stay under 50K for reliable agent consumption.
    """
    size = len(md)
    if size <= 50_000:
        return CheckResult(
            "AF-01", "Document size",
            "pass", f"Document is {size:,} chars (under 50K agent-friendly limit)",
            f"{size:,} chars",
        )
    if size <= 100_000:
        return CheckResult(
            "AF-01", "Document size",
            "warn", f"Document is {size:,} chars; may be truncated by some agent pipelines (50K recommended)",
            f"{size:,} chars",
        )
    return CheckResult(
        "AF-01", "Document size",
        "fail", f"Document is {size:,} chars; will be truncated by most agent fetch pipelines (100K limit)",
        f"{size:,} chars",
    )


def _check_content_start(md: str) -> CheckResult:
    """AF-02: Content should start early in the document.

    Agent pipelines that convert HTML to Markdown often truncate from
    the top. Even for pure Markdown docs, front-loading key information
    helps agents that hit token limits mid-document.
    """
    lines = md.split("\n")
    first_content_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("---") and not stripped.startswith("<!--"):
            first_content_line = i
            break

    if first_content_line <= 5:
        return CheckResult(
            "AF-02", "Content start position",
            "pass", f"Content starts at line {first_content_line + 1}",
            f"line {first_content_line + 1}",
        )
    if first_content_line <= 20:
        return CheckResult(
            "AF-02", "Content start position",
            "warn", f"Content starts at line {first_content_line + 1}; consider moving metadata to the end",
            f"line {first_content_line + 1}",
        )
    return CheckResult(
        "AF-02", "Content start position",
        "fail", f"Content starts at line {first_content_line + 1}; agents may miss the beginning",
        f"line {first_content_line + 1}",
    )


def _check_section_headers(md: str) -> CheckResult:
    """AF-03: Well-structured headers help agents navigate.

    Compliance docs should use H2 for major sections and H3 for
    subsections. Agents use headers to locate relevant content.
    """
    h1_count = len(re.findall(r"^# [^#]", md, re.MULTILINE))
    h2_count = len(re.findall(r"^## [^#]", md, re.MULTILINE))
    h3_count = len(re.findall(r"^### [^#]", md, re.MULTILINE))

    total = h1_count + h2_count + h3_count
    if total == 0:
        return CheckResult(
            "AF-03", "Section headers",
            "fail", "No section headers found; agents cannot navigate the document",
            "0 headers",
        )

    if h2_count >= 5 and h1_count <= 2:
        return CheckResult(
            "AF-03", "Section headers",
            "pass", f"{h1_count} H1, {h2_count} H2, {h3_count} H3; well-structured for agent navigation",
            f"{total} headers",
        )

    return CheckResult(
        "AF-03", "Section headers",
        "warn", f"{h1_count} H1, {h2_count} H2, {h3_count} H3; consider more H2 section breaks",
        f"{total} headers",
    )


def _check_code_fences(md: str) -> CheckResult:
    """AF-04: Code fences must be properly closed.

    Unclosed code fences cause agents to misparse everything after
    the opening fence as code, losing the rest of the document.
    """
    opens = len(re.findall(r"^```", md, re.MULTILINE))

    if opens % 2 != 0:
        return CheckResult(
            "AF-04", "Code fence validity",
            "fail", f"{opens} code fence markers found (odd number = unclosed fence)",
            f"{opens} markers",
        )

    if opens == 0:
        return CheckResult(
            "AF-04", "Code fence validity",
            "pass", "No code fences (document is prose-only)",
            "0 fences",
        )

    return CheckResult(
        "AF-04", "Code fence validity",
        "pass", f"{opens // 2} code blocks, all properly closed",
        f"{opens // 2} blocks",
    )


def _check_table_structure(md: str) -> CheckResult:
    """AF-05: Markdown tables must be well-formed.

    Agents parse tables for structured data. Broken table syntax
    (missing separator rows, inconsistent columns) causes misreads.
    """
    table_headers = re.findall(r"^\|.*\|$", md, re.MULTILINE)
    separator_rows = re.findall(r"^\|[\s\-:|]+\|$", md, re.MULTILINE)

    if not table_headers:
        return CheckResult(
            "AF-05", "Table structure",
            "pass", "No tables (not required for compliance docs)",
            "0 tables",
        )

    # Rough estimate: each table needs a header row + separator row
    estimated_tables = len(separator_rows)
    if estimated_tables == 0 and table_headers:
        return CheckResult(
            "AF-05", "Table structure",
            "fail", f"{len(table_headers)} table rows but no separator rows; tables will not parse correctly",
            f"{len(table_headers)} rows",
        )

    return CheckResult(
        "AF-05", "Table structure",
        "pass", f"{estimated_tables} well-formed table(s) detected",
        f"{estimated_tables} tables",
    )


def _check_link_format(md: str) -> CheckResult:
    """AF-06: Links should use standard Markdown format.

    Agents can follow [text](url) links but may miss bare URLs or
    non-standard link formats.
    """
    md_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", md)
    bare_urls = re.findall(r"(?<!\()(https?://\S+)(?!\))", md)

    if not md_links and not bare_urls:
        return CheckResult(
            "AF-06", "Link format",
            "pass", "No links (acceptable for generated compliance docs)",
            "0 links",
        )

    total = len(md_links) + len(bare_urls)
    if bare_urls and md_links:
        bare_pct = (len(bare_urls) / total) * 100
        if bare_pct > 50:
            return CheckResult(
                "AF-06", "Link format",
                "warn", f"{len(bare_urls)} bare URLs vs {len(md_links)} Markdown links; prefer [text](url) format",
                f"{bare_pct:.0f}% bare",
            )

    return CheckResult(
        "AF-06", "Link format",
        "pass", f"{len(md_links)} Markdown links, {len(bare_urls)} bare URLs",
        f"{len(md_links)} links",
    )


def _check_placeholder_density(md: str) -> CheckResult:
    """AF-07: Placeholder text ratio indicates completeness.

    Agents cannot act on [MANUAL INPUT REQUIRED] placeholders.
    High placeholder density means the document is a skeleton,
    not a usable compliance artifact.
    """
    placeholder_pattern = r"\[MANUAL INPUT REQUIRED\]"
    placeholders = len(re.findall(placeholder_pattern, md))

    lines = [line for line in md.split("\n") if line.strip()]
    total_lines = len(lines)

    if total_lines == 0:
        return CheckResult(
            "AF-07", "Placeholder density",
            "fail", "Document is empty",
            "empty",
        )

    placeholder_lines = sum(
        1 for line in lines if re.search(placeholder_pattern, line)
    )
    density = (placeholder_lines / total_lines) * 100

    if density <= 10:
        return CheckResult(
            "AF-07", "Placeholder density",
            "pass", f"{placeholders} placeholders ({density:.0f}% of content lines)",
            f"{density:.0f}%",
        )
    if density <= 30:
        return CheckResult(
            "AF-07", "Placeholder density",
            "warn", f"{placeholders} placeholders ({density:.0f}%); document needs manual completion",
            f"{density:.0f}%",
        )
    return CheckResult(
        "AF-07", "Placeholder density",
        "fail", f"{placeholders} placeholders ({density:.0f}%); document is mostly skeleton",
        f"{density:.0f}%",
    )


def _check_information_density(md: str) -> CheckResult:
    """AF-08: Content should be dense, not padded.

    Agents consume tokens for every line. Compliance docs should
    minimize boilerplate and maximize substantive content per token.
    """
    lines = md.split("\n")
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return CheckResult(
            "AF-08", "Information density",
            "fail", "Document is empty",
            "0%",
        )

    # Count lines that carry actual information vs structural/empty
    info_lines = [
        line for line in non_empty
        if not re.match(r"^(#{1,6}\s|[\-*]\s*$|\|[\s\-:|]+\||---+|```|>)", line.strip())
    ]

    density = (len(info_lines) / len(non_empty)) * 100

    if density >= 50:
        return CheckResult(
            "AF-08", "Information density",
            "pass", f"{density:.0f}% of lines carry substantive content",
            f"{density:.0f}%",
        )
    if density >= 30:
        return CheckResult(
            "AF-08", "Information density",
            "warn", f"{density:.0f}% information density; consider reducing structural boilerplate",
            f"{density:.0f}%",
        )
    return CheckResult(
        "AF-08", "Information density",
        "fail", f"{density:.0f}% information density; document is mostly structure with little content",
        f"{density:.0f}%",
    )


def _check_line_length(md: str) -> CheckResult:
    """AF-09: Lines should not be excessively long.

    Some agent pipelines wrap or truncate lines. Lines over 500 chars
    may cause parsing issues in Markdown-to-structured-data conversion.
    """
    lines = md.split("\n")
    long_lines = [i + 1 for i, line in enumerate(lines) if len(line) > 500]

    if not long_lines:
        return CheckResult(
            "AF-09", "Line length",
            "pass", "No lines exceed 500 chars",
            "all ok",
        )

    if len(long_lines) <= 3:
        return CheckResult(
            "AF-09", "Line length",
            "warn", f"{len(long_lines)} line(s) exceed 500 chars (lines {', '.join(str(n) for n in long_lines[:3])})",
            f"{len(long_lines)} long",
        )

    return CheckResult(
        "AF-09", "Line length",
        "fail", f"{len(long_lines)} lines exceed 500 chars; may cause agent parsing issues",
        f"{len(long_lines)} long",
    )


def _check_llms_txt_extractable(md: str) -> CheckResult:
    """AF-10: Document should have extractable summary for llms.txt.

    A well-structured compliance doc has a clear title (H1) and
    summary paragraph that could be extracted into an llms.txt entry.
    """
    h1_match = re.search(r"^# (.+)$", md, re.MULTILINE)

    if not h1_match:
        return CheckResult(
            "AF-10", "llms.txt extractable",
            "fail", "No H1 title found; cannot extract summary for llms.txt",
            "no title",
        )

    # Check for a summary-like line after the title
    title = h1_match.group(1)
    title_end = h1_match.end()
    after_title = md[title_end:title_end + 500].strip()

    # Look for a blockquote summary or first paragraph
    has_summary = bool(
        re.search(r"^>", after_title, re.MULTILINE)
        or (after_title and not after_title.startswith("#"))
    )

    if has_summary:
        return CheckResult(
            "AF-10", "llms.txt extractable",
            "pass", f"Title '{title[:50]}...' with extractable summary found",
            "extractable",
        )

    return CheckResult(
        "AF-10", "llms.txt extractable",
        "warn", f"Title '{title[:50]}' found but no summary paragraph follows",
        "title only",
    )
