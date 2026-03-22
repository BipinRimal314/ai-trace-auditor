"""Agent-friendly documentation checks.

Validates whether generated compliance documentation is consumable by
AI coding agents, following principles from the Agent-Friendly
Documentation Spec (agentdocsspec.com).
"""

from ai_trace_auditor.agent_friendly.checker import (
    AgentFriendlyReport,
    CheckResult,
    check_agent_friendly,
)

__all__ = ["AgentFriendlyReport", "CheckResult", "check_agent_friendly"]
