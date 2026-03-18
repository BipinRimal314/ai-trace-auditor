"""Detect external service connections and data flows in source code."""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

from ai_trace_auditor.models.docs import CodeScanResult
from ai_trace_auditor.models.flow import (
    CloudServiceUsage,
    DataFlow,
    DatabaseConnection,
    ExternalService,
    FileIOOperation,
    FlowScanResult,
    HTTPClientUsage,
)
from ai_trace_auditor.flow.patterns import (
    AI_PROVIDER_GDPR,
    AWS_SERVICE_PATTERNS,
    CLOUD_SDK_IMPORTS,
    DATABASE_IMPORTS,
    FILE_READ_PATTERNS,
    FILE_WRITE_PATTERNS,
    HTTP_CLIENT_IMPORTS,
    JS_DATABASE_IMPORTS,
    JS_HTTP_CLIENT_IMPORTS,
    URL_PATTERN,
    VECTOR_DB_GDPR,
)
from ai_trace_auditor.scanner.patterns import (
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    SKIP_DIRS,
)


def detect_flows(root_dir: Path, code_scan: CodeScanResult | None = None) -> FlowScanResult:
    """Scan a codebase for external service connections and data flows.

    Builds on top of CodeScanResult (if provided) to enrich AI provider
    and vector DB detections with GDPR flow annotations.
    """
    start = time.monotonic()

    external_services: list[ExternalService] = []
    data_flows: list[DataFlow] = []
    http_clients: list[HTTPClientUsage] = []
    databases: list[DatabaseConnection] = []
    file_io: list[FileIOOperation] = []
    cloud_services: list[CloudServiceUsage] = []
    file_count = 0

    all_extensions = PYTHON_EXTENSIONS | JS_EXTENSIONS

    for file_path in sorted(root_dir.rglob("*")):
        if file_path.is_dir():
            continue
        if _should_skip(file_path, root_dir):
            continue
        if file_path.suffix.lower() not in all_extensions:
            continue

        file_count += 1
        fp = str(file_path)

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = source.splitlines()
        is_python = file_path.suffix.lower() in PYTHON_EXTENSIONS

        # Python AST-based detection
        if is_python:
            _detect_python_imports(source, fp, lines, http_clients, databases, cloud_services)

        # JS import detection
        if not is_python:
            _detect_js_imports(lines, fp, http_clients, databases)

        # Line-by-line patterns (both languages)
        _detect_file_io(lines, fp, file_io)
        _detect_http_urls(lines, fp, http_clients)
        _detect_aws_services(lines, fp, cloud_services)

    # Build external services and flows from code_scan (AI providers + vector DBs)
    if code_scan is not None:
        _build_ai_provider_flows(code_scan, external_services, data_flows)
        _build_vector_db_flows(code_scan, external_services, data_flows)

    # Build external services from databases
    _build_database_services(databases, external_services, data_flows)

    # Build external services from cloud SDKs
    _build_cloud_services(cloud_services, external_services, data_flows)

    # Build external services from HTTP clients with known URLs
    _build_http_services(http_clients, external_services, data_flows)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return FlowScanResult(
        scanned_dir=str(root_dir),
        file_count=file_count,
        scan_duration_ms=elapsed_ms,
        external_services=external_services,
        data_flows=data_flows,
        http_clients=http_clients,
        databases=databases,
        file_io=file_io,
        cloud_services=cloud_services,
    )


def _should_skip(file_path: Path, root_dir: Path) -> bool:
    try:
        rel = file_path.relative_to(root_dir)
    except ValueError:
        return True
    for part in rel.parts[:-1]:
        if part in SKIP_DIRS or part.endswith(".egg-info"):
            return True
    return False


# ---------------------------------------------------------------------------
# Python import detection
# ---------------------------------------------------------------------------

_PY_HTTP_LOOKUP: dict[str, str] = {}
for lib, modules in HTTP_CLIENT_IMPORTS.items():
    for mod in modules:
        _PY_HTTP_LOOKUP[mod] = lib

_PY_DB_LOOKUP: dict[str, tuple[str, str]] = {}
for db_type, (lib_name, modules) in DATABASE_IMPORTS.items():
    for mod in modules:
        _PY_DB_LOOKUP[mod] = (db_type.replace("_sa", ""), lib_name)

_PY_CLOUD_LOOKUP: dict[str, tuple[str, str]] = {}
for provider, services in CLOUD_SDK_IMPORTS.items():
    for svc, modules in services.items():
        for mod in modules:
            _PY_CLOUD_LOOKUP[mod] = (provider, svc)


def _detect_python_imports(
    source: str,
    fp: str,
    lines: list[str],
    http_clients: list[HTTPClientUsage],
    databases: list[DatabaseConnection],
    cloud_services: list[CloudServiceUsage],
) -> None:
    try:
        tree = ast.parse(source, filename=fp)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        mod_name = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name
                _check_py_import(mod_name, fp, node.lineno, http_clients, databases, cloud_services)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod_name = node.module
            _check_py_import(mod_name, fp, node.lineno, http_clients, databases, cloud_services)


