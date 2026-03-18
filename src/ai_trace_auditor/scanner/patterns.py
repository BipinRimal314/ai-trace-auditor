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
    # Anthropic: claude-3-opus-20240229, claude-sonnet-4-20250514, etc.
    # Require version/variant after "claude-" (digit, "opus", "sonnet", "haiku", "instant")
    re.compile(r"claude-(?:\d|opus|sonnet|haiku|instant|v\d)[\w.-]*"),
    # OpenAI: gpt-4o, gpt-3.5-turbo, o1-mini, o3-pro, etc.
    re.compile(r"gpt-4[\w.-]*"),
    re.compile(r"gpt-3\.5[\w.-]*"),
    re.compile(r"o[134]-(?:mini|pro|preview)[\w.-]*"),
    # Google: gemini-1.5-flash, gemini-2.5-pro, etc.
    # Require version number after "gemini-"
    re.compile(r"gemini-\d[\w.-]*"),
    # Meta: llama-2-70b, llama-3-8b-instruct, etc.
    # Require version number
    re.compile(r"llama-\d[\w.-]*"),
    # Mistral: mistral-7b, mistral-large-2407, etc.
    # Require size/version indicator
    re.compile(r"mistral-(?:\d|large|medium|small|tiny|embed|nemo)[\w.-]*"),
    re.compile(r"mixtral-[\w.-]+"),
    # Cohere: command-r-plus, command-a-03-2025, etc.
    # Require "r", "r-plus", "light", "nightly", "a-" or version after "command-"
    re.compile(r"command-(?:r|light|nightly|xlarge|medium|text|a-\d)[\w.-]*"),
    # Embeddings: embed-english-v3.0, embed-multilingual-v3.0, embed-v4, etc.
    # Require language or version after "embed-"
    re.compile(r"embed-(?:english|multilingual|v\d|text|\d)[\w.-]*"),
    re.compile(r"text-embedding-[\w.-]+"),
    # Audio/image models
    re.compile(r"whisper-[\w.-]+"),
    re.compile(r"dall-e-\d[\w.-]*"),
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

# ---------------------------------------------------------------------------
# Test file detection (model refs in test files are test data, not usage)
# ---------------------------------------------------------------------------
TEST_DIR_NAMES: frozenset[str] = frozenset({
    "test", "tests", "testing", "test_utils", "fixtures",
    "mocks", "mock", "stubs", "fakes", "conftest",
})

TEST_FILE_PREFIXES: tuple[str, ...] = ("test_", "tests_", "conftest")
TEST_FILE_SUFFIXES: tuple[str, ...] = ("_test.py", "_tests.py", "_spec.py", "_spec.ts", "_spec.js", ".test.ts", ".test.js", ".test.tsx", ".spec.ts", ".spec.js")

# ---------------------------------------------------------------------------
# Config/mapping file detection (model names in these are reference data)
# ---------------------------------------------------------------------------
CONFIG_FILE_NAMES: frozenset[str] = frozenset({
    "config.py", "settings.py", "constants.py", "defaults.py",
    "model_prices.py", "model_map.py", "model_config.py",
    "model_list.py", "supported_models.py", "cost_map.py",
})
