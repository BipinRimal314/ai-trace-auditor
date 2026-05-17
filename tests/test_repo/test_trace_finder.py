"""Tests for trace artifact discovery."""

from __future__ import annotations

import json
from pathlib import Path

from ai_trace_auditor.repo.trace_finder import find_trace_artifacts


def _write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)


def test_finds_otel_shaped_json(tmp_path: Path):
    otel_doc = {"resourceSpans": [{"scopeSpans": [{"spans": []}]}]}
    _write(tmp_path / "traces.json", json.dumps(otel_doc))

    artifacts = find_trace_artifacts(tmp_path)

    assert len(artifacts) == 1
    assert artifacts[0].shape == "otel"
    assert artifacts[0].path.name == "traces.json"


def test_finds_langfuse_export(tmp_path: Path):
    lf_doc = [
        {"id": "trace-1", "name": "chat", "observations": [{"type": "GENERATION"}]}
    ]
    _write(tmp_path / "exports" / "langfuse.json", json.dumps(lf_doc))

    artifacts = find_trace_artifacts(tmp_path)

    assert len(artifacts) == 1
    assert artifacts[0].shape == "langfuse"


def test_finds_chat_jsonl(tmp_path: Path):
    line = json.dumps({"messages": [{"role": "user", "content": "hi"}], "model": "gpt-4"})
    _write(tmp_path / "calls.jsonl", line + "\n" + line + "\n")

    artifacts = find_trace_artifacts(tmp_path)

    assert len(artifacts) == 1
    assert artifacts[0].shape == "chat_jsonl"


def test_ignores_unrelated_json(tmp_path: Path):
    _write(tmp_path / "package.json", json.dumps({"name": "pkg", "version": "1.0"}))
    _write(tmp_path / "tsconfig.json", json.dumps({"compilerOptions": {}}))

    artifacts = find_trace_artifacts(tmp_path)

    assert artifacts == []


def test_skips_files_over_size_cap(tmp_path: Path):
    big = "x" * 6_000_000
    _write(tmp_path / "huge.json", json.dumps({"resourceSpans": [], "padding": big}))

    artifacts = find_trace_artifacts(tmp_path, max_file_bytes=5_000_000)

    assert artifacts == []


def test_handles_malformed_json_without_crashing(tmp_path: Path):
    _write(tmp_path / "broken.json", "{not valid json")
    _write(tmp_path / "broken.jsonl", "not\nvalid\njson\n")

    artifacts = find_trace_artifacts(tmp_path)

    assert artifacts == []


def test_finds_multiple_artifacts(tmp_path: Path):
    _write(
        tmp_path / "a.json",
        json.dumps({"resourceSpans": []}),
    )
    _write(
        tmp_path / "subdir" / "b.jsonl",
        json.dumps({"messages": [{"role": "user", "content": "x"}]}) + "\n",
    )

    artifacts = find_trace_artifacts(tmp_path)

    shapes = {a.shape for a in artifacts}
    assert shapes == {"otel", "chat_jsonl"}
