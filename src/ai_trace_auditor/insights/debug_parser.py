"""Parse Claude Code debug logs (~/.claude/debug/*.txt).

Each line follows the format:
  2026-02-26T19:20:38.262Z [LEVEL] message

Extracts structured events: tool errors, streaming stalls, API errors,
MCP failures, startup timing, permission rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ToolError:
    timestamp: datetime
    tool: str  # "Bash", "Read", "WebFetch", etc.
    duration_ms: float
    message: str


@dataclass
class StreamingStall:
    timestamp: datetime
    gap_seconds: float
    stall_number: int


@dataclass
class APIError:
    timestamp: datetime
    attempt: int
    max_attempts: int
    message: str


@dataclass
class MCPEvent:
    timestamp: datetime
    server: str
    event_type: str  # "connected", "failed", "error"
    duration_ms: float | None
    message: str


@dataclass
class StartupTiming:
    total_ms: float
    setup_ms: float
    mcp_load_ms: float
    commands_load_ms: float
    screens_ms: float


@dataclass
class DebugLogSummary:
    """Parsed summary of a debug log file."""
    session_id: str
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    duration_hours: float

    # Counts by level
    debug_count: int
    info_count: int
    warn_count: int
    error_count: int

    # Structured events
    tool_errors: list[ToolError]
    streaming_stalls: list[StreamingStall]
    api_errors: list[APIError]
    mcp_events: list[MCPEvent]
    startup: StartupTiming | None

    # Permission summary
    allow_rules_count: int
    permission_sources: dict[str, int]  # {"userSettings": 4, "localSettings": 110, ...}

    # Derived
    total_stall_seconds: float
    tool_error_rate: dict[str, int]  # {"Bash": 3, "Read": 2, ...}


# Regex patterns
LOG_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+\[(\w+)\]\s+(.*)"
)

TOOL_ERROR = re.compile(
    r"(\w+) tool error \((\d+)ms\): (.*)"
)

STREAMING_STALL = re.compile(
    r"Streaming stall detected: ([\d.]+)s gap between events \(stall #(\d+)\)"
)

API_ERROR = re.compile(
    r"API error \(attempt (\d+)/(\d+)\): (.+)"
)

MCP_SERVER = re.compile(
    r'MCP server "([^"]+)"[:\s]+(.*)'
)

MCP_CONNECTED = re.compile(
    r"connected after (\d+)ms"
)

MCP_FAILED = re.compile(
    r"(?:connection failed after|failed after) (\d+)ms: (.*)"
)

PERMISSION_UPDATE = re.compile(
    r"Applying permission update: Adding (\d+) allow rule\(s\) to destination '(\w+)'"
)

STARTUP_COMPLETED = re.compile(
    r"\[STARTUP\] (\w[\w()]*) completed in (\d+)ms"
)

MCP_LOADED = re.compile(
    r"\[STARTUP\] MCP configs loaded in (\d+)ms"
)


def _parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_debug_log(path: Path) -> DebugLogSummary:
    """Parse a single debug log file into a structured summary."""
    session_id = path.stem

    level_counts = {"DEBUG": 0, "INFO": 0, "WARN": 0, "ERROR": 0}
    tool_errors: list[ToolError] = []
    streaming_stalls: list[StreamingStall] = []
    api_errors: list[APIError] = []
    mcp_events: list[MCPEvent] = []
    permission_sources: dict[str, int] = {}
    startup_parts: dict[str, float] = {}

    first_ts: datetime | None = None
    last_ts: datetime | None = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LOG_LINE.match(line)
            if not m:
                continue

            ts_str, level, message = m.groups()
            ts = _parse_timestamp(ts_str)

            if first_ts is None:
                first_ts = ts
            last_ts = ts

            level_counts[level] = level_counts.get(level, 0) + 1

            # Tool errors
            tm = TOOL_ERROR.search(message)
            if tm:
                tool_errors.append(ToolError(
                    timestamp=ts,
                    tool=tm.group(1),
                    duration_ms=float(tm.group(2)),
                    message=tm.group(3),
                ))
                continue

            # Streaming stalls
            sm = STREAMING_STALL.search(message)
            if sm:
                streaming_stalls.append(StreamingStall(
                    timestamp=ts,
                    gap_seconds=float(sm.group(1)),
                    stall_number=int(sm.group(2)),
                ))
                continue

            # API errors
            am = API_ERROR.search(message)
            if am:
                api_errors.append(APIError(
                    timestamp=ts,
                    attempt=int(am.group(1)),
                    max_attempts=int(am.group(2)),
                    message=am.group(3),
                ))
                continue

            # MCP events
            mm = MCP_SERVER.search(message)
            if mm:
                server_name = mm.group(1)
                detail = mm.group(2)

                evt_type = "info"
                dur = None

                cm = MCP_CONNECTED.search(detail)
                if cm:
                    evt_type = "connected"
                    dur = float(cm.group(1))

                fm = MCP_FAILED.search(detail)
                if fm:
                    evt_type = "failed"
                    dur = float(fm.group(1))

                if level == "ERROR":
                    evt_type = "error"

                mcp_events.append(MCPEvent(
                    timestamp=ts,
                    server=server_name,
                    event_type=evt_type,
                    duration_ms=dur,
                    message=detail[:200],
                ))
                continue

            # Permission rules
            pm = PERMISSION_UPDATE.search(message)
            if pm:
                count = int(pm.group(1))
                dest = pm.group(2)
                permission_sources[dest] = count
                continue

            # Startup timing
            su = STARTUP_COMPLETED.search(message)
            if su:
                name = su.group(1)
                ms = float(su.group(2))
                startup_parts[name] = ms

            ml = MCP_LOADED.search(message)
            if ml:
                startup_parts["mcp_load"] = float(ml.group(1))

    # Build startup timing
    startup = None
    if startup_parts:
        startup = StartupTiming(
            total_ms=sum(startup_parts.values()),
            setup_ms=startup_parts.get("setup()", 0),
            mcp_load_ms=startup_parts.get("mcp_load", 0),
            commands_load_ms=startup_parts.get("Commands", startup_parts.get("agents", 0)),
            screens_ms=startup_parts.get("showSetupScreens()", 0),
        )

    # Compute derived
    duration = 0.0
    if first_ts and last_ts:
        duration = (last_ts - first_ts).total_seconds() / 3600

    total_stall = sum(s.gap_seconds for s in streaming_stalls)

    tool_error_rate: dict[str, int] = {}
    for te in tool_errors:
        tool_error_rate[te.tool] = tool_error_rate.get(te.tool, 0) + 1

    return DebugLogSummary(
        session_id=session_id,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        duration_hours=duration,
        debug_count=level_counts.get("DEBUG", 0),
        info_count=level_counts.get("INFO", 0),
        warn_count=level_counts.get("WARN", 0),
        error_count=level_counts.get("ERROR", 0),
        tool_errors=tool_errors,
        streaming_stalls=streaming_stalls,
        api_errors=api_errors,
        mcp_events=mcp_events,
        startup=startup,
        allow_rules_count=sum(permission_sources.values()),
        permission_sources=permission_sources,
        total_stall_seconds=total_stall,
        tool_error_rate=tool_error_rate,
    )


def parse_all_debug_logs(debug_dir: Path | None = None) -> dict[str, DebugLogSummary]:
    """Parse all debug logs, keyed by session ID."""
    if debug_dir is None:
        debug_dir = Path.home() / ".claude" / "debug"

    if not debug_dir.exists():
        return {}

    results: dict[str, DebugLogSummary] = {}
    for path in debug_dir.glob("*.txt"):
        try:
            summary = parse_debug_log(path)
            results[summary.session_id] = summary
        except (OSError, ValueError):
            continue

    return results