def _check_py_import(
    mod_name: str,
    fp: str,
    line: int,
    http_clients: list[HTTPClientUsage],
    databases: list[DatabaseConnection],
    cloud_services: list[CloudServiceUsage],
) -> None:
    # HTTP clients
    for prefix, lib in _PY_HTTP_LOOKUP.items():
        if mod_name == prefix or mod_name.startswith(prefix + "."):
            http_clients.append(HTTPClientUsage(library=lib, file_path=fp, line_number=line))
            return

    # Databases
    for prefix, (db_type, lib_name) in _PY_DB_LOOKUP.items():
        if mod_name == prefix or mod_name.startswith(prefix + "."):
            databases.append(DatabaseConnection(
                db_type=db_type, library=lib_name, file_path=fp, line_number=line,
            ))
            return

    # Cloud SDKs
    for prefix, (provider, svc) in _PY_CLOUD_LOOKUP.items():
        if mod_name == prefix or mod_name.startswith(prefix + "."):
            cloud_services.append(CloudServiceUsage(
                provider=provider, service=svc, library=mod_name, file_path=fp, line_number=line,
            ))
            return


# ---------------------------------------------------------------------------
# JS import detection
# ---------------------------------------------------------------------------

_JS_IMPORT_RE = re.compile(r"""(?:import\s+.*?\s+from\s+|require\s*\(\s*)['"](.+?)['"]""")

_JS_HTTP_LOOKUP: dict[str, str] = {}
for lib, packages in JS_HTTP_CLIENT_IMPORTS.items():
    for pkg in packages:
        _JS_HTTP_LOOKUP[pkg] = lib

_JS_DB_LOOKUP: dict[str, tuple[str, str]] = {}
for db_type, (lib_name, packages) in JS_DATABASE_IMPORTS.items():
    for pkg in packages:
        _JS_DB_LOOKUP[pkg] = (db_type, lib_name)


def _detect_js_imports(
    lines: list[str],
    fp: str,
    http_clients: list[HTTPClientUsage],
    databases: list[DatabaseConnection],
) -> None:
    for i, line in enumerate(lines, 1):
        for m in _JS_IMPORT_RE.finditer(line):
            pkg = m.group(1)
            if pkg in _JS_HTTP_LOOKUP:
                http_clients.append(HTTPClientUsage(
                    library=_JS_HTTP_LOOKUP[pkg], file_path=fp, line_number=i,
                ))
            for known_pkg, (db_type, lib_name) in _JS_DB_LOOKUP.items():
                if pkg == known_pkg or pkg.startswith(known_pkg + "/"):
                    databases.append(DatabaseConnection(
                        db_type=db_type, library=lib_name, file_path=fp, line_number=i,
                    ))


# ---------------------------------------------------------------------------
# Line-by-line pattern detection
# ---------------------------------------------------------------------------

def _detect_file_io(lines: list[str], fp: str, file_io: list[FileIOOperation]) -> None:
    for i, line in enumerate(lines, 1):
        for pat in FILE_WRITE_PATTERNS:
            if pat.search(line):
                file_io.append(FileIOOperation(
                    operation="write", pattern=pat.pattern, file_path=fp,
                    line_number=i, context=line.strip()[:120],
                ))
                break
        for pat in FILE_READ_PATTERNS:
            if pat.search(line):
                file_io.append(FileIOOperation(
                    operation="read", pattern=pat.pattern, file_path=fp,
                    line_number=i, context=line.strip()[:120],
                ))
                break


def _detect_http_urls(lines: list[str], fp: str, http_clients: list[HTTPClientUsage]) -> None:
    for i, line in enumerate(lines, 1):
        for m in URL_PATTERN.finditer(line):
            url = m.group(0).strip("'\"")
            # Skip common non-data URLs
            if any(skip in url for skip in ("localhost", "127.0.0.1", "example.com", "schema.org")):
                continue
            http_clients.append(HTTPClientUsage(
                library="url_reference", file_path=fp, line_number=i,
                url_hint=url[:200], context=line.strip()[:120],
            ))


def _detect_aws_services(lines: list[str], fp: str, cloud_services: list[CloudServiceUsage]) -> None:
    for i, line in enumerate(lines, 1):
        for pat in AWS_SERVICE_PATTERNS:
            m = pat.search(line)
            if m:
                # Extract service name from the pattern match
                svc = m.group(0).split("'")[1] if "'" in m.group(0) else m.group(0).split('"')[1]
                cloud_services.append(CloudServiceUsage(
                    provider="aws", service=svc, library="boto3",
                    file_path=fp, line_number=i,
                ))


# ---------------------------------------------------------------------------
# Build external services and data flows from detected connections
# ---------------------------------------------------------------------------

