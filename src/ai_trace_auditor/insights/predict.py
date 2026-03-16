"""Predictive and proactive analysis.

5.1 Cost forecasting — project next period's cost from daily trends
5.2 Context pressure — detect sessions hitting context limits
5.3 CLAUDE.md effectiveness — measure impact of project docs on efficiency
5.4 Permission optimization — identify unused/missing allow rules
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_trace_auditor.insights.debug_parser import parse_all_debug_logs


# ── Cost Forecasting ────────────────────────────────────────────────────────

PRICE_CACHE_READ_PER_M = 1.5
PRICE_CACHE_CREATE_PER_M = 18.75
PRICE_FRESH_INPUT_PER_M = 15.0
PRICE_OUTPUT_PER_M = 75.0


@dataclass
class DailyUsage:
    date: str
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    est_cost: float


@dataclass
class CostForecast:
    daily_usage: list[DailyUsage]
    total_days: int
    active_days: int
    avg_daily_cost: float
    avg_active_day_cost: float
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_pct: float  # percent change recent vs earlier
    forecast_7d: float
    forecast_30d: float
    busiest_day: DailyUsage | None
    quietest_day: DailyUsage | None


# ── Context Pressure ────────────────────────────────────────────────────────


@dataclass
class SessionPressure:
    session_id: str
    date: str
    total_calls: int
    max_single_input: int
    cumulative_input: int
    input_growth_rate: float  # avg increase per call
    likely_compressed: bool
    peak_call_number: int  # which call had the max input


@dataclass
class ContextPressureReport:
    sessions_analyzed: int
    sessions_likely_compressed: int
    compression_rate: float
    avg_cumulative_input: float
    max_cumulative_input: int
    sessions: list[SessionPressure]


# ── CLAUDE.md Effectiveness ─────────────────────────────────────────────────


@dataclass
class ClaudeMdInsight:
    """Insight about CLAUDE.md effectiveness."""
    metric: str
    with_reads: float  # value when CLAUDE.md was read
    without_reads: float  # value when CLAUDE.md was not read
    delta_pct: float  # percentage difference
    recommendation: str


@dataclass
class FrequentlyReadFile:
    """File that's read repeatedly — candidate for CLAUDE.md documentation."""
    path: str
    total_reads: int
    session_count: int
    avg_reads_per_session: float


@dataclass
class ClaudeMdReport:
    projects_with_claude_md: int
    projects_without: int
    insights: list[ClaudeMdInsight]
    suggested_additions: list[FrequentlyReadFile]


# ── Permission Optimization ─────────────────────────────────────────────────


@dataclass
class PermissionInsight:
    total_rules: int
    rules_by_source: dict[str, int]
    unused_estimate: str  # qualitative since we can't track usage precisely
    recommendation: str


# ── Combined Report ─────────────────────────────────────────────────────────


@dataclass
class PredictiveReport:
    cost_forecast: CostForecast
    context_pressure: ContextPressureReport
    claude_md: ClaudeMdReport
    permissions: PermissionInsight | None


# ── Implementation ──────────────────────────────────────────────────────────


def build_predictive_report(
    projects_dir: Path | None = None,
    debug_dir: Path | None = None,
) -> PredictiveReport:
    """Build the complete predictive analysis report."""
    if projects_dir is None:
        projects_dir = Path.home() / ".claude" / "projects"

    cost = _forecast_cost(projects_dir)
    pressure = _analyze_context_pressure(projects_dir)
    claude_md = _analyze_claude_md_effectiveness(projects_dir)
    perms = _analyze_permissions(debug_dir)

    return PredictiveReport(
        cost_forecast=cost,
        context_pressure=pressure,
        claude_md=claude_md,
        permissions=perms,
    )


