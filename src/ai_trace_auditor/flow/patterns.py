"""Detection patterns for external services, HTTP clients, databases, cloud SDKs."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# HTTP client libraries (Python)
# ---------------------------------------------------------------------------
HTTP_CLIENT_IMPORTS: dict[str, list[str]] = {
    "requests": ["requests"],
    "httpx": ["httpx"],
    "aiohttp": ["aiohttp"],
    "urllib3": ["urllib3"],
}

# ---------------------------------------------------------------------------
# HTTP client libraries (JavaScript/TypeScript)
# ---------------------------------------------------------------------------
JS_HTTP_CLIENT_IMPORTS: dict[str, list[str]] = {
    "axios": ["axios"],
    "node-fetch": ["node-fetch"],
    "got": ["got"],
    "ky": ["ky"],
    "undici": ["undici"],
}

# ---------------------------------------------------------------------------
# Database libraries (Python)
# ---------------------------------------------------------------------------
DATABASE_IMPORTS: dict[str, tuple[str, list[str]]] = {
    # db_type -> (library_name, import_modules)
    "postgresql": ("psycopg2", ["psycopg2", "psycopg", "asyncpg"]),
    "postgresql_sa": ("sqlalchemy", ["sqlalchemy"]),
    "mysql": ("pymysql", ["pymysql", "mysql.connector", "aiomysql"]),
    "mongodb": ("pymongo", ["pymongo", "motor"]),
    "redis": ("redis", ["redis", "aioredis"]),
    "sqlite": ("sqlite3", ["sqlite3", "aiosqlite"]),
    "elasticsearch": ("elasticsearch", ["elasticsearch"]),
}

# ---------------------------------------------------------------------------
# Database libraries (JavaScript/TypeScript)
# ---------------------------------------------------------------------------
JS_DATABASE_IMPORTS: dict[str, tuple[str, list[str]]] = {
    "postgresql": ("pg", ["pg", "@prisma/client", "drizzle-orm", "knex"]),
    "mongodb": ("mongoose", ["mongoose", "mongodb"]),
    "redis": ("ioredis", ["ioredis", "redis"]),
    "sqlite": ("better-sqlite3", ["better-sqlite3", "sql.js"]),
}

# ---------------------------------------------------------------------------
# Cloud service SDKs (Python)
# ---------------------------------------------------------------------------
CLOUD_SDK_IMPORTS: dict[str, dict[str, list[str]]] = {
    "aws": {
        "s3": ["boto3"],  # detected by service name in code
        "bedrock": ["boto3"],
        "sagemaker": ["sagemaker"],
        "lambda": ["boto3"],
    },
    "gcp": {
        "vertex_ai": ["vertexai", "google.cloud.aiplatform"],
        "cloud_storage": ["google.cloud.storage"],
        "bigquery": ["google.cloud.bigquery"],
        "firestore": ["google.cloud.firestore"],
    },
    "azure": {
        "openai": ["openai"],  # Azure OpenAI uses same SDK
        "blob_storage": ["azure.storage.blob"],
        "cosmos_db": ["azure.cosmos"],
    },
}

# AWS service detection patterns (in boto3 client/resource calls)
AWS_SERVICE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"""client\s*\(\s*['"]s3['"]"""),
    re.compile(r"""client\s*\(\s*['"]bedrock['"]"""),
    re.compile(r"""client\s*\(\s*['"]bedrock-runtime['"]"""),
    re.compile(r"""client\s*\(\s*['"]sagemaker['"]"""),
    re.compile(r"""client\s*\(\s*['"]lambda['"]"""),
    re.compile(r"""client\s*\(\s*['"]dynamodb['"]"""),
    re.compile(r"""resource\s*\(\s*['"]s3['"]"""),
    re.compile(r"""resource\s*\(\s*['"]dynamodb['"]"""),
]

# ---------------------------------------------------------------------------
# File I/O patterns that suggest data processing
# ---------------------------------------------------------------------------
FILE_WRITE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.to_csv\s*\("),
    re.compile(r"\.to_json\s*\("),
    re.compile(r"\.to_parquet\s*\("),
    re.compile(r"\.save\s*\("),
    re.compile(r"\.write\s*\("),
    re.compile(r"\.dump\s*\("),
    re.compile(r"json\.dump\s*\("),
    re.compile(r"pickle\.dump\s*\("),
    re.compile(r"torch\.save\s*\("),
]

