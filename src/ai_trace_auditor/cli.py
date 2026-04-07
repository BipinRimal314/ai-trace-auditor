"""CLI interface for AI Trace Auditor."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

import ai_trace_auditor
from ai_trace_auditor.analysis.engine import ComplianceAnalyzer
from ai_trace_auditor.ingest.detect import ingest_directory, ingest_file
from ai_trace_auditor.models.gap import GapReport
from ai_trace_auditor.regulations.registry import RequirementRegistry
from ai_trace_auditor.config import load_config
from ai_trace_auditor.reports.json_report import JSONReporter
from ai_trace_auditor.reports.markdown import MarkdownReporter

app = typer.Typer(
    name="aitrace",
    help="Audit LLM traces against regulatory compliance requirements.",
    no_args_is_help=True,
)
console = Console(stderr=True)
stdout_console = Console()


def _load_traces(path: Path, format_hint: str) -> list:
    """Load traces from a file or directory."""
    if path.is_dir():
        return ingest_directory(path, format_hint)
    return ingest_file(path, format_hint)


def _print_trace_summary(traces: list) -> None:
    """Print a Rich summary table of ingested traces."""
    table = Table(title="Trace Summary")
    table.add_column("Traces", justify="right")
    table.add_column("Spans", justify="right")
    table.add_column("Providers")
    table.add_column("Models")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")

    total_spans = sum(t.span_count for t in traces)
    all_providers = set()
    all_models = set()
    total_input = 0
    total_output = 0

    for t in traces:
        all_providers.update(t.providers)
        all_models.update(t.models)
        total_input += t.total_input_tokens
        total_output += t.total_output_tokens

    table.add_row(
        str(len(traces)),
        str(total_spans),
        ", ".join(sorted(all_providers)) or "-",
        ", ".join(sorted(all_models)) or "-",
        f"{total_input:,}" if total_input else "-",
        f"{total_output:,}" if total_output else "-",
    )
    console.print(table)


def _print_report_summary(report: GapReport) -> None:
    """Print a Rich summary of the compliance report."""
    score = report.overall_score * 100
    color = "green" if score >= 90 else "yellow" if score >= 50 else "red"

    console.print()
    console.print(f"[bold]Overall Compliance Score:[/bold] [{color}]{score:.1f}%[/{color}]")
    console.print()

    table = Table(title="Results by Status")
    table.add_column("Status")
    table.add_column("Count", justify="right")

    if report.summary.satisfied:
        table.add_row("[green]Satisfied[/green]", str(report.summary.satisfied))
    if report.summary.partial:
        table.add_row("[yellow]Partial[/yellow]", str(report.summary.partial))
    if report.summary.missing:
        table.add_row("[red]Missing[/red]", str(report.summary.missing))
    if report.summary.not_applicable:
        table.add_row("[dim]N/A[/dim]", str(report.summary.not_applicable))

    console.print(table)

    if report.tiered_scores:
        console.print()
        tier_table = Table(title="Tiered Compliance Scores")
        tier_table.add_column("Tier")
        tier_table.add_column("Score", justify="right")
        tier_table.add_column("Satisfied", justify="right")
        tier_table.add_column("Gaps", justify="right")
        for ts in report.tiered_scores:
            pct = ts.score * 100
            tc = "green" if pct >= 90 else "yellow" if pct >= 50 else "red"
            tier_table.add_row(
                ts.label,
                f"[{tc}]{pct:.0f}%[/{tc}]",
                str(ts.satisfied),
                str(ts.gaps),
            )
        console.print(tier_table)

    if report.summary.top_gaps:
        console.print()
        console.print("[bold]Top gaps:[/bold]")
        for i, gap in enumerate(report.summary.top_gaps, 1):
            console.print(f"  {i}. {gap}")

    # Multi-agent per-agent scores
    if report.agent_scores:
        console.print()
        agent_table = Table(title="Per-Agent Compliance Scores")
        agent_table.add_column("Agent ID")
        agent_table.add_column("Score", justify="right")
        for agent_id, score in sorted(report.agent_scores.items()):
            pct = score * 100
            color = "green" if pct >= 90 else "yellow" if pct >= 50 else "red"
            agent_table.add_row(agent_id, f"[{color}]{pct:.1f}%[/{color}]")
        console.print(agent_table)


@app.command()
def audit(
    path: Annotated[Path, typer.Argument(help="Trace file or directory to audit")],
    regulation: Annotated[
        Optional[list[str]],
        typer.Option("--regulation", "-r", help="Filter to specific regulation"),
    ] = None,
    risk_level: Annotated[
        str, typer.Option("--risk-level", help="Risk classification")
    ] = "high_risk",
    format_hint: Annotated[
        str, typer.Option("--format", "-f", help="Input format: auto, otel, langfuse, raw")
    ] = "auto",
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Output file path")
    ] = None,
    report_format: Annotated[
        str,
        typer.Option("--report-format", help="Output format: markdown, json, both"),
    ] = "markdown",
    show_dag: Annotated[
        bool,
        typer.Option("--show-dag", help="Output Mermaid DAG visualization for multi-agent traces"),
    ] = False,
) -> None:
    """Audit LLM traces against regulatory compliance requirements."""
    if not path.exists():
        console.print(f"[red]Error:[/red] {path} does not exist")
        raise typer.Exit(code=2)

    # Load project config (CLI flags override config values)
    cfg = load_config(path.parent if path.is_file() else path)
    if cfg is not None:
        console.print("[dim]Loaded config from .aitrace.toml[/dim]")
        if risk_level == "high_risk" and cfg.risk_level != "high_risk":
            risk_level = cfg.risk_level
        if report_format == "markdown" and cfg.report_format != "markdown":
            report_format = cfg.report_format

    # Load traces
    console.print(f"Loading traces from [bold]{path}[/bold]...")
    try:
        traces = _load_traces(path, format_hint)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=2) from e

    if not traces:
        console.print("[yellow]Warning:[/yellow] No traces found")
        raise typer.Exit(code=0)

    _print_trace_summary(traces)

    # Multi-agent detection
    multi_agent_traces = [t for t in traces if t.is_multi_agent]
    if multi_agent_traces:
        total_agents = set()
        for t in multi_agent_traces:
            total_agents.update(t.agents)
        console.print(
            f"[bold cyan]Multi-agent system detected:[/bold cyan] "
            f"{len(total_agents)} agents across "
            f"{sum(t.span_count for t in multi_agent_traces)} spans"
        )

    # Load requirements
    registry = RequirementRegistry()
    registry.load()
    console.print(
        f"Loaded [bold]{registry.count}[/bold] requirements "
        f"from {', '.join(registry.regulations)}"
    )

    # Run analysis
    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(
        traces=traces,
        regulations=regulation,
        risk_level=risk_level,
        trace_source=str(path),
    )

    # Output report
    if report_format in ("markdown", "both"):
        md = MarkdownReporter().render(report)
        if output:
            md_path = output if report_format == "markdown" else output.with_suffix(".md")
            md_path.write_text(md, encoding="utf-8")
            console.print(f"Markdown report written to [bold]{md_path}[/bold]")
        else:
            stdout_console.print(md)

    if report_format in ("json", "both"):
        jr = JSONReporter().render(report)
        if output:
            json_path = output if report_format == "json" else output.with_suffix(".json")
            json_path.write_text(jr, encoding="utf-8")
            console.print(f"JSON report written to [bold]{json_path}[/bold]")
        else:
            stdout_console.print(jr)

    _print_report_summary(report)

    # Multi-agent DAG visualization
    if show_dag and multi_agent_traces:
        from ai_trace_auditor.analysis.dag import build_adjacency_list
        from ai_trace_auditor.analysis.dag_mermaid import generate_agent_dag_mermaid

        console.print()
        console.print("[bold]Agent Execution DAG:[/bold]")
        for trace in multi_agent_traces:
            if not trace.dag_adjacency_list:
                trace.dag_adjacency_list = build_adjacency_list(trace)
            mermaid = generate_agent_dag_mermaid(trace, report.agent_scores)
            if mermaid:
                console.print(f"\n```mermaid\n{mermaid}\n```")

    # Exit code: 0 = all satisfied, 1 = gaps found
    has_gaps = report.summary.missing > 0 or report.summary.partial > 0
    raise typer.Exit(code=1 if has_gaps else 0)


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="Trace file to ingest")],
    format_hint: Annotated[
        str, typer.Option("--format", "-f", help="Input format: auto, otel, langfuse, raw")
    ] = "auto",
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Write normalized traces as JSON")
    ] = None,
    summary: Annotated[
        bool, typer.Option("--summary", help="Print summary table only")
    ] = False,
) -> None:
    """Ingest and normalize trace files."""
    if not path.exists():
        console.print(f"[red]Error:[/red] {path} does not exist")
        raise typer.Exit(code=2)

    try:
        traces = _load_traces(path, format_hint)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=2) from e

    _print_trace_summary(traces)

    if not summary and output:
        import json

        data = [t.model_dump(mode="json") for t in traces]
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        console.print(f"Normalized traces written to [bold]{output}[/bold]")


@app.command(name="requirements")
def list_requirements(
    regulation: Annotated[
        Optional[str], typer.Option("--regulation", "-r", help="Filter by regulation")
    ] = None,
    severity: Annotated[
        Optional[str], typer.Option("--severity", help="Filter by severity")
    ] = None,
    show_id: Annotated[
        Optional[str], typer.Option("--show", help="Show details for a specific requirement ID")
    ] = None,
) -> None:
    """List or inspect regulatory requirements."""
    registry = RequirementRegistry()
    registry.load()

    if show_id:
        req = registry.get_by_id(show_id)
        if not req:
            console.print(f"[red]Error:[/red] Requirement '{show_id}' not found")
            raise typer.Exit(code=2)

        console.print(f"\n[bold]{req.id}:[/bold] {req.title}")
        console.print(f"[dim]Regulation:[/dim] {req.regulation} {req.article}")
        if req.legal_text:
            console.print(f"[dim]Legal text:[/dim] {req.legal_text}")
        console.print(f"[dim]Severity:[/dim] {req.severity}")
        if req.framework_nature:
            console.print(f"[dim]Framework:[/dim] {req.framework_nature}")
        if req.check_type:
            console.print(f"[dim]Check type:[/dim] {req.check_type}")
        if req.applies_to:
            console.print(f"[dim]Applies to:[/dim] {', '.join(req.applies_to)}")
        verified = "Yes" if req.verified_against_primary else "No"
        console.print(f"[dim]Verified against primary source:[/dim] {verified}")
        console.print(f"\n{req.description}\n")

        if req.evidence_fields:
            table = Table(title="Evidence Fields")
            table.add_column("Field Path")
            table.add_column("Required")
            table.add_column("Check")
            table.add_column("Description")

            for ef in req.evidence_fields:
                table.add_row(
                    f"`{ef.field_path}`",
                    "Yes" if ef.required else "No",
                    ef.check_type,
                    ef.description,
                )
            console.print(table)
        return

    requirements = registry.get_all()
    if regulation:
        requirements = [r for r in requirements if r.regulation == regulation]
    if severity:
        requirements = [r for r in requirements if r.severity == severity]

    if not requirements:
        console.print("[yellow]No requirements found matching filters[/yellow]")
        return

    table = Table(title=f"Requirements ({len(requirements)})")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Regulation")
    table.add_column("Severity")
    table.add_column("Fields", justify="right")

    for req in requirements:
        table.add_row(
            req.id,
            req.title,
            f"{req.regulation} {req.article}",
            req.severity,
            str(len(req.evidence_fields)),
        )
    console.print(table)


@app.command()
def insights(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Path to a specific project traces directory"),
    ] = None,
    project: Annotated[
        Optional[str],
        typer.Option("--project", "-p", help="Filter to a project by name (partial match)"),
    ] = None,
    since: Annotated[
        Optional[str],
        typer.Option("--since", help="Only include sessions after this date (YYYY-MM-DD)"),
    ] = None,
    last: Annotated[
        Optional[str],
        typer.Option("--last", help="Time window: 7d, 30d, 90d"),
    ] = None,
    timezone: Annotated[
        Optional[str],
        typer.Option("--timezone", "--tz", help="Timezone offset (e.g., +5:45, -8, Asia/Kathmandu)"),
    ] = None,
    json_output: Annotated[
        Optional[Path], typer.Option("--json", help="Export insights as JSON")
    ] = None,
    summary_only: Annotated[
        bool, typer.Option("--summary", help="Show cross-project summary table only")
    ] = False,
) -> None:
    """Analyze Claude Code usage patterns and workflow insights.

    With no arguments, shows a cross-project summary of all discovered projects.
    Use --project to drill into a specific project, or provide a path directly.
    """
    from ai_trace_auditor.insights.analyzer import analyze_claude_code_dir
    from ai_trace_auditor.insights.projects import (
        discover_projects,
        get_strip_prefix,
    )
    from ai_trace_auditor.insights.renderer import render_insights

    # Parse date filters
    since_dt, until_dt = _parse_date_filters(since, last)

    # Parse timezone
    tz_offset = _parse_timezone(timezone)
    tz_label = timezone or "UTC"
    if tz_offset == 0.0 and timezone is None:
        tz_label = "UTC"

    if path is not None:
        # Direct path mode
        if not path.exists() or not path.is_dir():
            console.print(f"[red]Error:[/red] {path} is not a valid directory")
            raise typer.Exit(code=2)

        try:
            report = analyze_claude_code_dir(
                path, since=since_dt, until=until_dt, tz_offset_hours=tz_offset,
            )
            render_insights(report, console, tz_label=tz_label)
            if json_output:
                _export_insights_json(report, json_output, path.name)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=2) from e
        return

    # Auto-discover projects
    projects = discover_projects()
    if not projects:
        console.print("[red]Error:[/red] No Claude Code traces found in ~/.claude/projects/")
        raise typer.Exit(code=2)

    # Filter by project name if specified
    if project:
        query = project.lower()
        projects = [p for p in projects if query in p.display_name.lower()]
        if not projects:
            console.print(f"[yellow]No projects matching '{project}'[/yellow]")
            # Show available projects
            all_projects = discover_projects()
            console.print("\nAvailable projects:")
            for p in all_projects[:20]:
                console.print(f"  {p.display_name} ({p.session_count} sessions)")
            raise typer.Exit(code=0)

    # If summary only, or multiple projects without filter, show summary table
    if summary_only or (len(projects) > 1 and project is None):
        _render_project_summary(projects, console)

        if len(projects) > 1 and project is None:
            console.print(
                "\n[dim]Use --project <name> to drill into a specific project, "
                "or --summary for just this table.[/dim]"
            )
        if json_output and summary_only:
            _export_summary_json(projects, json_output)
        return

    # Single project (filtered) — show full insights
    for proj in projects:
        console.print(f"\n[bold blue]Project:[/bold blue] {proj.display_name}")
        console.print(f"[dim]{proj.cwd}[/dim]")

        try:
            strip = get_strip_prefix(proj)
            report = analyze_claude_code_dir(
                proj.dir_path,
                strip_prefix=strip,
                since=since_dt,
                until=until_dt,
                tz_offset_hours=tz_offset,
            )
            render_insights(report, console, tz_label=tz_label)

            if json_output:
                _export_insights_json(report, json_output, proj.display_name)

        except ValueError as e:
            console.print(f"  [dim]{e}[/dim]")


def _parse_date_filters(
    since: str | None, last: str | None
) -> tuple[datetime | None, datetime | None]:
    """Parse --since and --last into datetime bounds."""
    from datetime import datetime, timedelta, timezone

    since_dt = None
    until_dt = None

    if last:
        last = last.lower().strip()
        now = datetime.now(timezone.utc)
        if last.endswith("d"):
            days = int(last[:-1])
            since_dt = now - timedelta(days=days)
        elif last.endswith("w"):
            weeks = int(last[:-1])
            since_dt = now - timedelta(weeks=weeks)
        elif last.endswith("m"):
            months = int(last[:-1])
            since_dt = now - timedelta(days=months * 30)
    elif since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return since_dt, until_dt


def _parse_timezone(tz_str: str | None) -> float:
    """Parse timezone string to UTC offset in hours."""
    if tz_str is None:
        return 0.0

    # Common named timezones
    named = {
        "Asia/Kathmandu": 5.75,
        "Asia/Kolkata": 5.5,
        "US/Pacific": -8,
        "US/Eastern": -5,
        "US/Central": -6,
        "US/Mountain": -7,
        "Europe/London": 0,
        "Europe/Berlin": 1,
        "Europe/Paris": 1,
        "Asia/Tokyo": 9,
        "Asia/Shanghai": 8,
        "Australia/Sydney": 11,
        "UTC": 0,
    }

    if tz_str in named:
        return named[tz_str]

    # Parse offset format: +5:45, -8, +9
    try:
        tz_str = tz_str.strip()
        if ":" in tz_str:
            parts = tz_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1])
            sign = -1 if hours < 0 else 1
            return hours + sign * minutes / 60
        return float(tz_str)
    except (ValueError, IndexError):
        return 0.0


def _render_project_summary(projects: list, console: Console) -> None:
    """Render a cross-project summary table."""
    from ai_trace_auditor.insights.analyzer import analyze_claude_code_dir

    table = Table(title="Claude Code Projects", border_style="dim")
    table.add_column("Project", max_width=30)
    table.add_column("Sessions", justify="right")
    table.add_column("AI Calls", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Est. Cost", justify="right")
    table.add_column("Active")

    total_calls = 0
    total_cost = 0.0

    for proj in projects:
        try:
            report = analyze_claude_code_dir(proj.dir_path)
            calls = report.total_ai_calls
            inp_m = report.total_input_tokens / 1e6
            out_k = report.total_output_tokens / 1000
            cost = report.cost.est_cost_with_cache
            dates = f"{report.date_range[0]} → {report.date_range[1]}"

            total_calls += calls
            total_cost += cost

            table.add_row(
                proj.display_name,
                str(report.total_sessions),
                f"{calls:,}",
                f"{inp_m:.1f}M",
                f"{out_k:.0f}K",
                f"${cost:,.0f}",
                dates,
            )
        except ValueError:
            table.add_row(
                proj.display_name,
                str(proj.session_count),
                "-", "-", "-", "-", "-",
            )

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {len(projects)} projects, {total_calls:,} AI calls, ${total_cost:,.0f} estimated cost")


def _export_insights_json(report: "InsightsReport", output: Path, project_name: str) -> None:
    """Export insights report as JSON."""
    import json as json_mod
    from dataclasses import asdict

    data = {
        "project": project_name,
        "generated_at": report.generated_at.isoformat(),
        "total_sessions": report.total_sessions,
        "total_ai_calls": report.total_ai_calls,
        "total_input_tokens": report.total_input_tokens,
        "total_output_tokens": report.total_output_tokens,
        "date_range": list(report.date_range),
        "cost": asdict(report.cost),
        "models": report.models,
        "tool_usage": [asdict(t) for t in report.tool_usage],
        "sessions": [asdict(s) for s in report.sessions[:20]],
        "hourly_activity": [asdict(h) for h in report.hourly_activity],
        "workflow_patterns": [asdict(p) for p in report.workflow_patterns],
        "bash_commands": report.bash_commands,
    }
    output.write_text(json_mod.dumps(data, indent=2), encoding="utf-8")
    console.print(f"JSON insights written to [bold]{output}[/bold]")


def _export_summary_json(projects: list, output: Path) -> None:
    """Export cross-project summary as JSON."""
    import json as json_mod
    from ai_trace_auditor.insights.analyzer import analyze_claude_code_dir

    data = []
    for proj in projects:
        try:
            report = analyze_claude_code_dir(proj.dir_path)
            data.append({
                "project": proj.display_name,
                "cwd": proj.cwd,
                "sessions": report.total_sessions,
                "ai_calls": report.total_ai_calls,
                "input_tokens": report.total_input_tokens,
                "output_tokens": report.total_output_tokens,
                "est_cost": round(report.cost.est_cost_with_cache, 2),
                "date_range": list(report.date_range),
            })
        except ValueError:
            data.append({"project": proj.display_name, "sessions": proj.session_count})

    output.write_text(json_mod.dumps(data, indent=2), encoding="utf-8")
    console.print(f"Summary JSON written to [bold]{output}[/bold]")


@app.command()
def workflow(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Path to a project traces directory"),
    ] = None,
    project: Annotated[
        Optional[str],
        typer.Option("--project", "-p", help="Filter by project name"),
    ] = None,
) -> None:
    """Analyze conversation efficiency, prompt patterns, and file churn.

    Shows token efficiency, edit convergence, correction rates, optimal
    session length, and files with the highest iteration count.
    """
    from ai_trace_auditor.insights.projects import discover_projects, get_strip_prefix
    from ai_trace_auditor.insights.renderer import render_workflow
    from ai_trace_auditor.insights.workflow import analyze_workflow

    if path is not None:
        if not path.exists() or not path.is_dir():
            console.print(f"[red]Error:[/red] {path} is not a valid directory")
            raise typer.Exit(code=2)
        try:
            report = analyze_workflow(path)
            render_workflow(report, console)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=2) from e
        return

    # Auto-discover
    projects = discover_projects()
    if not projects:
        console.print("[red]Error:[/red] No Claude Code traces found")
        raise typer.Exit(code=2)

    if project:
        query = project.lower()
        projects = [p for p in projects if query in p.display_name.lower()]
        if not projects:
            console.print(f"[yellow]No projects matching '{project}'[/yellow]")
            raise typer.Exit(code=0)
    else:
        # Default to largest project
        projects = projects[:1]
        console.print(f"[dim]Analyzing largest project: {projects[0].display_name} (use -p to select)[/dim]")

    for proj in projects:
        console.print(f"\n[bold magenta]Project:[/bold magenta] {proj.display_name}")
        try:
            report = analyze_workflow(proj.dir_path)
            render_workflow(report, console)
        except ValueError as e:
            console.print(f"  [dim]{e}[/dim]")


@app.command()
def predict(
) -> None:
    """Cost forecasting, context pressure, CLAUDE.md effectiveness, permissions.

    Analyzes usage trends to forecast costs, detects sessions that hit
    context window limits, measures CLAUDE.md impact on efficiency, and
    audits permission rules.
    """
    from ai_trace_auditor.insights.predict import build_predictive_report
    from ai_trace_auditor.insights.renderer import render_predictions

    console.print("Analyzing usage trends...")
    report = build_predictive_report()
    render_predictions(report, console)


@app.command()
def agents(
) -> None:
    """Analyze multi-agent delegation, plans, and teams.

    Reconstructs agent delegation patterns, analyzes implementation plans,
    and summarizes team configurations and inbox activity.
    """
    from ai_trace_auditor.insights.agents import build_agent_report
    from ai_trace_auditor.insights.renderer import render_agents

    console.print("Scanning agent traces, plans, and teams...")
    report = build_agent_report()
    render_agents(report, console)


@app.command()
def health(
    session_id: Annotated[
        Optional[str],
        typer.Argument(help="Specific session ID to analyze"),
    ] = None,
) -> None:
    """Analyze session health from debug logs.

    Scores each session on tool reliability, streaming stability,
    API reliability, startup speed, and MCP connection health.
    Identifies friction points with actionable recommendations.
    """
    from ai_trace_auditor.insights.debug_parser import parse_all_debug_logs, parse_debug_log
    from ai_trace_auditor.insights.health import aggregate_health, score_session
    from ai_trace_auditor.insights.renderer import render_health_summary

    debug_dir = Path.home() / ".claude" / "debug"
    if not debug_dir.exists():
        console.print("[red]Error:[/red] ~/.claude/debug/ not found")
        raise typer.Exit(code=2)

    if session_id:
        # Single session
        path = debug_dir / f"{session_id}.txt"
        if not path.exists():
            console.print(f"[red]Error:[/red] No debug log for session {session_id}")
            raise typer.Exit(code=2)
        from ai_trace_auditor.insights.debug_parser import parse_debug_log
        debug = parse_debug_log(path)
        h = score_session(None, debug)
        agg = aggregate_health([h])
        render_health_summary([h], agg, console)
    else:
        # All sessions
        console.print("Parsing debug logs...")
        all_debug = parse_all_debug_logs(debug_dir)
        console.print(f"Found {len(all_debug)} debug logs")

        healths = [score_session(None, d) for d in all_debug.values()]
        agg = aggregate_health(healths)
        render_health_summary(healths, agg, console)


@app.command()
def docs(
    path: Annotated[
        Path, typer.Argument(help="Codebase directory to scan")
    ] = Path("."),
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Output file path")
    ] = None,
    trace_path: Annotated[
        Optional[Path],
        typer.Option("--traces", "-t", help="Trace file/directory for enrichment"),
    ] = None,
    trace_format: Annotated[
        str,
        typer.Option("--trace-format", help="Trace format: auto, otel, langfuse, raw"),
    ] = "auto",
    risk_level: Annotated[
        str, typer.Option("--risk-level", help="Risk classification")
    ] = "high_risk",
    agent_friendly: Annotated[
        bool,
        typer.Option("--agent-friendly", help="Run agent-friendly documentation checks on output"),
    ] = False,
) -> None:
    """Generate EU AI Act Article 11 / Annex IV technical documentation.

    Scans a codebase for AI framework usage (SDKs, models, vector DBs,
    training data, evaluation scripts, deployment configs, API endpoints)
    and generates a structured Markdown document following Annex IV.

    Optionally enrich with trace data from `aitrace audit` for sections
    on monitoring, lifecycle, and post-market monitoring.
    """
    if not path.exists() or not path.is_dir():
        console.print(f"[red]Error:[/red] {path} is not a valid directory")
        raise typer.Exit(code=2)

    # Load project config
    cfg = load_config(path)
    if cfg is not None:
        console.print("[dim]Loaded config from .aitrace.toml[/dim]")
        if risk_level == "high_risk" and cfg.risk_level != "high_risk":
            risk_level = cfg.risk_level

    # Scan codebase
    from ai_trace_auditor.scanner import scan_codebase

    console.print(f"Scanning [bold]{path}[/bold] for AI framework usage...")
    scan_result = scan_codebase(path)
    _print_scan_summary(scan_result)

    # Optional trace enrichment
    gap_report = None
    if trace_path is not None:
        if not trace_path.exists():
            console.print(f"[red]Error:[/red] {trace_path} does not exist")
            raise typer.Exit(code=2)

        console.print(f"Loading traces from [bold]{trace_path}[/bold]...")
        try:
            traces = _load_traces(trace_path, trace_format)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=2) from e

        if traces:
            registry = RequirementRegistry()
            registry.load()
            analyzer = ComplianceAnalyzer(registry)
            gap_report = analyzer.analyze(
                traces=traces,
                risk_level=risk_level,
                trace_source=str(trace_path),
            )
            console.print(
                f"Trace enrichment: [bold]{gap_report.overall_score * 100:.1f}%[/bold] compliance"
            )

    # Generate Annex IV document
    from ai_trace_auditor.docs import generate_annex_iv
    from ai_trace_auditor.reports.docs_report import DocsReporter

    console.print("Generating Annex IV documentation...")
    doc = generate_annex_iv(scan_result, gap_report)
    reporter = DocsReporter()

    rendered = reporter.render(doc)

    if output:
        reporter.write(doc, output)
        console.print(f"Documentation written to [bold]{output}[/bold]")
    else:
        stdout_console.print(rendered)

    # Print completion summary
    _print_docs_summary(doc)

    # Agent-friendly checks
    if agent_friendly:
        _run_agent_friendly_checks(rendered)


def _print_scan_summary(scan: "CodeScanResult") -> None:
    """Print a Rich summary of codebase scan results."""
    table = Table(title="Codebase Scan Results")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    table.add_row(
        "Files scanned", str(scan.file_count), f"in {scan.scan_duration_ms}ms",
    )
    table.add_row(
        "AI SDK imports",
        str(len(scan.ai_imports)),
        ", ".join(scan.providers) or "-",
    )
    table.add_row(
        "Model identifiers",
        str(len(scan.model_references)),
        ", ".join(scan.models[:5]) or "-",
    )
    table.add_row(
        "Vector databases",
        str(len(scan.vector_dbs)),
        ", ".join(sorted({v.db_name for v in scan.vector_dbs})) or "-",
    )
    table.add_row(
        "Training data refs",
        str(len(scan.training_data_refs)),
        "",
    )
    table.add_row(
        "Eval scripts",
        str(len(scan.eval_scripts)),
        "",
    )
    table.add_row(
        "Deployment configs",
        str(len(scan.deployment_configs)),
        ", ".join(sorted({d.config_type for d in scan.deployment_configs})) or "-",
    )
    table.add_row(
        "AI endpoints",
        str(len(scan.ai_endpoints)),
        "",
    )
    console.print(table)


def _print_docs_summary(doc: "AnnexIVDocument") -> None:
    """Print completion summary for generated Annex IV document."""
    from ai_trace_auditor.models.docs import AnnexIVDocument

    auto_count = sum(1 for s in doc.sections if s.auto_populated)
    manual_count = len(doc.sections) - auto_count

    console.print()
    console.print(
        f"[bold]Documentation:[/bold] {auto_count}/9 sections auto-populated, "
        f"{manual_count} require manual input"
    )
    if not doc.trace_enriched:
        console.print(
            "[dim]Tip: Use --traces to enrich sections 3, 6, and 9 with compliance data[/dim]"
        )


def _run_agent_friendly_checks(markdown: str) -> None:
    """Run and display agent-friendly documentation checks."""
    from ai_trace_auditor.agent_friendly import check_agent_friendly

    report = check_agent_friendly(markdown)

    console.print()
    table = Table(title="Agent-Friendly Documentation Checks")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Value", justify="right")
    table.add_column("Detail")

    status_style = {"pass": "green", "warn": "yellow", "fail": "red"}

    for check in report.checks:
        style = status_style.get(check.status, "white")
        symbol = {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(check.status, "?")
        table.add_row(
            check.title,
            f"[{style}]{symbol} {check.status}[/{style}]",
            check.value,
            check.detail,
        )

    console.print(table)
    console.print(
        f"\n[bold]Agent-friendly score:[/bold] {report.score_pct:.0f}% "
        f"({report.passed} passed, {report.warnings} warnings, {report.failed} failed)"
    )


@app.command(name="agent-friendly")
def agent_friendly_cmd(
    path: Annotated[
        Path, typer.Argument(help="Markdown file to check"),
    ],
) -> None:
    """Check if a Markdown document is agent-friendly.

    Evaluates whether a compliance document (or any Markdown file) can
    be effectively consumed by AI coding agents. Checks document size,
    structure, placeholder density, information density, and more.

    Based on the Agent-Friendly Documentation Spec (agentdocsspec.com).
    """
    if not path.exists():
        console.print(f"[red]Error:[/red] {path} does not exist")
        raise typer.Exit(code=2)

    markdown = path.read_text(encoding="utf-8")
    _run_agent_friendly_checks(markdown)


@app.command()
def flow(
    path: Annotated[
        Path, typer.Argument(help="Codebase directory to scan")
    ] = Path("."),
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Output file path")
    ] = None,
    mermaid_only: Annotated[
        bool, typer.Option("--mermaid", help="Output only the Mermaid diagram")
    ] = False,
) -> None:
    """Map AI data flows for EU AI Act Article 13 and GDPR Article 30.

    Scans a codebase for external service connections (AI providers,
    vector DBs, databases, HTTP clients, cloud SDKs), generates a
    Mermaid data flow diagram, and produces a GDPR Article 30 Record
    of Processing Activities template.
    """
    from datetime import datetime, timezone

    from ai_trace_auditor.flow import detect_flows, generate_mermaid, generate_ropa
    from ai_trace_auditor.models.flow import FlowDiagram
    from ai_trace_auditor.reports.flow_report import FlowReporter
    from ai_trace_auditor.scanner import scan_codebase

    if not path.exists() or not path.is_dir():
        console.print(f"[red]Error:[/red] {path} is not a valid directory")
        raise typer.Exit(code=2)

    # Load project config
    cfg = load_config(path)
    if cfg is not None:
        console.print("[dim]Loaded config from .aitrace.toml[/dim]")

    # First run the code scanner (needed for AI provider/vector DB detection)
    console.print(f"Scanning [bold]{path}[/bold] for data flows...")
    code_scan = scan_codebase(path)

    # Then detect flows
    flow_result = detect_flows(path, code_scan)
    _print_flow_summary(flow_result)

    if not flow_result.external_services and not flow_result.data_flows:
        console.print("[yellow]No external data flows detected.[/yellow]")
        raise typer.Exit(code=0)

    # Generate Mermaid diagram
    mermaid_src = generate_mermaid(flow_result)

    if mermaid_only:
        if output:
            output.write_text(mermaid_src, encoding="utf-8")
            console.print(f"Mermaid diagram written to [bold]{output}[/bold]")
        else:
            stdout_console.print(mermaid_src)
        raise typer.Exit(code=0)

    # Generate full report with RoPA
    ropa = generate_ropa(flow_result)
    diagram = FlowDiagram(
        mermaid=mermaid_src,
        services=flow_result.external_services,
        flows=flow_result.data_flows,
        generated_at=datetime.now(timezone.utc),
        source_dir=str(path),
    )

    reporter = FlowReporter()
    if output:
        reporter.write(diagram, ropa, output)
        console.print(f"Flow report written to [bold]{output}[/bold]")
    else:
        stdout_console.print(reporter.render(diagram, ropa))

    console.print(
        f"\n[bold]Flows:[/bold] {len(flow_result.data_flows)} data flows to "
        f"{len(flow_result.external_services)} external services"
    )


def _print_flow_summary(flow_result: "FlowScanResult") -> None:
    """Print a Rich summary of flow scan results."""
    from ai_trace_auditor.models.flow import FlowScanResult

    table = Table(title="Data Flow Scan Results")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    table.add_row(
        "External services",
        str(len(flow_result.external_services)),
        ", ".join(flow_result.service_names[:5]) or "-",
    )
    table.add_row(
        "Data flows",
        str(len(flow_result.data_flows)),
        "",
    )
    table.add_row(
        "HTTP clients",
        str(len(flow_result.http_clients)),
        ", ".join(sorted({h.library for h in flow_result.http_clients})) or "-",
    )
    table.add_row(
        "Databases",
        str(len(flow_result.databases)),
        ", ".join(sorted({d.db_type for d in flow_result.databases})) or "-",
    )
    table.add_row(
        "Cloud services",
        str(len(flow_result.cloud_services)),
        ", ".join(sorted({f"{c.provider}/{c.service}" for c in flow_result.cloud_services})) or "-",
    )
    table.add_row(
        "File I/O ops",
        str(len(flow_result.file_io)),
        "",
    )
    console.print(table)


@app.command()
def comply(
    path: Annotated[
        Path, typer.Argument(help="Codebase directory to scan")
    ] = Path("."),
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output file or directory"),
    ] = None,
    trace_path: Annotated[
        Optional[Path],
        typer.Option("--traces", "-t", help="Trace file/directory for Article 12 audit"),
    ] = None,
    trace_format: Annotated[
        str,
        typer.Option("--trace-format", help="Trace format: auto, otel, langfuse, raw"),
    ] = "auto",
    risk_level: Annotated[
        str, typer.Option("--risk-level", help="Risk classification")
    ] = "high_risk",
    split: Annotated[
        bool,
        typer.Option("--split", help="Write individual report files to a directory"),
    ] = False,
    report_format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: markdown, pdf, both"),
    ] = "markdown",
    evidence_pack: Annotated[
        Optional[Path],
        typer.Option("--evidence-pack", help="Generate a compliance evidence pack in this directory"),
    ] = None,
) -> None:
    """Run the full EU AI Act compliance suite in one command.

    Scans your codebase and generates a complete compliance package
    covering Articles 11 (technical documentation), 12 (record-keeping,
    if traces provided), and 13 (data flow transparency), plus a
    GDPR Article 30 Record of Processing Activities.

    One codebase. One command. Three articles.
    """
    from ai_trace_auditor.comply.runner import run_full_compliance
    from ai_trace_auditor.reports.comply_report import ComplyReporter

    if not path.exists() or not path.is_dir():
        console.print(f"[red]Error:[/red] {path} is not a valid directory")
        raise typer.Exit(code=2)

    # Load project config (CLI flags override config values)
    cfg = load_config(path)
    if cfg is not None:
        console.print("[dim]Loaded config from .aitrace.toml[/dim]")
        if trace_path is None and cfg.traces_path is not None:
            trace_path = Path(cfg.traces_path)
        if trace_format == "auto" and cfg.trace_format != "auto":
            trace_format = cfg.trace_format
        if risk_level == "high_risk" and cfg.risk_level != "high_risk":
            risk_level = cfg.risk_level
        if not split and cfg.split:
            split = cfg.split
        if report_format == "markdown" and cfg.report_format != "markdown":
            report_format = cfg.report_format

    if trace_path and not trace_path.exists():
        console.print(f"[red]Error:[/red] {trace_path} does not exist")
        raise typer.Exit(code=2)

    console.print(f"[bold]EU AI Act Compliance Suite[/bold]")
    console.print(f"Scanning [bold]{path}[/bold]...\n")

    custom_reqs = cfg.custom_requirements if cfg is not None else None
    pkg = run_full_compliance(
        codebase_dir=path,
        trace_path=trace_path,
        trace_format=trace_format,
        risk_level=risk_level,
        custom_requirements=custom_reqs,
    )

    # Print summary
    _print_comply_summary(pkg)

    # Evidence pack mode
    if evidence_pack is not None:
        if output is not None:
            console.print("[red]Error:[/red] Use --evidence-pack OR --output, not both")
            raise typer.Exit(code=2)

        from ai_trace_auditor.evidence.pack import generate_evidence_pack

        created = generate_evidence_pack(pkg, evidence_pack)
        console.print(f"\n[bold green]Evidence pack written to {evidence_pack}/[/bold green]")
        for f in created:
            console.print(f"  {f.name}")

        for warning in pkg.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")

        has_gaps = (
            pkg.gap_report is not None
            and (pkg.gap_report.summary.missing > 0 or pkg.gap_report.summary.partial > 0)
        )
        raise typer.Exit(code=1 if has_gaps else 0)

    # Output
    reporter = ComplyReporter()
    want_pdf = report_format in ("pdf", "both")
    want_md = report_format in ("markdown", "both")

    if want_pdf:
        from ai_trace_auditor.reports.pdf_report import check_pdf_available, markdown_to_pdf
        if not check_pdf_available():
            console.print(
                "[red]Error:[/red] PDF output requires extra dependencies. "
                "Install with: [bold]pip install ai-trace-auditor\\[pdf][/bold]"
            )
            raise typer.Exit(code=2)

    if split and output:
        created = reporter.write_split(pkg, output)
        console.print(f"\n[bold]Compliance package written to {output}/[/bold]")
        for f in created:
            console.print(f"  {f.name}")
        if want_pdf:
            from ai_trace_auditor.reports.pdf_report import markdown_to_pdf
            for f in created:
                if f.suffix == ".md":
                    pdf_path = f.with_suffix(".pdf")
                    markdown_to_pdf(f.read_text(encoding="utf-8"), pdf_path)
                    console.print(f"  {pdf_path.name} [green](PDF)[/green]")
    elif output:
        md_content = reporter.render(pkg)
        if want_md:
            output.write_text(md_content, encoding="utf-8")
            console.print(f"\nCompliance package written to [bold]{output}[/bold]")
        if want_pdf:
            from ai_trace_auditor.reports.pdf_report import markdown_to_pdf
            pdf_path = output.with_suffix(".pdf") if output.suffix == ".md" else Path(str(output) + ".pdf")
            markdown_to_pdf(md_content, pdf_path)
            console.print(f"PDF report written to [bold]{pdf_path}[/bold]")
    else:
        stdout_console.print(reporter.render(pkg))

    # Warnings
    for warning in pkg.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")

    # Exit code
    has_gaps = (
        pkg.gap_report is not None
        and (pkg.gap_report.summary.missing > 0 or pkg.gap_report.summary.partial > 0)
    )
    raise typer.Exit(code=1 if has_gaps else 0)


def _print_comply_summary(pkg: "CompliancePackage") -> None:
    """Print the unified compliance summary."""
    from ai_trace_auditor.comply.runner import CompliancePackage

    table = Table(title="EU AI Act Compliance Package", border_style="bold green")
    table.add_column("Article", style="bold")
    table.add_column("Status")
    table.add_column("Key Metric", justify="right")

    # Article 12
    if pkg.gap_report:
        score = pkg.gap_report.overall_score * 100
        color = "green" if score >= 90 else "yellow" if score >= 50 else "red"
        table.add_row(
            "Art. 12 — Record-Keeping",
            "[green]Audited[/green]",
            f"[{color}]{score:.1f}%[/{color}] compliance",
        )
    else:
        table.add_row(
            "Art. 12 — Record-Keeping",
            "[dim]No traces[/dim]",
            "[dim]Use --traces[/dim]",
        )

    # Article 11
    pct = pkg.docs_completion_pct
    table.add_row(
        "Art. 11 — Tech Docs (Annex IV)",
        "[green]Generated[/green]",
        f"{pct:.0f}% auto-populated",
    )

    # Article 13
    table.add_row(
        "Art. 13 — Transparency",
        "[green]Mapped[/green]",
        f"{pkg.service_count} services, {pkg.flow_count} flows",
    )

    # GDPR
    ropa_count = len(pkg.ropa.entries) if pkg.ropa else 0
    table.add_row(
        "GDPR Art. 30 — RoPA",
        "[green]Generated[/green]",
        f"{ropa_count} activities",
    )

    console.print(table)

    # Quick stats
    console.print(f"\n[dim]Files scanned: {pkg.code_scan.file_count} | "
                  f"AI providers: {', '.join(pkg.code_scan.providers) or 'none'} | "
                  f"Models: {', '.join(pkg.code_scan.models[:3]) or 'none'}[/dim]")


@app.command(name="import")
def import_traces(
    source: Annotated[
        str,
        typer.Argument(help="Platform to import from: langfuse"),
    ],
    api_url: Annotated[
        str,
        typer.Option("--api-url", help="Platform API base URL"),
    ] = "",
    api_key: Annotated[
        str,
        typer.Option("--api-key", help="API key (or Langfuse public key)", envvar="AITRACE_API_KEY"),
    ] = "",
    secret_key: Annotated[
        str,
        typer.Option("--secret-key", help="Secret key (Langfuse)", envvar="AITRACE_SECRET_KEY"),
    ] = "",
    since: Annotated[
        Optional[str],
        typer.Option("--since", help="Import traces after this date (ISO 8601)"),
    ] = None,
    until: Annotated[
        Optional[str],
        typer.Option("--until", help="Import traces before this date (ISO 8601)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Maximum traces to import"),
    ] = 1000,
    regulation: Annotated[
        str,
        typer.Option("-r", "--regulation", help="Regulation to audit against"),
    ] = "EU AI Act",
    output: Annotated[
        Optional[Path],
        typer.Option("-o", "--output", help="Output file (default: stdout)"),
    ] = None,
    report_format: Annotated[
        str,
        typer.Option("--report-format", help="Report format: markdown, json"),
    ] = "markdown",
    tags: Annotated[
        Optional[str],
        typer.Option("--tags", help="Comma-separated tags to filter"),
    ] = None,
) -> None:
    """Import traces from an external platform and audit for compliance.

    Pulls traces directly from observability platforms (Langfuse, etc.)
    and runs compliance analysis. No file export needed.

    Example:
        aitrace import langfuse --api-key pk-... --secret-key sk-... --since 2026-03-01
    """
    from datetime import datetime as dt

    from ai_trace_auditor.importers.base import ImportConfig

    source_lower = source.lower()

    if source_lower == "langfuse":
        try:
            from ai_trace_auditor.importers.langfuse_api import LangfuseImporter
        except ImportError:
            console.print(
                "[red]httpx is required for Langfuse import. "
                "Install with: pip install ai-trace-auditor[langfuse][/red]"
            )
            raise typer.Exit(1)

        url = api_url or "https://cloud.langfuse.com"
        importer = LangfuseImporter(api_url=url, api_key=api_key, secret_key=secret_key)
    else:
        console.print(f"[red]Unknown import source: {source}. Supported: langfuse[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Connecting to {importer.platform_name}...[/bold]")
    if not importer.test_connection():
        console.print("[red]Connection failed. Check your API key and URL.[/red]")
        raise typer.Exit(1)
    console.print("[green]Connected.[/green]")

    config = ImportConfig(
        api_url=api_url or "https://cloud.langfuse.com",
        api_key=api_key,
        secret_key=secret_key,
        since=dt.fromisoformat(since) if since else None,
        until=dt.fromisoformat(until) if until else None,
        limit=limit,
        tags=tags.split(",") if tags else None,
    )

    console.print(f"[bold]Importing up to {limit} traces...[/bold]")
    traces = importer.import_traces(config)

    if not traces:
        console.print("[yellow]No traces found matching filters.[/yellow]")
        raise typer.Exit(0)

    total_spans = sum(len(t.spans) for t in traces)
    console.print(f"[green]Imported {len(traces)} traces ({total_spans} spans).[/green]")

    console.print(f"[bold]Auditing against {regulation}...[/bold]")
    registry = RequirementRegistry()
    registry.load()

    analyzer = ComplianceAnalyzer(registry)
    report = analyzer.analyze(traces, regulation=regulation)

    _print_report_summary(report)

    if report_format == "json":
        content = JSONReporter().render(report)
    else:
        content = MarkdownReporter().render(report)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Report written to {output}[/green]")
    else:
        stdout_console.print(content)


@app.command(name="lint-guide")
def lint_guide_cmd(
    path: Annotated[Path, typer.Argument(help="Markdown compliance guide to lint")],
) -> None:
    """Lint a compliance guide for common EU AI Act mistakes.

    Catches: Article 13/50 conflation, retention period errors, missing scope
    checks, provider/deployer conflation, self-promotional content, citation errors.
    """
    if not path.exists():
        console.print(f"[red]Error:[/red] {path} does not exist")
        raise typer.Exit(code=2)

    from ai_trace_auditor.guide_linter.rules import lint_guide

    content = path.read_text(encoding="utf-8")
    issues = lint_guide(content)

    if not issues:
        console.print(f"[green]No issues found[/green] in {path}")
        raise typer.Exit(code=0)

    severity_colors = {"error": "red", "warning": "yellow", "info": "blue"}

    table = Table(title=f"Guide Lint: {path.name}")
    table.add_column("Rule", style="dim")
    table.add_column("Sev")
    table.add_column("Line", justify="right")
    table.add_column("Issue")
    table.add_column("Fix", style="dim")

    for issue in issues:
        color = severity_colors.get(issue.severity, "white")
        table.add_row(
            issue.rule_id,
            f"[{color}]{issue.severity.upper()}[/{color}]",
            str(issue.line),
            issue.message,
            issue.fix_hint,
        )

    console.print(table)

    error_count = sum(1 for i in issues if i.severity == "error")
    warn_count = sum(1 for i in issues if i.severity == "warning")
    console.print(
        f"\n[bold]{len(issues)} issues:[/bold] "
        f"[red]{error_count} errors[/red], [yellow]{warn_count} warnings[/yellow]"
    )

    raise typer.Exit(code=1 if error_count > 0 else 0)


def _validate_requirement_entry(req_data: dict, index: int) -> list[str]:
    """Validate a single requirement dict. Returns list of error strings."""
    errors: list[str] = []
    for field in ("id", "title", "description"):
        if field not in req_data or not req_data[field]:
            errors.append(f"missing required field '{field}'")

    for ef in req_data.get("evidence_fields", []):
        if "field_path" not in ef:
            errors.append("evidence_field missing 'field_path'")
        if "description" not in ef:
            errors.append("evidence_field missing 'description'")

    sev = req_data.get("severity", "mandatory")
    if sev not in ("mandatory", "recommended", "best_practice"):
        errors.append(f"invalid severity '{sev}'")

    return errors


@app.command(name="validate-requirements")
def validate_requirements_cmd(
    path: Annotated[
        Path, typer.Argument(help="YAML file or directory of requirement definitions")
    ],
) -> None:
    """Validate custom requirement YAML files against the schema.

    Checks that requirement definitions have valid IDs, titles, descriptions,
    evidence fields, and severity levels. Use this to verify custom requirement
    packs before running compliance checks with them.

    Example:
        aitrace validate-requirements ./internal-policies/
    """
    import yaml

    if not path.exists():
        console.print(f"[red]Error:[/red] {path} does not exist")
        raise typer.Exit(code=2)

    yaml_files = sorted(path.rglob("*.yaml")) if path.is_dir() else [path]

    if not yaml_files:
        console.print(f"[yellow]No YAML files found in {path}[/yellow]")
        raise typer.Exit(code=0)

    total_reqs = 0
    total_errors = 0

    for yaml_path in yaml_files:
        console.print(f"\n[bold]{yaml_path.name}[/bold]")

        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            console.print(f"  [red]YAML parse error:[/red] {e}")
            total_errors += 1
            continue

        if not data or "requirements" not in data:
            console.print("  [yellow]Warning:[/yellow] No 'requirements' key found")
            continue

        status = data.get("status", "")
        if status == "beta":
            console.print("  [yellow]Status: beta[/yellow]")

        for i, req_data in enumerate(data["requirements"]):
            total_reqs += 1
            errors = _validate_requirement_entry(req_data, i)
            req_id = req_data.get("id", f"requirement[{i}]")

            if errors:
                total_errors += len(errors)
                for err in errors:
                    console.print(f"  [red]Error[/red] {req_id}: {err}")
            else:
                console.print(f"  [green]OK[/green] {req_id}: {req_data.get('title', '')}")

    console.print(f"\n[bold]Validated {total_reqs} requirements across {len(yaml_files)} files.[/bold]")
    if total_errors > 0:
        console.print(f"[red]{total_errors} error(s) found.[/red]")
        raise typer.Exit(code=1)
    else:
        console.print("[green]All requirements valid.[/green]")
        raise typer.Exit(code=0)


@app.command()
def version() -> None:
    """Print version information."""
    console.print(f"ai-trace-auditor v{ai_trace_auditor.__version__}")


if __name__ == "__main__":
    app()
