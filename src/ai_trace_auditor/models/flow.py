"""Data models for AI data flow mapping and GDPR/Article 13 compliance."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ExternalService(BaseModel):
    """An external service that receives or provides data."""

    name: str  # "Anthropic API", "Pinecone", "PostgreSQL"
    category: str  # "ai_provider", "vector_db", "database", "cache", "queue", "storage", "http_api"
    service_type: str  # "cloud_api", "self_hosted", "managed"
    file_path: str
    line_number: int
    module_path: str  # "anthropic", "pinecone", "sqlalchemy"
    data_direction: str  # "outbound", "inbound", "bidirectional"


class DataFlow(BaseModel):
    """A single data flow between the application and an external service."""

    source: str  # "user_input", "application", "database", "ai_provider"
    destination: str  # service name
    data_type: str  # "prompts", "embeddings", "user_data", "model_responses", "logs"
    purpose: str  # "inference", "storage", "training", "monitoring"
    gdpr_role: str  # "controller", "processor", "joint_controller", "sub_processor"
    gdpr_role_note: str = ""  # qualifier: "verify per provider DPA" or empty for definitive roles
    file_path: str
    line_number: int
    contains_pii: str = "unknown"  # "yes", "no", "unknown", "likely"
    requires_transfer_safeguards: bool = False  # True if provider is outside EEA
    provider_jurisdiction: str = ""  # "US", "EU", "self_hosted", etc.


class HTTPClientUsage(BaseModel):
    """An HTTP client call to an external service."""

    library: str  # "requests", "httpx", "aiohttp", "fetch", "axios"
    file_path: str
    line_number: int
    url_hint: str = ""  # extracted URL if available
    context: str = ""


class DatabaseConnection(BaseModel):
    """A database connection detected in code."""

    db_type: str  # "postgresql", "mysql", "mongodb", "sqlite", "redis"
    library: str  # "sqlalchemy", "psycopg2", "pymongo", "redis"
    file_path: str
    line_number: int


class FileIOOperation(BaseModel):
    """File I/O that may involve data processing."""

    operation: str  # "read", "write"
    pattern: str  # "open(", "to_csv", "to_json", etc.
    file_path: str
    line_number: int
    context: str = ""


class CloudServiceUsage(BaseModel):
    """Cloud service SDK usage (AWS, GCP, Azure)."""

    provider: str  # "aws", "gcp", "azure"
    service: str  # "s3", "bedrock", "vertex_ai", "blob_storage"
    library: str
    file_path: str
    line_number: int


class FlowScanResult(BaseModel):
    """Aggregated results from scanning for data flows."""

    scanned_dir: str
    file_count: int
    scan_duration_ms: int
    external_services: list[ExternalService] = []
    data_flows: list[DataFlow] = []
    http_clients: list[HTTPClientUsage] = []
    databases: list[DatabaseConnection] = []
    file_io: list[FileIOOperation] = []
    cloud_services: list[CloudServiceUsage] = []

    @property
    def service_names(self) -> list[str]:
        return sorted({s.name for s in self.external_services})

    @property
    def outbound_services(self) -> list[ExternalService]:
        return [s for s in self.external_services if s.data_direction in ("outbound", "bidirectional")]


class FlowDiagram(BaseModel):
    """A complete data flow diagram with GDPR annotations."""

    mermaid: str  # Mermaid diagram source
    services: list[ExternalService]
    flows: list[DataFlow]
    generated_at: datetime
    source_dir: str
    trace_enriched: bool = False


class RoPAEntry(BaseModel):
    """A single GDPR Article 30 Record of Processing Activities entry."""

    processing_activity: str
    purpose: str
    data_categories: str
    data_subjects: str
    recipients: str
    transfers: str
    retention: str = "[MANUAL INPUT REQUIRED]"
    security_measures: str = "[MANUAL INPUT REQUIRED]"


class RoPAReport(BaseModel):
    """GDPR Article 30 Record of Processing Activities."""

    entries: list[RoPAEntry]
    generated_at: datetime
    source_dir: str
    controller_name: str = "[MANUAL INPUT REQUIRED]"
    controller_contact: str = "[MANUAL INPUT REQUIRED]"
    dpo_contact: str = "[MANUAL INPUT REQUIRED]"