FILE_READ_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"open\s*\(.*['\"]r['\"]"),
    re.compile(r"\.read\s*\("),
    re.compile(r"json\.load\s*\("),
    re.compile(r"pickle\.load\s*\("),
    re.compile(r"torch\.load\s*\("),
]

# ---------------------------------------------------------------------------
# URL extraction from code (for HTTP client calls)
# ---------------------------------------------------------------------------
URL_PATTERN = re.compile(r"""['"]https?://[^'"]+['"]""")

# ---------------------------------------------------------------------------
# AI provider -> GDPR data classification
# ---------------------------------------------------------------------------
AI_PROVIDER_GDPR: dict[str, dict[str, str | bool]] = {
    "anthropic": {
        "name": "Anthropic API",
        "service_type": "cloud_api",
        "gdpr_role": "processor",
        "gdpr_role_note": "typically processor for customer data; verify per Anthropic DPA",
        "data_type": "prompts",
        "purpose": "inference",
        "contains_pii": "likely",
        "provider_jurisdiction": "US",
        "requires_transfer_safeguards": True,
    },
    "openai": {
        "name": "OpenAI API",
        "service_type": "cloud_api",
        "gdpr_role": "processor",
        "gdpr_role_note": "typically processor for customer data; verify per OpenAI DPA",
        "data_type": "prompts",
        "purpose": "inference",
        "contains_pii": "likely",
        "provider_jurisdiction": "US",
        "requires_transfer_safeguards": True,
    },
    "google_genai": {
        "name": "Google Generative AI",
        "service_type": "cloud_api",
        "gdpr_role": "processor",
        "gdpr_role_note": "typically processor for customer data; verify per Google Cloud DPA",
        "data_type": "prompts",
        "purpose": "inference",
        "contains_pii": "likely",
        "provider_jurisdiction": "US",
        "requires_transfer_safeguards": True,
    },
    "cohere": {
        "name": "Cohere API",
        "service_type": "cloud_api",
        "gdpr_role": "processor",
        "gdpr_role_note": "typically processor for customer data; verify per Cohere DPA",
        "data_type": "prompts",
        "purpose": "inference",
        "contains_pii": "likely",
        "provider_jurisdiction": "CA",
        "requires_transfer_safeguards": True,
    },
    "huggingface": {
        "name": "HuggingFace",
        "service_type": "cloud_api",
        "gdpr_role": "processor",
        "gdpr_role_note": "role depends on usage: Inference API is processor; local models have no GDPR transfer",
        "data_type": "model_data",
        "purpose": "inference",
        "contains_pii": "unknown",
        "provider_jurisdiction": "US",
        "requires_transfer_safeguards": True,
    },
}

VECTOR_DB_GDPR: dict[str, dict[str, str | bool]] = {
    "pinecone": {
        "name": "Pinecone",
        "service_type": "cloud_api",
        "gdpr_role": "processor",
        "gdpr_role_note": "typically processor; verify per Pinecone DPA",
        "data_type": "embeddings",
        "purpose": "storage",
        "contains_pii": "likely",
        "provider_jurisdiction": "US",
        "requires_transfer_safeguards": True,
    },
    "weaviate": {
        "name": "Weaviate",
        "service_type": "managed",
        "gdpr_role": "processor",
        "gdpr_role_note": "processor if using Weaviate Cloud; controller if self-hosted",
        "data_type": "embeddings",
        "purpose": "storage",
        "contains_pii": "likely",
        "provider_jurisdiction": "NL",
        "requires_transfer_safeguards": False,
    },
    "qdrant": {
        "name": "Qdrant",
        "service_type": "managed",
        "gdpr_role": "processor",
        "gdpr_role_note": "processor if using Qdrant Cloud; controller if self-hosted",
        "data_type": "embeddings",
        "purpose": "storage",
        "contains_pii": "likely",
        "provider_jurisdiction": "DE",
        "requires_transfer_safeguards": False,
    },
    "chromadb": {
        "name": "ChromaDB",
        "service_type": "self_hosted",
        "gdpr_role": "controller",
        "gdpr_role_note": "",
        "data_type": "embeddings",
        "purpose": "storage",
        "contains_pii": "likely",
        "provider_jurisdiction": "self_hosted",
        "requires_transfer_safeguards": False,
    },
    "faiss": {
        "name": "FAISS",
        "service_type": "self_hosted",
        "gdpr_role": "controller",
        "gdpr_role_note": "",
        "data_type": "embeddings",
        "purpose": "storage",
        "contains_pii": "unknown",
        "provider_jurisdiction": "self_hosted",
        "requires_transfer_safeguards": False,
    },
}
