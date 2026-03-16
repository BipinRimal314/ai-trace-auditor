"""Analyze Claude Code traces for usage patterns and workflow insights."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class ToolUsage:
    name: str
    count: int
    pct: float  # percentage of total tool calls


@dataclass
class FileHotspot:
    path: str
    reads: int
    edits: int
    writes: int
    total: int


@dataclass
class SessionSummary:
    session_id: str
    date: str
    ai_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_create_tokens: int
    tool_calls: int
    top_tool: str
    duration_hours: float
    models: list[str]


@dataclass
class HourlyBucket:
    hour: int
    count: int
    pct: float


@dataclass
class CostBreakdown:
    total_input_tokens: int
    total_output_tokens: int
    cache_read_tokens: int
    cache_create_tokens: int
    fresh_input_tokens: int
    cache_read_pct: float
    est_cost_no_cache: float  # at list price
    est_cost_with_cache: float  # with cache discount


@dataclass
class WorkflowPattern:
    """Detected workflow pattern."""
    name: str
    description: str
    value: str
    recommendation: str | None = None


@dataclass
class InsightsReport:
    """Complete usage insights report."""
    generated_at: datetime
    source_path: str
    total_sessions: int
    total_ai_calls: int
    total_input_tokens: int
    total_output_tokens: int
    date_range: tuple[str, str]

    # Breakdowns
    cost: CostBreakdown
    models: list[tuple[str, int]]
    tool_usage: list[ToolUsage]
    file_hotspots_read: list[FileHotspot]
    file_hotspots_edit: list[FileHotspot]
    hourly_activity: list[HourlyBucket]
    sessions: list[SessionSummary]
    stop_reasons: list[tuple[str, int]]
    bash_commands: list[tuple[str, int]]
    workflow_patterns: list[WorkflowPattern]


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# Approximate pricing per million tokens (Claude Opus 4)
PRICE_INPUT_PER_M = 15.0
PRICE_OUTPUT_PER_M = 75.0
PRICE_CACHE_READ_PER_M = 1.5  # ~90% discount
PRICE_CACHE_CREATE_PER_M = 18.75  # 25% premium


def analyze_claude_code_dir(
    directory: Path,
    strip_prefix: str = "",
    since: datetime | None = None,
    until: datetime | None = None,
    tz_offset_hours: float = 0.0,
) -> InsightsReport:
    """Analyze all Claude Code .jsonl files in a directory.

    Args:
        directory: Path to a project's trace directory.
        strip_prefix: Path prefix to strip from file paths in reports.
        since: Only include sessions with activity on or after this date.
        until: Only include sessions with activity before this date.
        tz_offset_hours: Offset from UTC for hourly activity display.
    """
    files = sorted(directory.glob("*.jsonl"))
    if not files:
        raise ValueError(f"No .jsonl files found in {directory}")

    all_sessions: list[SessionSummary] = []
    total_calls = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    models_counter: Counter[str] = Counter()
    tool_counter: Counter[str] = Counter()
    stop_counter: Counter[str] = Counter()
    hourly: Counter[int] = Counter()
    read_files: Counter[str] = Counter()
    edit_files: Counter[str] = Counter()
    write_files: Counter[str] = Counter()
    bash_cmds: Counter[str] = Counter()
    all_dates: list[datetime] = []

    for fpath in files:
        session = _analyze_session(
            fpath, strip_prefix, models_counter, tool_counter,
            stop_counter, hourly, read_files, edit_files,
            write_files, bash_cmds, all_dates,
            tz_offset_hours=tz_offset_hours,
        )
        if session is None:
            continue

        # Apply date filter
        if since and session.date != "?":
            session_date = datetime.strptime(session.date, "%Y-%m-%d")
            if session_date < since.replace(tzinfo=None):
                continue
        if until and session.date != "?":
            session_date = datetime.strptime(session.date, "%Y-%m-%d")
            if session_date >= until.replace(tzinfo=None):
                continue

        all_sessions.append(session)
        total_calls += session.ai_calls
        total_input += session.input_tokens
        total_output += session.output_tokens
        total_cache_read += session.cache_read_tokens
        total_cache_create += session.cache_create_tokens

    if not all_sessions:
        raise ValueError(f"No AI calls found in {directory}")

    # Sort sessions by calls descending
    all_sessions.sort(key=lambda s: -s.ai_calls)

    # Compute derived metrics
    fresh_input = total_input - total_cache_read - total_cache_create
    cache_read_pct = total_cache_read / total_input * 100 if total_input > 0 else 0

    est_no_cache = (total_input / 1e6 * PRICE_INPUT_PER_M
                    + total_output / 1e6 * PRICE_OUTPUT_PER_M)
    est_with_cache = (
        fresh_input / 1e6 * PRICE_INPUT_PER_M
        + total_cache_create / 1e6 * PRICE_CACHE_CREATE_PER_M
        + total_cache_read / 1e6 * PRICE_CACHE_READ_PER_M
        + total_output / 1e6 * PRICE_OUTPUT_PER_M
    )

    cost = CostBreakdown(
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        cache_read_tokens=total_cache_read,
        cache_create_tokens=total_cache_create,
        fresh_input_tokens=fresh_input,
        cache_read_pct=cache_read_pct,
        est_cost_no_cache=est_no_cache,
        est_cost_with_cache=est_with_cache,
    )

    # Tool usage with percentages
    total_tool_calls = sum(tool_counter.values())
    tools = [
        ToolUsage(name=name, count=count, pct=count / total_tool_calls * 100)
        for name, count in tool_counter.most_common(20)
    ] if total_tool_calls > 0 else []

    # File hotspots
    all_files: set[str] = set(read_files) | set(edit_files) | set(write_files)
    hotspots = [
        FileHotspot(
            path=fp,
            reads=read_files.get(fp, 0),
            edits=edit_files.get(fp, 0),
            writes=write_files.get(fp, 0),
            total=read_files.get(fp, 0) + edit_files.get(fp, 0) + write_files.get(fp, 0),
        )
        for fp in all_files
    ]
    hotspots.sort(key=lambda h: -h.total)

    # Hotspots by read and edit separately
    read_hotspots = sorted(hotspots, key=lambda h: -h.reads)[:15]
    edit_hotspots = sorted(hotspots, key=lambda h: -h.edits)[:15]

    # Hourly activity with percentages
    max_hourly = max(hourly.values()) if hourly else 1
    hourly_buckets = [
        HourlyBucket(
            hour=h,
            count=hourly.get(h, 0),
            pct=hourly.get(h, 0) / total_calls * 100 if total_calls > 0 else 0,
        )
        for h in range(24)
    ]

    # Date range
    dates_sorted = sorted(all_dates) if all_dates else []
    date_range = (
        dates_sorted[0].strftime("%Y-%m-%d") if dates_sorted else "?",
        dates_sorted[-1].strftime("%Y-%m-%d") if dates_sorted else "?",
    )

    # Workflow patterns
    patterns = _detect_patterns(
        all_sessions, cost, tools, total_calls, total_tool_calls,
        hourly, edit_hotspots,
    )

    return InsightsReport(
        generated_at=datetime.now(timezone.utc),
        source_path=str(directory),
        total_sessions=len(all_sessions),
        total_ai_calls=total_calls,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        date_range=date_range,
        cost=cost,
        models=models_counter.most_common(),
        tool_usage=tools,
        file_hotspots_read=read_hotspots,
        file_hotspots_edit=edit_hotspots,
        hourly_activity=hourly_buckets,
        sessions=all_sessions,
        stop_reasons=stop_counter.most_common(),
        bash_commands=bash_cmds.most_common(15),
        workflow_patterns=patterns,
    )


def _analyze_session(
    fpath: Path,
    strip_prefix: str,
    models_counter: Counter[str],
    tool_counter: Counter[str],
    stop_counter: Counter[str],
    hourly: Counter[int],
    read_files: Counter[str],
    edit_files: Counter[str],
    write_files: Counter[str],
    bash_cmds: Counter[str],
    all_dates: list[datetime],
    tz_offset_hours: float = 0.0,
) -> SessionSummary | None:
    """Analyze a single session file."""
    calls = 0
    inp = 0
    out = 0
    cache_read = 0
    cache_create = 0
    session_tools: Counter[str] = Counter()
    session_models: set[str] = set()
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    session_id = fpath.stem

    detected_prefix = ""

    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)

                # Auto-detect strip prefix from session cwd
                if not strip_prefix and not detected_prefix:
                    cwd = obj.get("cwd")
                    if cwd:
                        detected_prefix = cwd if cwd.endswith("/") else cwd + "/"

                effective_prefix = strip_prefix or detected_prefix

                ts = _parse_ts(obj.get("timestamp"))
                if ts:
                    all_dates.append(ts)
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                    adjusted = ts + timedelta(hours=tz_offset_hours)
                    hourly[adjusted.hour] += 1

                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message", {})
                if not isinstance(msg, dict) or msg.get("type") != "message":
                    continue

                calls += 1
                usage = msg.get("usage", {})
                i = (usage.get("input_tokens") or 0)
                cc = (usage.get("cache_creation_input_tokens") or 0)
                cr = (usage.get("cache_read_input_tokens") or 0)
                o = (usage.get("output_tokens") or 0)
                inp += i + cc + cr
                out += o
                cache_read += cr
                cache_create += cc

                model = msg.get("model", "unknown")
                session_models.add(model)
                models_counter[model] += 1

                stop = msg.get("stop_reason") or "none"
                stop_counter[str(stop)] += 1

                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        name = block.get("name", "unknown")
                        session_tools[name] += 1
                        tool_counter[name] += 1

                        tool_input = block.get("input", {})
                        if not isinstance(tool_input, dict):
                            continue

                        fp = tool_input.get("file_path", "")
                        if fp and effective_prefix:
                            fp = fp.replace(effective_prefix, "")

                        if name == "Read" and fp:
                            read_files[fp] += 1
                        elif name == "Edit" and fp:
                            edit_files[fp] += 1
                        elif name == "Write" and fp:
                            write_files[fp] += 1
                        elif name == "Bash":
                            cmd = tool_input.get("command", "")
                            parts = cmd.split()
                            if parts:
                                bash_cmds[parts[0]] += 1
    except (json.JSONDecodeError, OSError):
        return None

    if calls == 0:
        return None

    duration = 0.0
    if first_ts and last_ts:
        duration = (last_ts - first_ts).total_seconds() / 3600

    top_tool = session_tools.most_common(1)[0][0] if session_tools else "-"

    return SessionSummary(
        session_id=session_id[:12],
        date=first_ts.strftime("%Y-%m-%d") if first_ts else "?",
        ai_calls=calls,
        input_tokens=inp,
        output_tokens=out,
        cache_read_tokens=cache_read,
        cache_create_tokens=cache_create,
        tool_calls=sum(session_tools.values()),
        top_tool=top_tool,
        duration_hours=duration,
        models=sorted(session_models),
    )


def _detect_patterns(
    sessions: list[SessionSummary],
    cost: CostBreakdown,
    tools: list[ToolUsage],
    total_calls: int,
    total_tool_calls: int,
    hourly: Counter[int],
    edit_hotspots: list[FileHotspot],
) -> list[WorkflowPattern]:
    """Detect workflow patterns from usage data."""
    patterns: list[WorkflowPattern] = []

    # 1. Builder vs. Advisor ratio
    tool_ratio = total_tool_calls / total_calls * 100 if total_calls > 0 else 0
    if tool_ratio > 60:
        style = "Builder"
        desc = f"{tool_ratio:.0f}% of AI output is tool calls. You use Claude as a hands-on builder, not a chatbot."
    elif tool_ratio > 40:
        style = "Hybrid"
        desc = f"{tool_ratio:.0f}% tool calls. Balanced between building and discussing."
    else:
        style = "Advisor"
        desc = f"Only {tool_ratio:.0f}% tool calls. You use Claude primarily for thinking and planning, not direct code manipulation."
    patterns.append(WorkflowPattern(
        name="Workflow Style",
        description=desc,
        value=style,
    ))

    # 2. Cache efficiency
    if cost.cache_read_pct > 90:
        patterns.append(WorkflowPattern(
            name="Cache Efficiency",
            description=f"{cost.cache_read_pct:.1f}% of input tokens are cache reads. Claude spends almost all input re-reading your codebase context, not processing new information.",
            value=f"{cost.cache_read_pct:.1f}%",
            recommendation="This is normal for Claude Code. Long conversations benefit most from caching.",
        ))
    elif cost.cache_read_pct > 50:
        patterns.append(WorkflowPattern(
            name="Cache Efficiency",
            description=f"{cost.cache_read_pct:.1f}% cache hit rate. Moderate caching efficiency.",
            value=f"{cost.cache_read_pct:.1f}%",
            recommendation="Longer focused sessions on one topic improve cache utilization.",
        ))

    # 3. Session intensity
    if sessions:
        heaviest = sessions[0]
        avg_calls = total_calls / len(sessions)
        patterns.append(WorkflowPattern(
            name="Session Intensity",
            description=f"Heaviest session: {heaviest.ai_calls:,} AI calls over {heaviest.duration_hours:.1f}h. Average: {avg_calls:.0f} calls/session.",
            value=f"{heaviest.ai_calls:,} peak, {avg_calls:.0f} avg",
        ))

    # 4. Iteration hotspots
    if edit_hotspots and edit_hotspots[0].edits > 20:
        top = edit_hotspots[0]
        patterns.append(WorkflowPattern(
            name="Iteration Hotspot",
            description=f"Most iterated file: {top.path} ({top.edits} edits, {top.reads} reads). High edit counts suggest complex logic that needed multiple refinement passes.",
            value=top.path,
            recommendation="Files with 50+ edits may benefit from being broken into smaller modules.",
        ))

    # 5. Working hours
    peak_hour = max(range(24), key=lambda h: hourly.get(h, 0))
    peak_count = hourly.get(peak_hour, 0)
    total_hourly = sum(hourly.values())
    night_calls = sum(hourly.get(h, 0) for h in range(0, 6))
    night_pct = night_calls / total_hourly * 100 if total_hourly > 0 else 0

    patterns.append(WorkflowPattern(
        name="Peak Hours",
        description=f"Most active hour: {peak_hour:02d}:00 UTC ({peak_count:,} calls, {peak_count/total_hourly*100:.1f}% of total).",
        value=f"{peak_hour:02d}:00 UTC",
    ))

    if night_pct > 20:
        patterns.append(WorkflowPattern(
            name="Night Owl Alert",
            description=f"{night_pct:.0f}% of your AI usage happens between midnight and 6 AM UTC. That's a lot of late-night coding.",
            value=f"{night_pct:.0f}% nocturnal",
            recommendation="Consider whether late-night sessions produce your best work or just your most caffeinated.",
        ))

    # 6. Cost savings from caching
    if cost.est_cost_no_cache > 100:
        savings = cost.est_cost_no_cache - cost.est_cost_with_cache
        savings_pct = savings / cost.est_cost_no_cache * 100
        patterns.append(WorkflowPattern(
            name="Cache Savings",
            description=f"Estimated cost without caching: ${cost.est_cost_no_cache:,.0f}. With caching: ${cost.est_cost_with_cache:,.0f}. Caching saved ~${savings:,.0f} ({savings_pct:.0f}%).",
            value=f"${savings:,.0f} saved",
        ))

    # 7. Primary tool preference
    if tools:
        top3 = tools[:3]
        tool_desc = ", ".join(f"{t.name} ({t.pct:.0f}%)" for t in top3)
        patterns.append(WorkflowPattern(
            name="Tool Preference",
            description=f"Top tools: {tool_desc}. This shapes how Claude collaborates with you.",
            value=top3[0].name,
        ))

    # 8. Read-before-edit ratio
    total_reads = sum(1 for t in tools if t.name == "Read")
    total_edits = sum(1 for t in tools if t.name == "Edit")
    read_count = next((t.count for t in tools if t.name == "Read"), 0)
    edit_count = next((t.count for t in tools if t.name == "Edit"), 0)
    if read_count > 0 and edit_count > 0:
        ratio = read_count / edit_count
        if ratio > 1.5:
            patterns.append(WorkflowPattern(
                name="Read-Heavy",
                description=f"Read/Edit ratio: {ratio:.1f}x. Claude reads significantly more than it edits, suggesting careful exploration before changes.",
                value=f"{ratio:.1f}x",
            ))
        elif ratio < 0.5:
            patterns.append(WorkflowPattern(
                name="Edit-Heavy",
                description=f"Read/Edit ratio: {ratio:.1f}x. Claude edits more than it reads. Fast iteration, but may miss context.",
                value=f"{ratio:.1f}x",
                recommendation="Consider whether more upfront reading would reduce edit iterations.",
            ))

    return patterns
