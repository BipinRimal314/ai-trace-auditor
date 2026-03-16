"""Session health scoring.

Combines conversation traces with debug logs to produce a health score
per session. Identifies friction points, failure patterns, and workflow
blockers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_trace_auditor.insights.analyzer import SessionSummary
from ai_trace_auditor.insights.debug_parser import DebugLogSummary


@dataclass
class FrictionPoint:
    """A specific source of workflow friction."""
    category: str  # "tool_error", "streaming_stall", "api_error", "mcp_failure"
    severity: str  # "high", "medium", "low"
    count: int
    description: str
    recommendation: str


@dataclass
class SessionHealth:
    """Health assessment for a single session."""
    session_id: str
    score: int  # 0-100
    grade: str  # A, B, C, D, F

    # Component scores (each 0-100)
    tool_reliability: int
    streaming_stability: int
    api_reliability: int
    startup_speed: int
    mcp_health: int

    # Friction points
    friction_points: list[FrictionPoint]

    # Key metrics
    total_errors: int
    total_stall_seconds: float
    tool_error_count: int
    api_error_count: int
    stall_count: int
    boot_time_ms: float


def score_session(
    session: SessionSummary | None,
    debug: DebugLogSummary | None,
) -> SessionHealth:
    """Score a session's health from conversation + debug data.

    Either input can be None if data is unavailable; the score
    adjusts to use whatever data exists.
    """
    friction: list[FrictionPoint] = []

    # 1. Tool reliability (0-100)
    tool_reliability = 100
    tool_errors = 0
    if debug and debug.tool_errors:
        tool_errors = len(debug.tool_errors)
        # Deduct 8 points per tool error, floor at 0
        tool_reliability = max(0, 100 - tool_errors * 8)

        # Categorize tool errors
        for tool, count in sorted(debug.tool_error_rate.items(), key=lambda x: -x[1]):
            sev = "high" if count >= 5 else "medium" if count >= 2 else "low"
            # Generate specific recommendations
            rec = _tool_error_recommendation(tool, count)
            friction.append(FrictionPoint(
                category="tool_error",
                severity=sev,
                count=count,
                description=f"{tool} failed {count} time{'s' if count != 1 else ''}",
                recommendation=rec,
            ))

    # 2. Streaming stability (0-100)
    streaming_stability = 100
    stall_count = 0
    total_stall_seconds = 0.0
    if debug and debug.streaming_stalls:
        stall_count = len(debug.streaming_stalls)
        total_stall_seconds = debug.total_stall_seconds

        # Deduct based on stall severity
        for stall in debug.streaming_stalls:
            if stall.gap_seconds > 200:
                streaming_stability -= 15
            elif stall.gap_seconds > 100:
                streaming_stability -= 10
            elif stall.gap_seconds > 50:
                streaming_stability -= 5
            else:
                streaming_stability -= 2
        streaming_stability = max(0, streaming_stability)

        if stall_count > 0:
            avg_stall = total_stall_seconds / stall_count
            sev = "high" if avg_stall > 120 else "medium"
            friction.append(FrictionPoint(
                category="streaming_stall",
                severity=sev,
                count=stall_count,
                description=f"{stall_count} streaming stalls, {total_stall_seconds:.0f}s total wait",
                recommendation=(
                    "Streaming stalls indicate network instability or server load. "
                    "If frequent, check your internet connection or try during off-peak hours."
                ),
            ))

    # 3. API reliability (0-100)
    api_reliability = 100
    api_errors = 0
    if debug and debug.api_errors:
        api_errors = len(debug.api_errors)
        api_reliability = max(0, 100 - api_errors * 15)

        # Group by message
        error_msgs: dict[str, int] = {}
        for err in debug.api_errors:
            key = err.message[:80]
            error_msgs[key] = error_msgs.get(key, 0) + 1

        for msg, count in error_msgs.items():
            friction.append(FrictionPoint(
                category="api_error",
                severity="high",
                count=count,
                description=f"API error: {msg} ({count}x)",
                recommendation=(
                    "API errors may indicate rate limiting, network issues, or "
                    "server-side problems. Check Anthropic status page if recurring."
                ),
            ))

    # 4. Startup speed (0-100)
    startup_speed = 100
    boot_time_ms = 0.0
    if debug and debug.startup:
        boot_time_ms = debug.startup.total_ms
        if boot_time_ms > 5000:
            startup_speed = 50
            friction.append(FrictionPoint(
                category="startup",
                severity="medium",
                count=1,
                description=f"Slow startup: {boot_time_ms:.0f}ms",
                recommendation=(
                    "Startup is slow. Check MCP server connections and plugin count. "
                    "Disconnecting unused MCP servers speeds up boot."
                ),
            ))
        elif boot_time_ms > 2000:
            startup_speed = 75
        elif boot_time_ms > 1000:
            startup_speed = 90

    # 5. MCP health (0-100)
    mcp_health = 100
    if debug and debug.mcp_events:
        failures = [e for e in debug.mcp_events if e.event_type in ("failed", "error")]
        if failures:
            mcp_health = max(0, 100 - len(failures) * 20)
            # Group by server
            servers: dict[str, int] = {}
            for f in failures:
                servers[f.server] = servers.get(f.server, 0) + 1

            for server, count in servers.items():
                friction.append(FrictionPoint(
                    category="mcp_failure",
                    severity="medium" if count < 3 else "high",
                    count=count,
                    description=f"MCP server \"{server}\" failed {count}x",
                    recommendation=(
                        f"MCP server \"{server}\" is failing to connect. "
                        "Check authentication or disconnect it if unused."
                    ),
                ))

    # Overall score: weighted average
    total_errors = tool_errors + api_errors
    weights = {
        "tool": 30,
        "streaming": 20,
        "api": 25,
        "startup": 10,
        "mcp": 15,
    }
    weighted_sum = (
        tool_reliability * weights["tool"]
        + streaming_stability * weights["streaming"]
        + api_reliability * weights["api"]
        + startup_speed * weights["startup"]
        + mcp_health * weights["mcp"]
    )
    score = round(weighted_sum / sum(weights.values()))

    # Grade
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    # Sort friction by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    friction.sort(key=lambda f: severity_order.get(f.severity, 3))

    return SessionHealth(
        session_id=debug.session_id if debug else (session.session_id if session else "unknown"),
        score=score,
        grade=grade,
        tool_reliability=tool_reliability,
        streaming_stability=streaming_stability,
        api_reliability=api_reliability,
        startup_speed=startup_speed,
        mcp_health=mcp_health,
        friction_points=friction,
        total_errors=total_errors,
        total_stall_seconds=total_stall_seconds,
        tool_error_count=tool_errors,
        api_error_count=api_errors,
        stall_count=stall_count,
        boot_time_ms=boot_time_ms,
    )


def aggregate_health(healths: list[SessionHealth]) -> dict[str, Any]:
    """Aggregate health scores across sessions for summary stats."""
    if not healths:
        return {}

    from typing import Any

    scores = [h.score for h in healths]
    avg_score = sum(scores) / len(scores)

    # Aggregate friction points
    friction_totals: dict[str, int] = {}
    for h in healths:
        for fp in h.friction_points:
            key = fp.category
            friction_totals[key] = friction_totals.get(key, 0) + fp.count

    # Grade distribution
    grades: dict[str, int] = {}
    for h in healths:
        grades[h.grade] = grades.get(h.grade, 0) + 1

    return {
        "sessions_analyzed": len(healths),
        "average_score": round(avg_score, 1),
        "min_score": min(scores),
        "max_score": max(scores),
        "grade_distribution": grades,
        "friction_totals": friction_totals,
        "total_stall_seconds": sum(h.total_stall_seconds for h in healths),
        "total_tool_errors": sum(h.tool_error_count for h in healths),
        "total_api_errors": sum(h.api_error_count for h in healths),
    }


def _tool_error_recommendation(tool: str, count: int) -> str:
    """Generate tool-specific recommendations."""
    recs = {
        "Bash": (
            "Shell commands are failing. Common causes: missing dependencies, "
            "wrong working directory, or permission issues. Check the specific "
            "commands that failed."
        ),
        "Read": (
            "File read errors usually mean the file doesn't exist or the path "
            "is wrong. If frequent, ensure your CLAUDE.md documents the correct "
            "project structure."
        ),
        "Write": (
            "File write failures may indicate permission issues or locked files. "
            "Check if another process has the file open."
        ),
        "WebFetch": (
            "Web fetch failures indicate unreachable URLs, SSL issues, or blocked "
            "domains. Check your network and the target site's availability."
        ),
        "Edit": (
            "Edit failures usually mean the old_string wasn't found in the file. "
            "This happens when Claude's context is stale. Shorter sessions reduce this."
        ),
    }
    return recs.get(tool, f"{tool} tool failed {count} times. Check the error messages for details.")
