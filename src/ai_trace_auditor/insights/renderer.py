"""Rich terminal renderer for usage insights."""

from __future__ import annotations

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ai_trace_auditor.insights.agents import AgentReport
from ai_trace_auditor.insights.analyzer import InsightsReport
from ai_trace_auditor.insights.health import SessionHealth
from ai_trace_auditor.insights.workflow import WorkflowReport


def render_insights(
    report: InsightsReport,
    console: Console | None = None,
    tz_label: str = "UTC",
) -> None:
    """Render an InsightsReport to the terminal with Rich formatting."""
    if console is None:
        console = Console()

    _render_header(report, console)
    _render_cost(report, console)
    _render_sessions(report, console)
    _render_tools(report, console)
    _render_files(report, console)
    _render_activity(report, console, tz_label)
    _render_bash(report, console)
    _render_patterns(report, console)


def _render_header(report: InsightsReport, console: Console) -> None:
    console.print()
    console.print(Panel(
        f"[bold]Claude Code Usage Insights[/bold]\n"
        f"{report.date_range[0]} to {report.date_range[1]}  ·  "
        f"{report.total_sessions} sessions  ·  "
        f"{report.total_ai_calls:,} AI calls",
        border_style="blue",
    ))


def _render_cost(report: InsightsReport, console: Console) -> None:
    c = report.cost
    table = Table(title="Token Usage & Cost", border_style="dim")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total input tokens", f"{c.total_input_tokens:,} ({c.total_input_tokens/1e6:.1f}M)")
    table.add_row("  Cache reads", f"{c.cache_read_tokens:,} ({c.cache_read_pct:.1f}%)")
    table.add_row("  Cache creates", f"{c.cache_create_tokens:,}")
    table.add_row("  Fresh input", f"{c.fresh_input_tokens:,}")
    table.add_row("Total output tokens", f"{c.total_output_tokens:,} ({c.total_output_tokens/1e6:.1f}M)")
    table.add_row("", "")
    table.add_row("Est. cost (no cache)", f"[dim]${c.est_cost_no_cache:,.0f}[/dim]")
    table.add_row("Est. cost (with cache)", f"[green]${c.est_cost_with_cache:,.0f}[/green]")
    savings = c.est_cost_no_cache - c.est_cost_with_cache
    if savings > 0:
        table.add_row("Cache savings", f"[green]${savings:,.0f}[/green]")

    console.print(table)
    console.print()


