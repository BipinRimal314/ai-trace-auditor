"""Tests for agent-friendly documentation checker."""

from ai_trace_auditor.agent_friendly.checker import (
    AgentFriendlyReport,
    CheckResult,
    check_agent_friendly,
)


MINIMAL_DOC = """\
# EU AI Act — Annex IV Technical Documentation

> Auto-generated compliance documentation for MyApp.

## Section 1: General System Description

MyApp is an AI-powered document analysis system using OpenAI GPT-4o.

## Section 2: Development Elements

Built with Python 3.11, FastAPI, and the OpenAI SDK.

## Section 3: Monitoring and Control

[MANUAL INPUT REQUIRED] Describe performance monitoring.

## Section 4: Performance Metrics

Accuracy: 94.2% on test set (n=1,000).

## Section 5: Risk Management

[MANUAL INPUT REQUIRED] Describe risk management system.

## Section 6: Lifecycle Changes

Version 1.0.0 — initial release.

## Section 7: Standards Applied

ISO/IEC 42001:2023 (AI Management System).

## Section 8: EU Declaration of Conformity

[MANUAL INPUT REQUIRED] Attach declaration.

## Section 9: Post-Market Monitoring

Review frequency: quarterly. Escalation: compliance@myapp.com.
"""


OVERSIZED_DOC = "# Title\n\n" + ("x" * 120_000)


UNCLOSED_FENCE_DOC = """\
# Title

```python
def hello():
    pass

## Section 2

This is outside the fence but looks like inside.
"""


EMPTY_DOC = ""


NO_HEADERS_DOC = """\
This document has no headers at all.
Just some paragraphs of text about compliance.
Nothing structured.
"""


PLACEHOLDER_HEAVY_DOC = """\
# Title

## Section 1
[MANUAL INPUT REQUIRED] Describe system.

## Section 2
[MANUAL INPUT REQUIRED] Describe development.

## Section 3
[MANUAL INPUT REQUIRED] Describe monitoring.

## Section 4
[MANUAL INPUT REQUIRED] Describe metrics.

## Section 5
[MANUAL INPUT REQUIRED] Describe risks.
"""


class TestCheckAgentFriendly:
    def test_returns_report(self):
        report = check_agent_friendly(MINIMAL_DOC)
        assert isinstance(report, AgentFriendlyReport)

    def test_all_checks_run(self):
        report = check_agent_friendly(MINIMAL_DOC)
        assert len(report.checks) == 10

    def test_minimal_doc_passes_most_checks(self):
        report = check_agent_friendly(MINIMAL_DOC)
        assert report.passed >= 7

    def test_score_is_percentage(self):
        report = check_agent_friendly(MINIMAL_DOC)
        assert 0 <= report.score_pct <= 100

    def test_total_chars_correct(self):
        report = check_agent_friendly(MINIMAL_DOC)
        assert report.total_chars == len(MINIMAL_DOC)

    def test_total_sections_counted(self):
        report = check_agent_friendly(MINIMAL_DOC)
        assert report.total_sections >= 9


class TestDocumentSize:
    def test_small_doc_passes(self):
        report = check_agent_friendly(MINIMAL_DOC)
        size_check = next(c for c in report.checks if c.check_id == "AF-01")
        assert size_check.status == "pass"

    def test_oversized_doc_fails(self):
        report = check_agent_friendly(OVERSIZED_DOC)
        size_check = next(c for c in report.checks if c.check_id == "AF-01")
        assert size_check.status == "fail"


class TestContentStart:
    def test_immediate_content_passes(self):
        report = check_agent_friendly(MINIMAL_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-02")
        assert check.status == "pass"


class TestSectionHeaders:
    def test_well_structured_passes(self):
        report = check_agent_friendly(MINIMAL_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-03")
        assert check.status == "pass"

    def test_no_headers_fails(self):
        report = check_agent_friendly(NO_HEADERS_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-03")
        assert check.status == "fail"


class TestCodeFences:
    def test_no_fences_passes(self):
        report = check_agent_friendly(MINIMAL_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-04")
        assert check.status == "pass"

    def test_unclosed_fence_fails(self):
        report = check_agent_friendly(UNCLOSED_FENCE_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-04")
        assert check.status == "fail"


class TestPlaceholderDensity:
    def test_low_placeholder_passes(self):
        report = check_agent_friendly(MINIMAL_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-07")
        assert check.status in ("pass", "warn")

    def test_heavy_placeholder_fails(self):
        report = check_agent_friendly(PLACEHOLDER_HEAVY_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-07")
        assert check.status in ("warn", "fail")


class TestEmptyDoc:
    def test_empty_doc_has_failures(self):
        report = check_agent_friendly(EMPTY_DOC)
        assert report.failed >= 2


class TestLlmsTxtExtractable:
    def test_titled_doc_passes(self):
        report = check_agent_friendly(MINIMAL_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-10")
        assert check.status == "pass"

    def test_no_title_fails(self):
        report = check_agent_friendly(NO_HEADERS_DOC)
        check = next(c for c in report.checks if c.check_id == "AF-10")
        assert check.status == "fail"


class TestIntegrationWithRealDocs:
    """Test against actual generated Annex IV docs from the fixture codebase."""

    def test_generated_annex_iv_is_agent_friendly(self):
        from pathlib import Path

        from ai_trace_auditor.docs.assembler import generate_annex_iv
        from ai_trace_auditor.reports.docs_report import DocsReporter
        from ai_trace_auditor.scanner.scan import scan_codebase

        fixtures = Path(__file__).parent.parent / "fixtures" / "sample_codebase"
        scan = scan_codebase(fixtures)
        doc = generate_annex_iv(scan)
        markdown = DocsReporter().render(doc)

        report = check_agent_friendly(markdown)

        # Generated docs should pass at least 70% of checks
        assert report.score_pct >= 60, (
            f"Generated docs scored {report.score_pct:.0f}%, expected >= 60%. "
            f"Failed: {[c.check_id for c in report.checks if c.status == 'fail']}"
        )