def _build_ai_provider_flows(
    scan: CodeScanResult,
    services: list[ExternalService],
    flows: list[DataFlow],
) -> None:
    seen: set[str] = set()
    for imp in scan.ai_imports:
        if imp.library in seen:
            continue
        seen.add(imp.library)

        gdpr = AI_PROVIDER_GDPR.get(imp.library)
        if not gdpr:
            continue

        services.append(ExternalService(
            name=gdpr["name"],
            category="ai_provider",
            service_type=gdpr["service_type"],
            file_path=imp.file_path,
            line_number=imp.line_number,
            module_path=imp.module_path,
            data_direction="bidirectional",
        ))
        flows.append(DataFlow(
            source="application",
            destination=gdpr["name"],
            data_type=gdpr["data_type"],
            purpose=gdpr["purpose"],
            gdpr_role=gdpr["gdpr_role"],
            file_path=imp.file_path,
            line_number=imp.line_number,
            contains_pii=gdpr["contains_pii"],
        ))


def _build_vector_db_flows(
    scan: CodeScanResult,
    services: list[ExternalService],
    flows: list[DataFlow],
) -> None:
    seen: set[str] = set()
    for vdb in scan.vector_dbs:
        if vdb.db_name in seen:
            continue
        seen.add(vdb.db_name)

        gdpr = VECTOR_DB_GDPR.get(vdb.db_name)
        if not gdpr:
            continue

        services.append(ExternalService(
            name=gdpr["name"],
            category="vector_db",
            service_type=gdpr["service_type"],
            file_path=vdb.file_path,
            line_number=vdb.line_number,
            module_path=vdb.module_path,
            data_direction="bidirectional",
        ))
        flows.append(DataFlow(
            source="application",
            destination=gdpr["name"],
            data_type=gdpr["data_type"],
            purpose=gdpr["purpose"],
            gdpr_role=gdpr["gdpr_role"],
            file_path=vdb.file_path,
            line_number=vdb.line_number,
            contains_pii=gdpr["contains_pii"],
        ))


def _build_database_services(
    databases: list[DatabaseConnection],
    services: list[ExternalService],
    flows: list[DataFlow],
) -> None:
    seen: set[str] = set()
    for db in databases:
        key = f"{db.db_type}_{db.library}"
        if key in seen:
            continue
        seen.add(key)

        name = f"{db.db_type.title()} ({db.library})"
        services.append(ExternalService(
            name=name,
            category="database",
            service_type="self_hosted",
            file_path=db.file_path,
            line_number=db.line_number,
            module_path=db.library,
            data_direction="bidirectional",
        ))
        flows.append(DataFlow(
            source="application",
            destination=name,
            data_type="user_data",
            purpose="storage",
            gdpr_role="controller",
            file_path=db.file_path,
            line_number=db.line_number,
            contains_pii="likely",
        ))


def _build_cloud_services(
    cloud_svcs: list[CloudServiceUsage],
    services: list[ExternalService],
    flows: list[DataFlow],
) -> None:
    seen: set[str] = set()
    for cs in cloud_svcs:
        key = f"{cs.provider}_{cs.service}"
        if key in seen:
            continue
        seen.add(key)

        name = f"{cs.provider.upper()} {cs.service}"
        services.append(ExternalService(
            name=name,
            category="cloud",
            service_type="cloud_api",
            file_path=cs.file_path,
            line_number=cs.line_number,
            module_path=cs.library,
            data_direction="bidirectional",
        ))
        flows.append(DataFlow(
            source="application",
            destination=name,
            data_type="user_data",
            purpose="storage",
            gdpr_role="processor",
            file_path=cs.file_path,
            line_number=cs.line_number,
            contains_pii="unknown",
        ))


def _build_http_services(
    http_clients: list[HTTPClientUsage],
    services: list[ExternalService],
    flows: list[DataFlow],
) -> None:
    seen: set[str] = set()
    for hc in http_clients:
        if not hc.url_hint or hc.library == "url_reference":
            continue
        # Extract domain from URL
        domain = _extract_domain(hc.url_hint)
        if not domain or domain in seen:
            continue
        seen.add(domain)

        services.append(ExternalService(
            name=domain,
            category="http_api",
            service_type="cloud_api",
            file_path=hc.file_path,
            line_number=hc.line_number,
            module_path=hc.library,
            data_direction="outbound",
        ))
        flows.append(DataFlow(
            source="application",
            destination=domain,
            data_type="user_data",
            purpose="api_call",
            gdpr_role="processor",
            file_path=hc.file_path,
            line_number=hc.line_number,
            contains_pii="unknown",
        ))


def _extract_domain(url: str) -> str:
    """Extract domain from a URL string."""
    url = url.strip("'\"")
    if "://" in url:
        url = url.split("://", 1)[1]
    return url.split("/")[0].split(":")[0]