def _render_sessions(report: InsightsReport, console: Console) -> None:
    table = Table(title=f"Top Sessions (of {report.total_sessions})", border_style="dim")
    table.add_column("Date")
    table.add_column("AI Calls", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Hours", justify="right")
    table.add_column("Tools", justify="right")
    table.add_column("Top Tool")

    for s in report.sessions[:10]:
        table.add_row(
            s.date,
            f"{s.ai_calls:,}",
            f"{s.input_tokens/1e6:.1f}M",
            f"{s.output_tokens/1000:.1f}K",
            f"{s.duration_hours:.1f}h",
            f"{s.tool_calls:,}",
            s.top_tool,
        )

    console.print(table)
    console.print()


def _render_tools(report: InsightsReport, console: Console) -> None:
    table = Table(title="Tool Usage", border_style="dim")
    table.add_column("Tool")
    table.add_column("Calls", justify="right")
    table.add_column("%", justify="right")
    table.add_column("", width=30)

    max_count = report.tool_usage[0].count if report.tool_usage else 1
    for t in report.tool_usage[:12]:
        bar_len = int(t.count / max_count * 25)
        bar = "█" * bar_len
        table.add_row(t.name, f"{t.count:,}", f"{t.pct:.1f}", f"[blue]{bar}[/blue]")

    console.print(table)
    console.print()


def _render_files(report: InsightsReport, console: Console) -> None:
    table = Table(title="Most Edited Files", border_style="dim")
    table.add_column("File")
    table.add_column("Edits", justify="right")
    table.add_column("Reads", justify="right")
    table.add_column("Writes", justify="right")

    for h in report.file_hotspots_edit[:10]:
        if h.edits == 0:
            continue
        # Truncate long paths
        path = h.path
        if len(path) > 60:
            path = "..." + path[-57:]
        table.add_row(path, str(h.edits), str(h.reads), str(h.writes))

    console.print(table)
    console.print()


def _render_activity(report: InsightsReport, console: Console, tz_label: str = "UTC") -> None:
    console.print(f"[bold]Hourly Activity ({tz_label})[/bold]")

    max_count = max(b.count for b in report.hourly_activity) if report.hourly_activity else 1
    for b in report.hourly_activity:
        bar_len = int(b.count / max_count * 40) if max_count > 0 else 0
        bar = "█" * bar_len
        count_str = f"{b.count:>5}"
        if b.count == max_count and b.count > 0:
            console.print(f"  {b.hour:02d}:00  {count_str}  [bold green]{bar}[/bold green] ← peak")
        elif b.count > 0:
            console.print(f"  {b.hour:02d}:00  {count_str}  [blue]{bar}[/blue]")
        else:
            console.print(f"  {b.hour:02d}:00  {count_str}")

    console.print()


def _render_bash(report: InsightsReport, console: Console) -> None:
    if not report.bash_commands:
        return

    table = Table(title="Top Bash Commands", border_style="dim")
    table.add_column("Command")
    table.add_column("Count", justify="right")

    for cmd, count in report.bash_commands[:10]:
        table.add_row(cmd, f"{count:,}")

    console.print(table)
    console.print()


def _render_patterns(report: InsightsReport, console: Console) -> None:
    if not report.workflow_patterns:
        return

    console.print("[bold]Workflow Insights[/bold]")
    console.print()

    for p in report.workflow_patterns:
        title = f"[bold]{p.name}[/bold]: {p.value}"
        body = p.description
        if p.recommendation:
            body += f"\n[dim italic]→ {p.recommendation}[/dim italic]"
        console.print(Panel(body, title=title, border_style="cyan", width=80))


def render_health_summary(
    healths: list[SessionHealth],
    aggregate: dict,
    console: Console | None = None,
) -> None:
    """Render session health scores."""
    if console is None:
        console = Console()

    if not healths:
        console.print("[yellow]No session health data available[/yellow]")
        return

    avg = aggregate.get("average_score", 0)
    color = "green" if avg >= 75 else "yellow" if avg >= 50 else "red"
    console.print()
    console.print(Panel(
        f"[bold]Session Health Report[/bold]\n"
        f"{aggregate['sessions_analyzed']} sessions analyzed  ·  "
        f"Average score: [{color}]{avg:.0f}/100[/{color}]",
        border_style=color,
    ))

    grades = aggregate.get("grade_distribution", {})
    if grades:
        parts = []
        for g in ("A", "B", "C", "D", "F"):
            c = grades.get(g, 0)
            if c == 0:
                continue
            gc = "green" if g == "A" else "cyan" if g == "B" else "yellow" if g == "C" else "red"
            parts.append(f"[{gc}]{g}: {c}[/{gc}]")
        console.print(f"  Grades: {'  '.join(parts)}")
        console.print()

    # Per-session table (worst first)
    table = Table(title="Session Health Scores", border_style="dim")
    table.add_column("Session ID", max_width=14)
    table.add_column("Score", justify="right")
    table.add_column("Grade")
    table.add_column("Tools", justify="right")
    table.add_column("Stream", justify="right")
    table.add_column("API", justify="right")
    table.add_column("Boot", justify="right")
    table.add_column("MCP", justify="right")
    table.add_column("Issues")

    for h in sorted(healths, key=lambda x: x.score)[:15]:
        sc = "green" if h.score >= 75 else "yellow" if h.score >= 50 else "red"
        issues = []
        if h.tool_error_count:
            issues.append(f"{h.tool_error_count} tool err")
        if h.stall_count:
            issues.append(f"{h.stall_count} stalls")
        if h.api_error_count:
            issues.append(f"{h.api_error_count} API err")
        table.add_row(
            h.session_id[:12], f"[{sc}]{h.score}[/{sc}]", h.grade,
            str(h.tool_reliability), str(h.streaming_stability),
            str(h.api_reliability), str(h.startup_speed), str(h.mcp_health),
            ", ".join(issues) if issues else "[green]clean[/green]",
        )
    console.print(table)

    # Friction totals
    friction = aggregate.get("friction_totals", {})
    if friction:
        console.print()
        console.print("[bold]Friction Points (all sessions)[/bold]")
        ft = Table(border_style="dim")
        ft.add_column("Category")
        ft.add_column("Total", justify="right")
        labels = {
            "tool_error": "Tool failures",
            "streaming_stall": "Streaming stalls",
            "api_error": "API errors",
            "mcp_failure": "MCP connection failures",
            "startup": "Slow startups",
        }
        for cat, count in sorted(friction.items(), key=lambda x: -x[1]):
            ft.add_row(labels.get(cat, cat), str(count))
        console.print(ft)

    # Top issues from worst sessions
    worst = sorted(healths, key=lambda x: x.score)[:3]
    if worst and worst[0].friction_points:
        console.print()
        console.print("[bold]Top Issues (from worst sessions)[/bold]")
        seen: set[str] = set()
        for h in worst:
            for fp in h.friction_points[:3]:
                if fp.description in seen:
                    continue
                seen.add(fp.description)
                sc = "red" if fp.severity == "high" else "yellow" if fp.severity == "medium" else "dim"
                console.print(Panel(
                    f"{fp.description}\n[dim italic]→ {fp.recommendation}[/dim italic]",
                    title=f"[{sc}]{fp.severity.upper()}[/{sc}]",
                    border_style=sc, width=80,
                ))
                if len(seen) >= 5:
                    break
            if len(seen) >= 5:
                break
    console.print()


def render_workflow(report: WorkflowReport, console: Console | None = None) -> None:
    """Render workflow optimization report."""
    if console is None:
        console = Console()

    console.print()
    console.print(Panel(
        f"[bold]Workflow Optimization Report[/bold]\n"
        f"{len(report.sessions)} sessions analyzed",
        border_style="magenta",
    ))

    # Efficiency overview
    table = Table(title="Efficiency Metrics", border_style="dim")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Assessment")

    tr = report.avg_token_ratio
    tr_color = "green" if tr > 0.003 else "yellow" if tr > 0.001 else "red"
    table.add_row(
        "Token efficiency",
        f"{tr:.4f}",
        f"[{tr_color}]{'Good' if tr > 0.003 else 'Low' if tr > 0.001 else 'Very low'}[/{tr_color}] (output/input ratio)",
    )

    ts = report.avg_tool_success
    ts_color = "green" if ts > 0.95 else "yellow" if ts > 0.85 else "red"
    table.add_row(
        "Tool success rate",
        f"{ts:.1%}",
        f"[{ts_color}]{'Excellent' if ts > 0.95 else 'Good' if ts > 0.85 else 'Needs attention'}[/{ts_color}]",
    )

    ae = report.avg_edits_per_file
    ae_color = "green" if ae < 3 else "yellow" if ae < 6 else "red"
    table.add_row(
        "Avg edits/file",
        f"{ae:.1f}",
        f"[{ae_color}]{'Focused' if ae < 3 else 'Iterative' if ae < 6 else 'High churn'}[/{ae_color}]",
    )

    console.print(table)
    console.print()

    # Prompt patterns
    ps = report.prompt_stats
    if ps.total_prompts > 0:
        table = Table(title="Prompt Patterns", border_style="dim")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Total prompts", f"{ps.total_prompts:,}")
        table.add_row("Avg length", f"{ps.avg_length_chars:.0f} chars")
        table.add_row("Short (< 50 chars)", f"{ps.short_prompts} ({ps.short_prompts/ps.total_prompts*100:.0f}%)")
        table.add_row("Medium (50-200)", f"{ps.medium_prompts} ({ps.medium_prompts/ps.total_prompts*100:.0f}%)")
        table.add_row("Long (200+)", f"{ps.long_prompts} ({ps.long_prompts/ps.total_prompts*100:.0f}%)")
        table.add_row("Questions (?)", f"{ps.question_count} ({ps.question_ratio:.0%})")
        table.add_row("Commands", f"{ps.command_count}")
        cr_color = "green" if ps.correction_ratio < 0.05 else "yellow" if ps.correction_ratio < 0.1 else "red"
        table.add_row("Corrections", f"[{cr_color}]{ps.correction_count} ({ps.correction_ratio:.1%})[/{cr_color}]")

        console.print(table)
        console.print()

    # Session length analysis
    if report.length_buckets:
        table = Table(title="Performance by Session Length", border_style="dim")
        table.add_column("Duration")
        table.add_column("Sessions", justify="right")
        table.add_column("Token Eff.", justify="right")
        table.add_column("Tool Success", justify="right")
        table.add_column("Edits/File", justify="right")
        table.add_column("Corrections", justify="right")

        for b in report.length_buckets:
            is_optimal = b.label == report.optimal_length
            prefix = "[bold green]" if is_optimal else ""
            suffix = " ★[/bold green]" if is_optimal else ""
            table.add_row(
                f"{prefix}{b.label}{suffix}",
                str(b.session_count),
                f"{b.avg_token_ratio:.4f}",
                f"{b.avg_tool_success:.1%}",
                f"{b.avg_edits_per_file:.1f}",
                f"{b.avg_corrections:.1f}",
            )

        console.print(table)
        console.print()

    # File churn
    if report.high_churn_files:
        table = Table(title="High-Churn Files", border_style="dim")
        table.add_column("File", max_width=50)
        table.add_column("Edits", justify="right")
        table.add_column("Sessions", justify="right")
        table.add_column("Avg/Session", justify="right")
        table.add_column("Max", justify="right")
        table.add_column("Reads", justify="right")

        for f in report.high_churn_files[:10]:
            path = f.path
            if len(path) > 50:
                path = "..." + path[-47:]
            table.add_row(
                path, str(f.total_edits), str(f.session_count),
                f"{f.avg_edits_per_session:.1f}", str(f.max_edits_in_session),
                str(f.total_reads),
            )

        console.print(table)
        console.print()

    # Recommendations
    if report.recommendations:
        console.print("[bold]Recommendations[/bold]")
        console.print()
        for i, rec in enumerate(report.recommendations, 1):
            console.print(Panel(rec, title=f"[bold]#{i}[/bold]", border_style="magenta", width=80))

    console.print()


def render_agents(report: AgentReport, console: Console | None = None) -> None:
    """Render multi-agent intelligence report."""
    if console is None:
        console = Console()

    a = report.agent_stats
    console.print()
    console.print(Panel(
        f"[bold]Multi-Agent Intelligence Report[/bold]\n"
        f"{a.total_calls} agent delegations across {a.total_sessions} sessions  ·  "
        f"{a.sessions_using_agents} sessions used agents ({a.agent_adoption_rate:.0%})",
        border_style="blue",
    ))

    # Agent type breakdown
    if a.by_type:
        table = Table(title="Agent Types", border_style="dim")
        table.add_column("Type")
        table.add_column("Calls", justify="right")
        table.add_column("%", justify="right")
        table.add_column("", width=25)

        max_count = a.by_type[0][1] if a.by_type else 1
        for t, count in a.by_type:
            pct = count / a.total_calls * 100 if a.total_calls > 0 else 0
            bar = "█" * int(count / max_count * 20)
            table.add_row(t or "(default)", f"{count}", f"{pct:.0f}", f"[blue]{bar}[/blue]")

        console.print(table)

    # Agent usage patterns
    console.print()
    table = Table(title="Delegation Patterns", border_style="dim")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Foreground agents", str(a.foreground_count))
    table.add_row("Background agents", str(a.background_count))
    bg_pct = a.background_count / a.total_calls * 100 if a.total_calls > 0 else 0
    table.add_row("Background rate", f"{bg_pct:.0f}%")
    table.add_row("Avg prompt length", f"{a.avg_prompt_length:.0f} chars")
    table.add_row("Longest prompt", f"{a.longest_prompt:,} chars")

    console.print(table)

    # Plans
    p = report.plan_stats
    if p.total_plans > 0:
        console.print()
        table = Table(title=f"Implementation Plans ({p.total_plans})", border_style="dim")
        table.add_column("Plan")
        table.add_column("Steps", justify="right")
        table.add_column("Complexity")

        for plan in p.plans:
            c_color = "green" if plan.estimated_complexity == "simple" else "yellow" if plan.estimated_complexity == "moderate" else "red"
            table.add_row(
                plan.title[:50],
                str(plan.step_count),
                f"[{c_color}]{plan.estimated_complexity}[/{c_color}]",
            )

        console.print(table)

        # Plan summary
        console.print()
        dist = p.complexity_distribution
        parts = []
        for level in ("simple", "moderate", "complex"):
            c = dist.get(level, 0)
            if c > 0:
                color = "green" if level == "simple" else "yellow" if level == "moderate" else "red"
                parts.append(f"[{color}]{level}: {c}[/{color}]")
        console.print(f"  Complexity: {'  '.join(parts)}  ·  Avg steps: {p.avg_steps:.1f}")

    # Teams
    if report.teams:
        console.print()
        for team in report.teams:
            console.print(Panel(
                f"[dim]{team.description}[/dim]\n\n"
                f"Members: {', '.join(m.name for m in team.members)}  ·  "
                f"Messages: {team.total_messages}",
                title=f"[bold]Team: {team.name}[/bold]",
                border_style="cyan",
                width=80,
            ))

            if team.inboxes:
                table = Table(border_style="dim")
                table.add_column("Agent")
                table.add_column("Messages", justify="right")
                table.add_column("From")

                for inbox in team.inboxes:
                    senders = ", ".join(f"{s} ({c})" for s, c in inbox.senders.items())
                    table.add_row(inbox.agent_name, str(inbox.message_count), senders or "-")

                console.print(table)

    console.print()
