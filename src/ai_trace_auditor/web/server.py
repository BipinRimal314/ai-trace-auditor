"""FastAPI web server for the AI Trace Auditor dashboard.

Run directly:
    python -m ai_trace_auditor.web.server

Or via the CLI entry point:
    aitrace-web
"""

from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path

try:
    import uvicorn
except ImportError:
    uvicorn = None  # Not needed in serverless environments (Vercel)
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import ai_trace_auditor
from ai_trace_auditor.reports.markdown import MarkdownReporter
from ai_trace_auditor.web.audit_service import (
    build_results_context,
    get_regulation_summary,
    get_regulations_detail,
    get_sample_traces,
    load_registry,
    load_traces_from_sample,
    load_traces_from_upload,
    run_audit,
)
from ai_trace_auditor.web.report_cache import ReportCache

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(
    title="AI Trace Auditor",
    version=ai_trace_auditor.__version__,
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount static files
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Load registry once at startup
_registry = load_registry()
_report_cache = ReportCache()
_markdown_reporter = MarkdownReporter()


def _safe_pdf_filename(trace_source: str) -> str:
    """Build a filesystem-safe PDF filename derived from the trace source."""
    stem = Path(trace_source).stem or "audit"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "audit"
    return f"{cleaned[:80]}-compliance-report.pdf"


def _render(
    request: Request,
    name: str,
    context: dict | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a Jinja2 template with Starlette 1.0 API."""
    ctx = context or {}
    return templates.TemplateResponse(
        request, name, context=ctx, status_code=status_code
    )


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    """Landing page with regulation overview and product hero."""
    regulation_summaries = get_regulation_summary(_registry)
    total_requirements = _registry.count

    return _render(request, "index.html", {
        "version": ai_trace_auditor.__version__,
        "regulations": regulation_summaries,
        "total_requirements": total_requirements,
    })


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> HTMLResponse:
    """Audit page with file upload and sample trace selection."""
    samples = get_sample_traces()
    regulations = _registry.regulations

    return _render(request, "audit.html", {
        "version": ai_trace_auditor.__version__,
        "samples": samples,
        "regulations": regulations,
    })


@app.post("/audit/run", response_class=HTMLResponse)
async def run_audit_handler(
    request: Request,
    regulation: str = Form(""),
    sample_file: str = Form(""),
    trace_file: UploadFile | None = File(None),
) -> HTMLResponse:
    """Execute an audit and display results."""
    regulation_filter = regulation if regulation else None

    try:
        if trace_file and trace_file.filename and trace_file.size:
            content = await trace_file.read()
            traces = load_traces_from_upload(content, trace_file.filename)
            trace_source = trace_file.filename
        elif sample_file:
            traces = load_traces_from_sample(sample_file)
            trace_source = sample_file
        else:
            return _render(request, "error.html", {
                "version": ai_trace_auditor.__version__,
                "error_title": "No Trace Data",
                "error_message": "Upload a trace file or select a sample trace.",
            }, status_code=400)

        if not traces:
            return _render(request, "error.html", {
                "version": ai_trace_auditor.__version__,
                "error_title": "Empty Trace",
                "error_message": "The trace file contained no parseable traces.",
            }, status_code=400)

        report = run_audit(traces, _registry, regulation_filter, trace_source)
        results_ctx = build_results_context(report, traces)
        markdown_report = _markdown_reporter.render(report)
        report_id = _report_cache.put(markdown_report, trace_source)

    except Exception as exc:
        logger.exception("Audit failed")
        return _render(request, "error.html", {
            "version": ai_trace_auditor.__version__,
            "error_title": "Audit Error",
            "error_message": str(exc),
        }, status_code=500)

    template_name = (
        "multi_agent.html" if results_ctx["is_multi_agent"] else "results.html"
    )

    return _render(request, template_name, {
        "version": ai_trace_auditor.__version__,
        "trace_source": trace_source,
        "report_id": report_id,
        **results_ctx,
    })


@app.get("/audit/pdf/{report_id}")
async def download_pdf(report_id: str) -> StreamingResponse:
    """Stream a PDF rendering of a previously generated audit report."""
    cached = _report_cache.get(report_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="Report has expired or does not exist. Re-run the audit.",
        )

    try:
        from ai_trace_auditor.reports.pdf_report import markdown_to_pdf
    except ImportError as exc:
        logger.exception("PDF dependencies missing")
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF generation is unavailable on this deployment. "
                "Install ai-trace-auditor[pdf]."
            ),
        ) from exc

    tmp_dir = Path(os.environ.get("PDF_TMPDIR", "/tmp"))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{report_id}.pdf"

    try:
        markdown_to_pdf(cached.markdown, tmp_path)
        pdf_bytes = tmp_path.read_bytes()
    except Exception as exc:
        logger.exception("PDF rendering failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to render PDF: {exc}",
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    filename = _safe_pdf_filename(cached.trace_source)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/regulations", response_class=HTMLResponse)
async def regulations_page(request: Request) -> HTMLResponse:
    """Browse all regulations and their requirements."""
    regulations_data = get_regulations_detail(_registry)

    return _render(request, "regulations.html", {
        "version": ai_trace_auditor.__version__,
        "regulations": regulations_data,
    })


def main() -> None:
    """Entry point for the web server."""
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(
        "ai_trace_auditor.web.server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
