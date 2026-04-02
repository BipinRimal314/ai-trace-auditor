"""Tests for compliance guide linter rules."""

from __future__ import annotations

from ai_trace_auditor.guide_linter.rules import (
    lint_article_13_50_conflation,
    lint_article_citations,
    lint_diagram_text_consistency,
    lint_guide,
    lint_missing_scope_check,
    lint_provider_deployer_conflation,
    lint_retention_periods,
    lint_self_promotion,
)


class TestArticle1350Conflation:
    def test_detects_user_disclosure_in_art13(self):
        lines = ["## Article 13", "Deployers must inform users that they are interacting with AI."]
        issues = lint_article_13_50_conflation(lines)
        assert len(issues) >= 1
        assert issues[0].rule_id == "CG-001"
        assert issues[0].severity == "error"

    def test_detects_tech_docs_in_art50(self):
        lines = ["## Article 50", "Include technical documentation per Annex IV."]
        issues = lint_article_13_50_conflation(lines)
        assert len(issues) >= 1

    def test_no_false_positive_correct_usage(self):
        lines = [
            "## Article 13",
            "Providers must supply deployers with technical documentation.",
        ]
        issues = lint_article_13_50_conflation(lines)
        assert issues == []


class TestRetentionPeriods:
    def test_detects_6_months_only(self):
        lines = ["Data retention: 6 months minimum for all logs."]
        issues = lint_retention_periods(lines)
        assert len(issues) >= 1
        assert "10 years" in issues[0].fix_hint

    def test_no_issue_when_both_mentioned(self):
        lines = [
            "Retention policy:",
            "- Providers: 10 years",
            "- Deployers: retention of at least 6 months",
        ]
        issues = lint_retention_periods(lines)
        assert issues == []

    def test_no_issue_without_retention(self):
        lines = ["This is about logging configuration."]
        issues = lint_retention_periods(lines)
        assert issues == []


class TestMissingScopeCheck:
    def test_detects_missing_scope(self):
        lines = [
            "# Compliance Guide",
            "## Article 12: Record Keeping",
            "You must log all AI operations.",
        ]
        issues = lint_missing_scope_check(lines)
        assert len(issues) >= 1
        assert issues[0].rule_id == "CG-003"

    def test_no_issue_with_scope_check(self):
        lines = [
            "# Compliance Guide",
            "## Does this apply to you?",
            "Check Annex III to determine if your system is high-risk.",
            "## Article 12: Record Keeping",
        ]
        issues = lint_missing_scope_check(lines)
        assert issues == []


class TestProviderDeployerConflation:
    def test_detects_processor_default(self):
        lines = ["AI providers are processors by default under GDPR."]
        issues = lint_provider_deployer_conflation(lines)
        assert len(issues) >= 1
        assert issues[0].severity == "error"

    def test_no_issue_with_proper_distinction(self):
        lines = [
            "## Provider Obligations (Article 16)",
            "Providers must ensure conformity.",
            "## Deployer Obligations (Article 26)",
            "Deployers must monitor the system.",
        ]
        issues = lint_provider_deployer_conflation(lines)
        assert issues == []


class TestSelfPromotion:
    def test_detects_pip_install(self):
        lines = ["```bash", "pip install ai-trace-auditor", "```"]
        issues = lint_self_promotion(lines)
        assert len(issues) >= 1
        assert issues[0].rule_id == "CG-005"

    def test_detects_aitrace_command(self):
        lines = ["Run `aitrace audit traces.json` to check compliance."]
        issues = lint_self_promotion(lines)
        assert len(issues) >= 1

    def test_no_issue_without_promo(self):
        lines = ["Use your observability platform to export traces."]
        issues = lint_self_promotion(lines)
        assert issues == []


class TestArticleCitations:
    def test_detects_art50_2_as_deployer(self):
        lines = ["Deployers must comply with Article 50(2) for content marking."]
        issues = lint_article_citations(lines)
        assert len(issues) >= 1

    def test_no_issue_for_provider_art50_2(self):
        lines = ["Providers must comply with Article 50(2) for watermarking."]
        issues = lint_article_citations(lines)
        assert issues == []


class TestFullLint:
    def test_clean_guide_passes(self):
        content = """# EU AI Act Compliance Guide

## Does this apply to you?

Check Annex III to determine if your system is high-risk.

## Article 12: Record-Keeping

Log timestamps and model versions.

## Data Retention

Providers: 10 years. Deployers: minimum 6 months.
"""
        issues = lint_guide(content)
        assert issues == []

    def test_bad_guide_catches_multiple(self):
        content = """# Compliance Guide

## Article 12

Log everything.

## Article 13

Inform users they are talking to AI.

## Data Retention

Keep logs for 6 months.

Run `aitrace audit` to verify.
"""
        issues = lint_guide(content)
        error_ids = {i.rule_id for i in issues}
        assert "CG-001" in error_ids  # Art 13/50 conflation
        assert "CG-002" in error_ids  # Retention
        assert "CG-003" in error_ids  # Missing scope
        assert "CG-005" in error_ids  # Self-promotion


class TestDiagramTextConsistency:
    def test_detects_processor_label_with_qualified_text(self):
        lines = [
            "```mermaid",
            "graph LR",
            "    classDef processor fill:#60a5fa",
            "    class OpenAI processor",
            "```",
            "",
            "AI providers may act as processors or controllers depending on the deployment.",
        ]
        issues = lint_diagram_text_consistency(lines)
        assert len(issues) >= 1
        assert issues[0].rule_id == "CG-007"
        assert "processor" in issues[0].message

    def test_no_issue_when_text_not_qualified(self):
        """If the text doesn't qualify roles, diagram labels are fine."""
        lines = [
            "```mermaid",
            "graph LR",
            "    classDef processor fill:#60a5fa",
            "    class OpenAI processor",
            "```",
            "",
            "OpenAI acts as a data processor under GDPR.",
        ]
        issues = lint_diagram_text_consistency(lines)
        assert issues == []

    def test_no_issue_with_neutral_labels(self):
        lines = [
            "```mermaid",
            "graph LR",
            "    classDef provider fill:#60a5fa",
            "    class OpenAI provider",
            "```",
            "",
            "AI providers may act as processors depending on the context.",
        ]
        issues = lint_diagram_text_consistency(lines)
        assert issues == []

    def test_detects_controller_label_with_qualified_text(self):
        lines = [
            "```mermaid",
            "graph LR",
            "    class VectorStore controller",
            "```",
            "",
            "The GDPR role depends on the specific deployment architecture.",
        ]
        issues = lint_diagram_text_consistency(lines)
        assert len(issues) >= 1
