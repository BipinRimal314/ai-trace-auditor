"""Tests for JavaScript/TypeScript source file scanner."""

from pathlib import Path

from ai_trace_auditor.scanner.js_scanner import scan_js_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


class TestJSImportDetection:
    def test_detects_anthropic_sdk(self):
        result = scan_js_file(FIXTURES / "api.ts")
        libraries = [imp.library for imp in result["ai_imports"]]
        assert "anthropic" in libraries

    def test_import_has_correct_module_path(self):
        result = scan_js_file(FIXTURES / "api.ts")
        anthropic_imports = [
            imp for imp in result["ai_imports"] if imp.library == "anthropic"
        ]
        assert len(anthropic_imports) >= 1
        assert anthropic_imports[0].module_path == "@anthropic-ai/sdk"

    def test_import_has_line_number(self):
        result = scan_js_file(FIXTURES / "api.ts")
        for imp in result["ai_imports"]:
            assert imp.line_number > 0


class TestJSVectorDBDetection:
    def test_detects_pinecone(self):
        result = scan_js_file(FIXTURES / "api.ts")
        db_names = [vdb.db_name for vdb in result["vector_dbs"]]
        assert "pinecone" in db_names


class TestJSModelDetection:
    def test_detects_claude_model_in_ts(self):
        result = scan_js_file(FIXTURES / "api.ts")
        model_ids = [ref.model_id for ref in result["model_refs"]]
        assert "claude-3-haiku-20240307" in model_ids

    def test_model_ref_has_context(self):
        result = scan_js_file(FIXTURES / "api.ts")
        refs = [r for r in result["model_refs"] if "claude" in r.model_id]
        assert len(refs) >= 1
        assert refs[0].context


class TestJSEndpointDetection:
    def test_detects_express_post(self):
        result = scan_js_file(FIXTURES / "api.ts")
        routes = [ep.route for ep in result["endpoints"]]
        assert "/api/generate" in routes

    def test_detects_express_get(self):
        result = scan_js_file(FIXTURES / "api.ts")
        routes = [ep.route for ep in result["endpoints"]]
        assert "/api/search" in routes

    def test_endpoint_framework_is_express(self):
        result = scan_js_file(FIXTURES / "api.ts")
        frameworks = {ep.framework for ep in result["endpoints"]}
        assert "express" in frameworks


class TestJSEdgeCases:
    def test_non_ai_file_returns_empty(self):
        result = scan_js_file(FIXTURES / "utils.ts")
        assert result["ai_imports"] == []
        assert result["model_refs"] == []
        assert result["endpoints"] == []

    def test_nonexistent_file_returns_empty(self):
        result = scan_js_file(Path("/nonexistent/file.ts"))
        assert result["ai_imports"] == []
