"""Parity and divergence tests for the optional native scanning core.

Two things are checked here:

1. Where the native path is meant to agree with the pure-Python scanners, it
   agrees exactly — same libraries, same files, same line numbers.
2. Where it is meant to differ, it differs in the *specific documented way*.
   Every entry in `native.KNOWN_DIVERGENCES` has a test below. A divergence
   with no test, or a test with no entry, means someone changed behaviour
   without saying so.

The whole module skips when `aitrace-core` is not installed, so the pure-Python
install stays fully testable.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ai_trace_auditor.scanner import native
from ai_trace_auditor.scanner.js_scanner import scan_js_file
from ai_trace_auditor.scanner.python_scanner import scan_python_file

pytestmark = pytest.mark.skipif(
    not native.is_available(), reason="aitrace-core native extension not installed"
)


def write(tmp_path: Path, name: str, source: str) -> Path:
    """Write a dedented source file into the temp tree."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    return path


def native_scan(tmp_path: Path) -> dict[Path, dict]:
    scans, _count = native.scan_all_files(tmp_path)
    return scans


def libraries(result: dict, key: str = "ai_imports") -> set[str]:
    attr = "library" if key == "ai_imports" else "db_name"
    return {getattr(item, attr) for item in result[key]}


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


def test_ordinary_python_imports_agree_exactly(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "app.py",
        """
        import anthropic
        from openai import OpenAI
        import chromadb
        """,
    )
    expected = scan_python_file(path)
    actual = native_scan(tmp_path)[path]

    assert libraries(actual) == libraries(expected) == {"anthropic", "openai"}
    assert libraries(actual, "vector_dbs") == libraries(expected, "vector_dbs")
    assert [i.line_number for i in actual["ai_imports"]] == [
        i.line_number for i in expected["ai_imports"]
    ]


def test_training_data_and_eval_metrics_agree(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "train.py",
        """
        import anthropic
        from datasets import load_dataset
        from sklearn.metrics import accuracy_score, f1_score

        ds = load_dataset("c4")
        score = accuracy_score(y, yhat)
        """,
    )
    expected = scan_python_file(path)
    actual = native_scan(tmp_path)[path]

    assert [(t.pattern, t.line_number) for t in actual["training_data"]] == [
        (t.pattern, t.line_number) for t in expected["training_data"]
    ]
    assert [e.metrics_detected for e in actual["eval_metrics"]] == [
        e.metrics_detected for e in expected["eval_metrics"]
    ]


def test_byok_api_url_detection_agrees(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "byok.py",
        """
        import requests

        def call():
            return requests.post("https://api.anthropic.com/v1/messages")
        """,
    )
    expected = scan_python_file(path)
    actual = native_scan(tmp_path)[path]

    assert [(i.library, i.line_number) for i in actual["ai_imports"]] == [
        (i.library, i.line_number) for i in expected["ai_imports"]
    ]


def test_model_identifiers_agree(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "models.py",
        """
        import anthropic

        MODEL = "claude-sonnet-4-20250514"
        FALLBACK = "gpt-4o-mini"
        """,
    )
    expected = scan_python_file(path)
    actual = native_scan(tmp_path)[path]

    assert {m.model_id for m in actual["model_refs"]} == {
        m.model_id for m in expected["model_refs"]
    }


def test_files_with_no_findings_are_absent_not_wrong(tmp_path: Path) -> None:
    write(tmp_path, "plain.py", "x = 1\n")
    write(tmp_path, "app.py", "import anthropic\n")
    scans = native_scan(tmp_path)

    # Files with nothing to report are dropped before crossing the FFI
    # boundary; the ones that remain must still be correct.
    assert tmp_path / "app.py" in scans
    assert libraries(scans[tmp_path / "app.py"]) == {"anthropic"}


# ---------------------------------------------------------------------------
# Documented divergences — one test per KNOWN_DIVERGENCES entry
# ---------------------------------------------------------------------------


def test_py_relative_imports_no_longer_false_positive(tmp_path: Path) -> None:
    """`from .openai import X` is a local submodule, not the OpenAI SDK."""
    path = write(
        tmp_path,
        "pkg/__init__.py",
        """
        from .openai import LocalGenerator
        from .anthropic import OtherThing
        """,
    )
    expected = scan_python_file(path)
    actual = native_scan(tmp_path)[path]

    # The bug being fixed: the pure-Python scanner reports both as SDK usage.
    assert libraries(expected) == {"openai", "anthropic"}
    # The native path correctly reports neither.
    assert libraries(actual) == set()


