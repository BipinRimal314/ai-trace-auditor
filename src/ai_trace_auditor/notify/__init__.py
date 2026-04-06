"""Compliance notification dispatchers (Slack, email)."""

from ai_trace_auditor.notify.slack import send_slack_notification

__all__ = ["send_slack_notification"]
