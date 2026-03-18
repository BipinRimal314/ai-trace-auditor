"""Detection patterns for AI frameworks, models, and infrastructure.

Add new SDKs or model patterns here — no logic changes needed.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Python AI SDK imports: library_name -> list of top-level module names
# ---------------------------------------------------------------------------
AI_SDK_IMPORTS: dict[str, list[str]] = {
    "anthropic": ["anthropic"],
    "openai": ["openai"],
    "google_genai": ["google.generativeai", "vertexai", "google.cloud.aiplatform"],
    "langchain": [
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langchain_anthropic",
        "langchain_community",
        "langchain_google_genai",
        "langgraph",
    ],
    "huggingface": ["transformers", "datasets", "huggingface_hub", "diffusers"],
    "cohere": ["cohere"],
    "mistral": ["mistralai"],
    "llama_index": ["llama_index"],
    "autogen": ["autogen", "pyautogen"],
    "crewai": ["crewai"],
}

# ---------------------------------------------------------------------------
# Vector database imports
# ---------------------------------------------------------------------------
VECTOR_DB_IMPORTS: dict[str, list[str]] = {
    "pinecone": ["pinecone"],
    "weaviate": ["weaviate"],
    "qdrant": ["qdrant_client"],
    "chromadb": ["chromadb"],
    "milvus": ["pymilvus"],
    "pgvector": ["pgvector"],
    "faiss": ["faiss"],
    "lancedb": ["lancedb"],
}

# ---------------------------------------------------------------------------
# Model identifier patterns (compiled regex)
# ---------------------------------------------------------------------------
MODEL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"claude-[\w.-]+"),
    re.compile(r"gpt-4[\w.-]*"),
    re.compile(r"gpt-3\.5[\w.-]*"),
    re.compile(r"o[134]-[\w.-]+"),
    re.compile(r"gemini-[\w.-]+"),
    re.compile(r"llama-[\w.-]+"),
    re.compile(r"mistral-[\w.-]+"),
    re.compile(r"mixtral-[\w.-]+"),
    re.compile(r"command-[\w.-]+"),
    re.compile(r"embed-[\w.-]+"),
    re.compile(r"text-embedding-[\w.-]+"),
    re.compile(r"whisper-[\w.-]+"),
    re.compile(r"dall-e-[\w.-]+"),
    re.compile(r"stable-diffusion-[\w.-]+"),
]

# ---------------------------------------------------------------------------
# Training data loading patterns (regex for line-by-line scan)
# ---------------------------------------------------------------------------
TRAINING_DATA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"load_dataset\s*\("),
    re.compile(r"\.read_csv\s*\("),
    re.compile(r"\.read_json\s*\("),
    re.compile(r"\.read_jsonl\s*\("),
    re.compile(r"\.read_parquet\s*\("),
    re.compile(r"pd\.read_"),
    re.compile(r"datasets\.load"),
    re.compile(r"from_pretrained\s*\("),
    re.compile(r"load_from_disk\s*\("),
]

# ---------------------------------------------------------------------------
# Evaluation metric patterns
# ---------------------------------------------------------------------------
EVAL_METRIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"accuracy_score"),
    re.compile(r"f1_score"),
    re.compile(r"precision_score"),
    re.compile(r"recall_score"),
    re.compile(r"roc_auc_score"),
    re.compile(r"mean_squared_error"),
    re.compile(r"mean_absolute_error"),
    re.compile(r"classification_report"),
    re.compile(r"confusion_matrix"),
    re.compile(r"evaluate\s*\("),
    re.compile(r"bleu_score"),
    re.compile(r"rouge_score"),
    re.compile(r"perplexity"),
]

# ---------------------------------------------------------------------------
# Deployment file patterns: type -> glob patterns
# ---------------------------------------------------------------------------
DEPLOYMENT_FILES: dict[str, list[str]] = {
    "dockerfile": ["Dockerfile", "Dockerfile.*"],
    "compose": [
        "docker-compose*.yml",
        "docker-compose*.yaml",
        "compose*.yml",
        "compose*.yaml",
    ],
    "kubernetes": ["k8s/*.yaml", "k8s/*.yml", "kubernetes/*.yaml", "kubernetes/*.yml"],
    "terraform": ["*.tf"],
}

# ---------------------------------------------------------------------------
# API framework route patterns
# ---------------------------------------------------------------------------
API_FRAMEWORK_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "fastapi": [
        re.compile(r"@(?:app|router)\.(get|post|put|delete|patch)\s*\("),
    ],
    "flask": [
        re.compile(r"@(?:app|blueprint)\.route\s*\("),
    ],
}

# ---------------------------------------------------------------------------
# JavaScript/TypeScript AI SDK imports
# ---------------------------------------------------------------------------
JS_AI_IMPORTS: dict[str, list[str]] = {
    "anthropic": ["@anthropic-ai/sdk", "anthropic"],
    "openai": ["openai"],
    "google_genai": ["@google/generative-ai", "@google-cloud/aiplatform"],
    "langchain": ["langchain", "@langchain/core", "@langchain/openai", "@langchain/anthropic"],
    "huggingface": ["@huggingface/inference", "@huggingface/transformers"],
    "cohere": ["cohere-ai"],
    "vercel_ai": ["ai", "@ai-sdk/anthropic", "@ai-sdk/openai", "@ai-sdk/google"],
}

JS_VECTOR_DB_IMPORTS: dict[str, list[str]] = {
    "pinecone": ["@pinecone-database/pinecone"],
    "weaviate": ["weaviate-ts-client", "weaviate-client"],
    "qdrant": ["@qdrant/js-client-rest"],
    "chromadb": ["chromadb"],
    "supabase_vector": ["@supabase/supabase-js"],
}

# ---------------------------------------------------------------------------
# File extensions and skip directories
# ---------------------------------------------------------------------------
PYTHON_EXTENSIONS: frozenset[str] = frozenset({".py"})

JS_EXTENSIONS: frozenset[str] = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build",
    ".next", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "env",
    ".eggs", "*.egg-info", "coverage", ".coverage", "htmlcov",
})