def test_py_absolute_imports_still_match_after_the_relative_fix(tmp_path: Path) -> None:
    """The relative-import fix must not suppress genuine absolute imports."""
    path = write(
        tmp_path,
        "pkg/real.py",
        """
        from openai import OpenAI
        from .openai import LocalThing
        """,
    )
    actual = native_scan(tmp_path)[path]
    assert libraries(actual) == {"openai"}
    assert [i.line_number for i in actual["ai_imports"]] == [1]


def test_py_syntax_error_recovery_finds_imports(tmp_path: Path) -> None:
    """A file that fails ast.parse still yields its imports."""
    path = write(
        tmp_path,
        "template.py",
        """
        from crewai import Agent, Crew
        import anthropic


        @CrewBase
        class {{crew_name}}():
            pass
        """,
    )
    expected = scan_python_file(path)
    actual = native_scan(tmp_path)[path]

    # The bug being fixed: SyntaxError wipes out import detection entirely.
    assert expected["ai_imports"] == []
    assert libraries(actual) == {"crewai", "anthropic"}


def test_py_finding_ordering_is_source_order(tmp_path: Path) -> None:
    """Repeated imports of one library keep the earliest line, not the AST's."""
    path = write(
        tmp_path,
        "repeat.py",
        """
        import os
        from anthropic import Anthropic

        def f():
            from anthropic.types import Message
            return Message
        """,
    )
    actual = native_scan(tmp_path)[path]
    lines = [i.line_number for i in actual["ai_imports"] if i.library == "anthropic"]
    assert lines == sorted(lines), "findings must be reported in source order"
    assert lines[0] == 2


def test_js_comments_are_not_imports(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "client.js",
        """
        // import Anthropic from '@anthropic-ai/sdk';
        /* const OpenAI = require('openai'); */
        const notCode = "require('cohere-ai')";
        import Real from '@pinecone-database/pinecone';
        """,
    )
    expected = scan_js_file(path)
    actual = native_scan(tmp_path)[path]

    # The regex scanner cannot tell code from a comment.
    assert {"anthropic", "openai"} & libraries(expected)
    # tree-sitter reports only the real import (a vector DB, not an AI SDK).
    assert libraries(actual) == set()
    assert libraries(actual, "vector_dbs") == {"pinecone"}


def test_js_multiline_imports_are_found(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "multi.ts",
        """
        import {
          Anthropic,
          type Message,
        } from '@anthropic-ai/sdk';
        """,
    )
    expected = scan_js_file(path)
    actual = native_scan(tmp_path)[path]

    assert libraries(expected) == set(), "regex scanner misses multi-line imports"
    assert libraries(actual) == {"anthropic"}


def test_js_model_refs_come_from_literals_not_lines(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "models.js",
        """
        import Anthropic from '@anthropic-ai/sdk';
        // we used to default to claude-3-opus-20240229 here
        const MODEL = 'claude-sonnet-4-20250514';
        """,
    )
    expected = scan_js_file(path)
    actual = native_scan(tmp_path)[path]

    assert "claude-3-opus-20240229" in {m.model_id for m in expected["model_refs"]}
    assert {m.model_id for m in actual["model_refs"]} == {"claude-sonnet-4-20250514"}


#: Explicit link from each documented divergence to the test that pins it.
#: Spelled out rather than matched by name so that renaming a test cannot
#: silently orphan a divergence.
DIVERGENCE_TESTS: dict[str, str] = {
    "py_relative_imports": "test_py_relative_imports_no_longer_false_positive",
    "py_syntax_error_recovery": "test_py_syntax_error_recovery_finds_imports",
    "py_finding_ordering": "test_py_finding_ordering_is_source_order",
    "js_comments": "test_js_comments_are_not_imports",
    "js_multiline_imports": "test_js_multiline_imports_are_found",
    "js_model_refs_from_literals": "test_js_model_refs_come_from_literals_not_lines",
}


def test_every_documented_divergence_has_a_test() -> None:
    """Guards the docs against drifting away from the behaviour, both ways."""
    assert set(DIVERGENCE_TESTS) == set(native.KNOWN_DIVERGENCES), (
        "KNOWN_DIVERGENCES and DIVERGENCE_TESTS disagree: "
        f"undocumented={set(DIVERGENCE_TESTS) - set(native.KNOWN_DIVERGENCES)}, "
        f"untested={set(native.KNOWN_DIVERGENCES) - set(DIVERGENCE_TESTS)}"
    )
    for key, test_name in DIVERGENCE_TESTS.items():
        assert test_name in globals(), f"{key}: missing test {test_name}"
