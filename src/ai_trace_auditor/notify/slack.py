"""Slack webhook notification for compliance results."""

from __future__ import annotations

from typing import Any

import ai_trace_auditor
from ai_trace_auditor.comply.runner import CompliancePackage


def format_slack_message(pkg: CompliancePackage) -> dict[str, Any]:
    """Format a CompliancePackage into a Slack Block Kit message."""
    score = pkg.compliance_score
    score_text = f"{score * 100:.1f}%" if score is not None else "N/A (no traces)"
    emoji = ":white_check_mark:" if score and score >= 0.9 else ":warning:" if score and score >= 0.5 else ":x:"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} EU AI Act Compliance Report",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Compliance Score:*\n{score_text}"},
                {"type": "mrkdwn", "text": f"*Source:*\n`{pkg.source_dir}`"},
            ],
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Articles Covered:*\n{len(pkg.articles_covered)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Tool Version:*\nv{ai_trace_auditor.__version__}",
                },
            ],
        },
    ]

    # Top gaps
    if pkg.gap_report and pkg.gap_report.summary.top_gaps:
        gaps_text = "\n".join(
            f"- {gap}" for gap in pkg.gap_report.summary.top_gaps[:3]
        )
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Top Gaps:*\n{gaps_text}",
            },
        })

    # Warnings count
    if pkg.warnings:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":information_source: {len(pkg.warnings)} warning(s). See full report for details.",
                }
            ],
        })

    return {"blocks": blocks}


def send_slack_notification(webhook_url: str, pkg: CompliancePackage) -> bool:
    """Send compliance results to a Slack webhook.

    Returns True if the message was accepted (HTTP 200), False otherwise.
    Requires httpx: pip install ai-trace-auditor[notify]
    """
    try:
        import httpx
    except ImportError as e:
        raise ImportError(
            "Slack notifications require httpx. "
            "Install with: pip install ai-trace-auditor[notify]"
        ) from e

    import sys

    payload = format_slack_message(pkg)
    resp = httpx.post(webhook_url, json=payload, timeout=10)
    if resp.status_code != 200:
        print(
            f"[ai-trace-auditor] Slack notification failed: "
            f"HTTP {resp.status_code} — {resp.text[:200]}",
            file=sys.stderr,
        )
        return False
    return True
