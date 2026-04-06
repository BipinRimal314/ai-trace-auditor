"""Compliance guide linting rules.

Each rule checks a Markdown compliance guide for a specific recurring mistake
found across real-world PR reviews (vLLM, LiteLLM, n8n, CrewAI, Haystack).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LintIssue:
    """A single issue found in a compliance guide."""

    rule_id: str
    severity: str  # "error", "warning", "info"
    line: int
    message: str
    fix_hint: str


def lint_article_13_50_conflation(lines: list[str]) -> list[LintIssue]:
    """Rule CG-001: Article 13 vs Article 50 conflation.

    Article 13 = provider→deployer documentation (technical docs).
    Article 50 = deployer→user disclosure (tell users they're talking to AI),
    unless obvious from circumstances and context (Article 50(1) exemption).
    Mixing these is the #1 recurring error across all PR reviews.
    """
    issues: list[LintIssue] = []
    user_disclosure_keywords = ("inform users", "user disclosure", "notify users", "tell users")
    tech_doc_keywords = ("technical documentation", "annex iv", "model accuracy", "training data")

    # Track which article "section" we're in by looking for headers
    current_article: str | None = None

    for i, line in enumerate(lines, 1):
        lower = line.lower()

        # Detect article sections from headers or prominent mentions
        if "article 13" in lower and ("#" in line or lower.strip().startswith("article 13")):
            current_article = "13"
        elif "article 50" in lower and ("#" in line or lower.strip().startswith("article 50")):
            current_article = "50"
        elif line.startswith("#") and "article" not in lower:
            current_article = None

        # Same-line checks
        if "article 13" in lower and any(kw in lower for kw in user_disclosure_keywords):
            issues.append(LintIssue(
                rule_id="CG-001", severity="error", line=i,
                message="Article 13 is about provider→deployer documentation, not user disclosure. "
                        "User notification is Article 50.",
                fix_hint="Move user disclosure requirements to an Article 50 section.",
            ))
        elif current_article == "13" and any(kw in lower for kw in user_disclosure_keywords):
            issues.append(LintIssue(
                rule_id="CG-001", severity="error", line=i,
                message="User disclosure content found in Article 13 section. "
                        "Article 13 is provider→deployer docs. User notification is Article 50.",
                fix_hint="Move this content to an Article 50 section.",
            ))

        if "article 50" in lower and any(kw in lower for kw in tech_doc_keywords):
            issues.append(LintIssue(
                rule_id="CG-001", severity="error", line=i,
                message="Article 50 is about deployer→user transparency, not technical documentation. "
                        "Technical docs are Article 11/13.",
                fix_hint="Move technical documentation to Article 11 or 13 section.",
            ))
        elif current_article == "50" and any(kw in lower for kw in tech_doc_keywords):
            issues.append(LintIssue(
                rule_id="CG-001", severity="error", line=i,
                message="Technical documentation found in Article 50 section. "
                        "Article 50 is deployer→user transparency. Tech docs go in Article 11/13.",
                fix_hint="Move this content to Article 11 or 13 section.",
            ))

    return issues


def lint_retention_periods(lines: list[str]) -> list[LintIssue]:
    """Rule CG-002: Incorrect retention period.

    Providers must retain logs for 10 years (Article 18).
    Deployers must retain logs for at least 6 months (Article 26(6)).
    Saying just '6 months' without distinguishing is wrong.
    """
    issues: list[LintIssue] = []

    for i, line in enumerate(lines, 1):
        lower = line.lower()

        # Mentions retention/logs with 6 months, no 10 year mention nearby
        has_retention_context = any(kw in lower for kw in ("retention", "retain", "keep log", "keep data", "store log"))
        if has_retention_context and "6 month" in lower and "10 year" not in lower:
            # Check surrounding lines for 10 year mention
            context = " ".join(lines[max(0, i - 3):min(len(lines), i + 3)]).lower()
            if "10 year" not in context and "10-year" not in context:
                issues.append(LintIssue(
                    rule_id="CG-002",
                    severity="error",
                    line=i,
                    message="Retention period '6 months' applies to deployers only. "
                            "Providers must retain logs for 10 years (Article 18).",
                    fix_hint="Add: 'Providers: 10 years. Deployers: minimum 6 months.'",
                ))

    return issues


def lint_missing_scope_check(lines: list[str]) -> list[LintIssue]:
    """Rule CG-003: Missing high-risk scope determination.

    Articles 12-14 only apply to high-risk AI systems (Annex III).
    A guide that jumps straight to Article 12 without checking scope
    may cause incorrect self-classification.
    """
    issues: list[LintIssue] = []

    full_text = "\n".join(lines).lower()

    # Check if guide mentions Article 12 but has no scope/risk check
    mentions_art12 = "article 12" in full_text
    has_scope_check = any(
        kw in full_text
        for kw in ("annex iii", "high-risk", "high risk", "risk classification", "scope determination")
    )

    if mentions_art12 and not has_scope_check:
        issues.append(LintIssue(
            rule_id="CG-003",
            severity="error",
            line=1,
            message="Guide applies Article 12-14 obligations without scope determination. "
                    "These only apply to high-risk AI systems per Annex III.",
            fix_hint="Add a 'Does this apply to you?' section before Article-specific guidance. "
                     "Include Annex III high-risk classification check.",
        ))

    return issues


def lint_provider_deployer_conflation(lines: list[str]) -> list[LintIssue]:
    """Rule CG-004: Provider vs deployer obligations conflated.

    The EU AI Act assigns different obligations to providers (Article 16)
    and deployers (Article 26). Mixing them up creates legal confusion.
    """
    issues: list[LintIssue] = []

    for i, line in enumerate(lines, 1):
        lower = line.lower()

        # "These requirements apply to the deployed system, not to providers"
        if "not to" in lower and ("provider" in lower or "deployer" in lower):
            if "provider" in lower and "deployer" in lower:
                issues.append(LintIssue(
                    rule_id="CG-004",
                    severity="warning",
                    line=i,
                    message="Provider and deployer obligations are distinct under the EU AI Act. "
                            "Ensure you're not conflating which party owes which obligation.",
                    fix_hint="Use 'Provider obligations (Article 16)' and "
                             "'Deployer obligations (Article 26)' as separate sections.",
                ))

        # "AI providers are processors by default" — overgeneralization
        if "provider" in lower and "processor" in lower and "by default" in lower:
            issues.append(LintIssue(
                rule_id="CG-004",
                severity="error",
                line=i,
                message="'Providers are processors by default' overgeneralizes. "
                        "Controller/processor roles depend on specific deployment and data flows.",
                fix_hint="Qualify with: 'Classification depends on the deployment architecture "
                         "and contractual arrangements (Data Processing Agreement).'",
            ))

    return issues


def lint_self_promotion(lines: list[str]) -> list[LintIssue]:
    """Rule CG-005: Self-promotional content.

    Compliance guides submitted to third-party repos should not contain
    install/usage instructions for the author's own tools. PR reviewers
    flag this as spam.
    """
    issues: list[LintIssue] = []
    promo_patterns = [
        r"pip install ai-trace-auditor",
        r"aitrace\s+(audit|comply|docs|flow)",
        r"ai-trace-auditor",
        r"BipinRimal314",
    ]

    for i, line in enumerate(lines, 1):
        for pattern in promo_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(LintIssue(
                    rule_id="CG-005",
                    severity="error",
                    line=i,
                    message="Self-promotional content detected. Third-party docs should not "
                            "include install/usage instructions for the guide author's tools.",
                    fix_hint="Remove tool-specific references. Provide framework-native guidance instead.",
                ))
                break  # one per line

    return issues


def lint_article_citations(lines: list[str]) -> list[LintIssue]:
    """Rule CG-006: Incorrect article citations.

    Common citation errors found in PR reviews.
    """
    issues: list[LintIssue] = []

    for i, line in enumerate(lines, 1):
        lower = line.lower()

        # Article 26(6) cited for deployer retention — actually Article 26(5) or 26(6)
        # depending on the final text version. Flag if specific paragraph cited
        # alongside retention and it's clearly wrong.
        if "article 50(2)" in lower and "deployer" in lower:
            issues.append(LintIssue(
                rule_id="CG-006",
                severity="warning",
                line=i,
                message="Article 50(2) (machine-readable marking) is a provider obligation, "
                        "not a deployer obligation.",
                fix_hint="Article 50(2) applies to providers. Deployer obligations are in 50(3) and 50(4).",
            ))

    return issues


def lint_diagram_text_consistency(lines: list[str]) -> list[LintIssue]:
    """Rule CG-007: Mermaid diagram labels contradict body text.

    Found via n8n PR #27370: the GDPR text said roles are context-dependent,
    but the Mermaid diagram hardcoded all providers as 'processor'.
    Diagrams must not assign GDPR roles that the text qualifies or disclaims.
    """
    issues: list[LintIssue] = []

    # Extract Mermaid blocks and check for GDPR role labels
    in_mermaid = False
    mermaid_start = 0
    role_labels_in_diagram: list[tuple[int, str, str]] = []  # (line, node, role)

    gdpr_role_patterns = re.compile(
        r"class(?:Def)?\s+(processor|controller|joint_controller|sub_processor)",
        re.IGNORECASE,
    )
    class_assignment = re.compile(
        r"class\s+(\w+)\s+(processor|controller|joint_controller|sub_processor)",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, 1):
        if "```mermaid" in line.lower():
            in_mermaid = True
            mermaid_start = i
            continue
        if in_mermaid and line.strip().startswith("```"):
            in_mermaid = False
            continue
        if in_mermaid:
            match = class_assignment.search(line)
            if match:
                role_labels_in_diagram.append((i, match.group(1), match.group(2)))

    # Check if body text qualifies GDPR roles as context-dependent
    full_text = "\n".join(lines).lower()
    roles_qualified = any(
        phrase in full_text
        for phrase in (
            "context-dependent",
            "depends on",
            "may act as",
            "not automatic",
            "classification is not",
            "depending on the specific",
        )
    )

    if roles_qualified and role_labels_in_diagram:
        for line_num, node, role in role_labels_in_diagram:
            issues.append(LintIssue(
                rule_id="CG-007",
                severity="error",
                line=line_num,
                message=f"Diagram assigns '{role}' role to '{node}', but body text says "
                        "GDPR roles are context-dependent. The diagram contradicts the text.",
                fix_hint=f"Rename 'classDef {role}' to a neutral name like 'provider' or "
                         "'external_service' that doesn't imply a specific GDPR classification.",
            ))

    return issues


# All rules in execution order
ALL_RULES = [
    lint_article_13_50_conflation,
    lint_retention_periods,
    lint_missing_scope_check,
    lint_provider_deployer_conflation,
    lint_self_promotion,
    lint_article_citations,
    lint_diagram_text_consistency,
]


def lint_guide(content: str) -> list[LintIssue]:
    """Run all linting rules against a compliance guide."""
    lines = content.split("\n")
    issues: list[LintIssue] = []

    for rule_fn in ALL_RULES:
        issues.extend(rule_fn(lines))

    return sorted(issues, key=lambda i: ({"error": 0, "warning": 1, "info": 2}[i.severity], i.line))
