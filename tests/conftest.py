"""Shared test fixtures."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def otel_trace_path() -> Path:
    return FIXTURES_DIR / "otel_chat_trace.json"


@pytest.fixture
def langfuse_trace_path() -> Path:
    return FIXTURES_DIR / "langfuse_export.json"


@pytest.fixture
def raw_api_path() -> Path:
    return FIXTURES_DIR / "raw_api_log.jsonl"


@pytest.fixture
def requirements_dir() -> Path:
    return Path(__file__).parent.parent / "requirements"


@pytest.fixture
def sample_codebase_dir() -> Path:
    return FIXTURES_DIR / "sample_codebase"
