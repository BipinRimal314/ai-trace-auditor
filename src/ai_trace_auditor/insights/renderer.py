"""Rich terminal renderer for usage insights."""

from __future__ import annotations

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ai_trace_auditor.insights.analyzer import InsightsReport


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

    console.print()