def _forecast_cost(projects_dir: Path) -> CostForecast:
    """Build daily usage timeline and forecast future costs."""
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {
        "calls": 0, "input": 0, "output": 0, "cache_read": 0, "cache_create": 0,
    })

    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        for fpath in proj_dir.glob("*.jsonl"):
            try:
                with open(fpath, encoding="utf-8") as f:
                    for line in f:
                        obj = json.loads(line.strip())
                        if obj.get("type") != "assistant":
                            continue
                        msg = obj.get("message", {})
                        if not isinstance(msg, dict) or msg.get("type") != "message":
                            continue
                        ts = obj.get("timestamp", "")
                        if not ts:
                            continue
                        day = ts[:10]
                        usage = msg.get("usage", {})
                        inp = usage.get("input_tokens") or 0
                        cr = usage.get("cache_read_input_tokens") or 0
                        cc = usage.get("cache_creation_input_tokens") or 0
                        out = usage.get("output_tokens") or 0
                        daily[day]["calls"] += 1
                        daily[day]["input"] += inp + cr + cc
                        daily[day]["output"] += out
                        daily[day]["cache_read"] += cr
                        daily[day]["cache_create"] += cc
            except (json.JSONDecodeError, OSError):
                continue

    if not daily:
        return CostForecast(
            daily_usage=[], total_days=0, active_days=0,
            avg_daily_cost=0, avg_active_day_cost=0,
            trend_direction="stable", trend_pct=0,
            forecast_7d=0, forecast_30d=0,
            busiest_day=None, quietest_day=None,
        )

    # Build sorted daily list
    usage_list: list[DailyUsage] = []
    for day in sorted(daily.keys()):
        d = daily[day]
        fresh = d["input"] - d["cache_read"] - d["cache_create"]
        cost = (
            max(0, fresh) / 1e6 * PRICE_FRESH_INPUT_PER_M
            + d["cache_read"] / 1e6 * PRICE_CACHE_READ_PER_M
            + d["cache_create"] / 1e6 * PRICE_CACHE_CREATE_PER_M
            + d["output"] / 1e6 * PRICE_OUTPUT_PER_M
        )
        usage_list.append(DailyUsage(
            date=day, calls=d["calls"],
            input_tokens=d["input"], output_tokens=d["output"],
            cache_read_tokens=d["cache_read"], est_cost=cost,
        ))

    # Compute date range
    first = datetime.strptime(usage_list[0].date, "%Y-%m-%d")
    last = datetime.strptime(usage_list[-1].date, "%Y-%m-%d")
    total_days = max(1, (last - first).days + 1)
    active_days = len(usage_list)

    total_cost = sum(u.est_cost for u in usage_list)
    avg_daily = total_cost / total_days
    avg_active = total_cost / active_days if active_days > 0 else 0

    # Trend: compare first half vs second half
    mid = len(usage_list) // 2
    first_half_cost = sum(u.est_cost for u in usage_list[:mid]) if mid > 0 else 0
    second_half_cost = sum(u.est_cost for u in usage_list[mid:]) if mid > 0 else 0

    if first_half_cost > 0:
        trend_pct = (second_half_cost - first_half_cost) / first_half_cost * 100
    else:
        trend_pct = 0

    if trend_pct > 20:
        trend_dir = "increasing"
    elif trend_pct < -20:
        trend_dir = "decreasing"
    else:
        trend_dir = "stable"

    # Forecast using recent 7-day average
    recent = usage_list[-7:] if len(usage_list) >= 7 else usage_list
    recent_avg = sum(u.est_cost for u in recent) / len(recent)
    # Adjust for active day frequency
    active_ratio = active_days / total_days
    forecast_7d = recent_avg * 7 * active_ratio
    forecast_30d = recent_avg * 30 * active_ratio

    busiest = max(usage_list, key=lambda u: u.est_cost)
    quietest = min(usage_list, key=lambda u: u.est_cost)

    return CostForecast(
        daily_usage=usage_list,
        total_days=total_days,
        active_days=active_days,
        avg_daily_cost=avg_daily,
        avg_active_day_cost=avg_active,
        trend_direction=trend_dir,
        trend_pct=trend_pct,
        forecast_7d=forecast_7d,
        forecast_30d=forecast_30d,
        busiest_day=busiest,
        quietest_day=quietest,
    )


def _analyze_context_pressure(projects_dir: Path) -> ContextPressureReport:
    """Detect sessions that likely hit context window limits."""
    sessions: list[SessionPressure] = []

    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        for fpath in proj_dir.glob("*.jsonl"):
            result = _check_session_pressure(fpath)
            if result:
                sessions.append(result)

    compressed = [s for s in sessions if s.likely_compressed]
    avg_cum = sum(s.cumulative_input for s in sessions) / len(sessions) if sessions else 0
    max_cum = max((s.cumulative_input for s in sessions), default=0)

    sessions.sort(key=lambda s: -s.cumulative_input)

    return ContextPressureReport(
        sessions_analyzed=len(sessions),
        sessions_likely_compressed=len(compressed),
        compression_rate=len(compressed) / len(sessions) if sessions else 0,
        avg_cumulative_input=avg_cum,
        max_cumulative_input=max_cum,
        sessions=sessions[:20],
    )


