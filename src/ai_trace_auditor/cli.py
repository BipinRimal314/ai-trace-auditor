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

    if report.summary.top_gaps:
        console.print()
        console.print("[bold]Top gaps:[/bold]")
        for i, gap in enumerate(report.summary.top_gaps, 1):
            console.print(f"  {i}. {gap}")


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
) -> None:
    """Audit LLM traces against regulatory compliance requirements."""
    if not path.exists():
        console.print(f"[red]Error:[/red] {path} does not exist")
        raise typer.Exit(code=2)

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
        console.print(f"[dim]Severity:[/dim] {req.severity}")
        if req.applies_to:
            console.print(f"[dim]Applies to:[/dim] {', '.join(req.applies_to)}")
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
def version() -> None:
    """Print version information."""
    console.print(f"ai-trace-auditor v{ai_trace_auditor.__version__}")


if __name__ == "__main__":
    app()