def _check_session_pressure(fpath: Path) -> SessionPressure | None:
    """Check a single session for context pressure signals."""
    call_num = 0
    max_input = 0
    cumulative = 0
    peak_call = 0
    input_values: list[int] = []
    date_str = "?"

    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line.strip())
                ts = obj.get("timestamp", "")
                if ts and date_str == "?":
                    date_str = ts[:10]
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message", {})
                if not isinstance(msg, dict) or msg.get("type") != "message":
                    continue
                call_num += 1
                usage = msg.get("usage", {})
                inp = (usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                cumulative += inp
                input_values.append(inp)
                if inp > max_input:
                    max_input = inp
                    peak_call = call_num
    except (json.JSONDecodeError, OSError):
        return None

    if call_num < 5:
        return None

    # Growth rate: average increase in input tokens per call
    growth = 0.0
    if len(input_values) >= 10:
        first_5 = sum(input_values[:5]) / 5
        last_5 = sum(input_values[-5:]) / 5
        if first_5 > 0:
            growth = (last_5 - first_5) / first_5

    # Heuristic: likely compressed if cumulative > 800M tokens
    # (context compression typically triggers around 200K tokens per turn,
    # but across many turns the cumulative grows large)
    # More practically: if the input per call starts DECREASING after growing,
    # that suggests context was compressed
    likely = False
    if len(input_values) >= 20:
        # Check if late-session inputs are significantly smaller than mid-session
        mid_avg = sum(input_values[len(input_values)//3:2*len(input_values)//3]) / max(1, len(input_values)//3)
        late_avg = sum(input_values[-len(input_values)//5:]) / max(1, len(input_values)//5)
        if mid_avg > 0 and late_avg < mid_avg * 0.7:
            likely = True

    return SessionPressure(
        session_id=fpath.stem[:12],
        date=date_str,
        total_calls=call_num,
        max_single_input=max_input,
        cumulative_input=cumulative,
        input_growth_rate=growth,
        likely_compressed=likely,
        peak_call_number=peak_call,
    )


def _analyze_claude_md_effectiveness(projects_dir: Path) -> ClaudeMdReport:
    """Analyze whether CLAUDE.md presence correlates with better session metrics."""
    # Group sessions by whether they read CLAUDE.md
    with_reads: list[dict[str, float]] = []
    without_reads: list[dict[str, float]] = []
    file_read_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    projects_with = 0
    projects_without = 0

    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue

        # Check if this project has a CLAUDE.md (by checking if sessions read it)
        project_has_claude_md = False

        for fpath in proj_dir.glob("*.jsonl"):
            session_metrics = _extract_session_metrics(fpath)
            if session_metrics is None:
                continue

            if session_metrics["claude_md_reads"] > 0:
                project_has_claude_md = True
                with_reads.append(session_metrics)
            else:
                without_reads.append(session_metrics)

            # Track all file reads for suggestion generation
            for fp, count in session_metrics.get("file_reads", {}).items():
                file_read_counts[fp]["total"] += count
                file_read_counts[fp]["sessions"] += 1

        if project_has_claude_md:
            projects_with += 1
        elif list(proj_dir.glob("*.jsonl")):
            projects_without += 1

    # Compare metrics
    insights: list[ClaudeMdInsight] = []

    if with_reads and without_reads:
        # Correction rate comparison
        avg_corr_with = sum(s["correction_rate"] for s in with_reads) / len(with_reads)
        avg_corr_without = sum(s["correction_rate"] for s in without_reads) / len(without_reads)
        if avg_corr_without > 0:
            delta = (avg_corr_with - avg_corr_without) / avg_corr_without * 100
            insights.append(ClaudeMdInsight(
                metric="Correction rate",
                with_reads=avg_corr_with,
                without_reads=avg_corr_without,
                delta_pct=delta,
                recommendation=(
                    "Sessions where CLAUDE.md was read have "
                    f"{'lower' if delta < 0 else 'higher'} correction rates."
                ),
            ))

        # Token efficiency comparison
        avg_eff_with = sum(s["token_ratio"] for s in with_reads) / len(with_reads)
        avg_eff_without = sum(s["token_ratio"] for s in without_reads) / len(without_reads)
        if avg_eff_without > 0:
            delta = (avg_eff_with - avg_eff_without) / avg_eff_without * 100
            insights.append(ClaudeMdInsight(
                metric="Token efficiency",
                with_reads=avg_eff_with,
                without_reads=avg_eff_without,
                delta_pct=delta,
                recommendation=(
                    f"Token efficiency is {abs(delta):.0f}% "
                    f"{'higher' if delta > 0 else 'lower'} when CLAUDE.md is read."
                ),
            ))

        # Avg edits per file
        avg_edits_with = sum(s["avg_edits_per_file"] for s in with_reads) / len(with_reads)
        avg_edits_without = sum(s["avg_edits_per_file"] for s in without_reads) / len(without_reads)
        if avg_edits_without > 0:
            delta = (avg_edits_with - avg_edits_without) / avg_edits_without * 100
            insights.append(ClaudeMdInsight(
                metric="Edits per file",
                with_reads=avg_edits_with,
                without_reads=avg_edits_without,
                delta_pct=delta,
                recommendation=(
                    f"Sessions with CLAUDE.md require {abs(delta):.0f}% "
                    f"{'fewer' if delta < 0 else 'more'} edits per file."
                ),
            ))

    # Suggest files to document in CLAUDE.md
    # Files read frequently across many sessions are candidates
    suggestions: list[FrequentlyReadFile] = []
    for fp, counts in file_read_counts.items():
        total = counts["total"]
        sess = counts["sessions"]
        if total >= 10 and sess >= 3:
            # Skip CLAUDE.md itself and memory files
            if "CLAUDE.md" in fp or "memory" in fp.lower() or "MEMORY" in fp:
                continue
            suggestions.append(FrequentlyReadFile(
                path=fp,
                total_reads=total,
                session_count=sess,
                avg_reads_per_session=total / sess,
            ))
    suggestions.sort(key=lambda s: -s.total_reads)

    return ClaudeMdReport(
        projects_with_claude_md=projects_with,
        projects_without=projects_without,
        insights=insights,
        suggested_additions=suggestions[:10],
    )


def _extract_session_metrics(fpath: Path) -> dict[str, Any] | None:
    """Extract metrics from a session for CLAUDE.md comparison."""
    calls = 0
    input_tokens = 0
    output_tokens = 0
    edits: dict[str, int] = Counter()
    reads: dict[str, int] = Counter()
    claude_md_reads = 0
    corrections = 0
    total_user = 0

    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line.strip())
                msg_type = obj.get("type")

                if msg_type == "user":
                    total_user += 1
                    msg = obj.get("message", {})
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            if re.search(r"\b(no[,.]|wrong|undo|revert|actually[,.])\b", content, re.I):
                                corrections += 1
                    continue

                if msg_type != "assistant":
                    continue
                msg = obj.get("message", {})
                if not isinstance(msg, dict) or msg.get("type") != "message":
                    continue

                calls += 1
                usage = msg.get("usage", {})
                input_tokens += (usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                output_tokens += usage.get("output_tokens") or 0

                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name", "")
                    fp = block.get("input", {}).get("file_path", "") if isinstance(block.get("input"), dict) else ""

                    if name == "Read" and fp:
                        reads[fp] += 1
                        if "CLAUDE.md" in fp:
                            claude_md_reads += 1
                    elif name == "Edit" and fp:
                        edits[fp] += 1
    except (json.JSONDecodeError, OSError):
        return None

    if calls < 3:
        return None

    files_edited = len(edits)
    total_edits = sum(edits.values())

    return {
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "token_ratio": output_tokens / input_tokens if input_tokens > 0 else 0,
        "correction_rate": corrections / total_user if total_user > 0 else 0,
        "avg_edits_per_file": total_edits / files_edited if files_edited > 0 else 0,
        "claude_md_reads": claude_md_reads,
        "file_reads": dict(reads),
    }


def _analyze_permissions(debug_dir: Path | None = None) -> PermissionInsight | None:
    """Analyze permission rules from debug logs."""
    if debug_dir is None:
        debug_dir = Path.home() / ".claude" / "debug"

    if not debug_dir.exists():
        return None

    # Get the most recent debug log
    logs = sorted(debug_dir.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not logs:
        return None

    from ai_trace_auditor.insights.debug_parser import parse_debug_log
    latest = parse_debug_log(logs[0])

    total = latest.allow_rules_count
    sources = latest.permission_sources

    if total == 0:
        return None

    # Estimate unused rules
    if total > 100:
        unused_est = "Many rules (100+). Likely 30-50% are unused WebFetch domain allowances accumulated over time."
        rec = "Run `aitrace health` to see which tools actually fail. Remove WebFetch domains you no longer visit."
    elif total > 50:
        unused_est = "Moderate rule set. Some accumulated WebFetch/Bash allowances may be stale."
        rec = "Review your .claude/settings.json for rules you added months ago."
    else:
        unused_est = "Lean rule set."
        rec = "Your permission configuration is focused. No action needed."

    return PermissionInsight(
        total_rules=total,
        rules_by_source=sources,
        unused_estimate=unused_est,
        recommendation=rec,
    )
