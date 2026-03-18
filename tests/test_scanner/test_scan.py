"""Tests for top-level codebase scanner orchestrator."""

from pathlib import Path

from ai_trace_auditor.scanner.scan import scan_codebase

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_codebase"


class TestFullCodebaseScan:
    def test_returns_code_scan_result(self):
        result = scan_codebase(FIXTURES)
        assert result.scanned_dir == str(FIXTURES)
        assert result.file_count > 0

    def test_scan_duration_is_positive(self):
        result = scan_codebase(FIXTURES)
        assert result.scan_duration_ms >= 0

    def test_detects_ai_imports_across_languages(self):
        result = scan_codebase(FIXTURES)
        providers = result.providers
        assert "anthropic" in providers
        assert "openai" in providers

    def test_detects_langchain(self):
        result = scan_codebase(FIXTURES)
        assert "langchain" in result.providers

    def test_detects_models_across_languages(self):
        result = scan_codebase(FIXTURES)
        models = result.models
        assert any("claude" in m for m in models)
        assert any("gpt" in m for m in models)

    def test_detects_vector_dbs(self):
        result = scan_codebase(FIXTURES)
        db_names = {vdb.db_name for vdb in result.vector_dbs}
        assert "chromadb" in db_names
        assert "pinecone" in db_names

    def test_detects_training_data(self):
        result = scan_codebase(FIXTURES)
        assert len(result.training_data_refs) >= 1

    def test_detects_eval_scripts(self):
        result = scan_codebase(FIXTURES)
        assert len(result.eval_scripts) >= 1

    def test_detects_deployment_configs(self):
        result = scan_codebase(FIXTURES)
        config_types = {dc.config_type for dc in result.deployment_configs}
        assert "dockerfile" in config_types
        assert "compose" in config_types

    def test_dockerfile_contains_ai_deps(self):
        result = scan_codebase(FIXTURES)
        dockerfiles = [
            dc for dc in result.deployment_configs if dc.config_type == "dockerfile"
        ]
        assert len(dockerfiles) >= 1
        assert dockerfiles[0].contains_ai_deps is True

    def test_detects_endpoints(self):
        result = scan_codebase(FIXTURES)
        routes = [ep.route for ep in result.ai_endpoints]
        assert "/api/chat" in routes
        assert "/api/generate" in routes

    def test_has_ai_usage_property(self):
        result = scan_codebase(FIXTURES)
        assert result.has_ai_usage is True


class TestSkipDirectories:
    def test_skips_node_modules(self):
        result = scan_codebase(FIXTURES)
        # The node_modules/fake_package.js file has 'openai' import
        # but should NOT be scanned
        for imp in result.ai_imports:
            assert "node_modules" not in imp.file_path

    def test_no_model_refs_from_node_modules(self):
        result = scan_codebase(FIXTURES)
        for ref in result.model_references:
            assert "node_modules" not in ref.file_path


class TestDeduplication:
    def test_no_duplicate_imports_per_file(self):
        result = scan_codebase(FIXTURES)
        seen = set()
        for imp in result.ai_imports:
            key = (imp.library, imp.file_path)
            assert key not in seen, f"Duplicate import: {imp.library} in {imp.file_path}"
            seen.add(key)

    def test_no_duplicate_model_refs_per_file(self):
        result = scan_codebase(FIXTURES)
        seen = set()
        for ref in result.model_references:
            key = (ref.model_id, ref.file_path)
            assert key not in seen, f"Duplicate model ref: {ref.model_id} in {ref.file_path}"
            seen.add(key)


class TestEdgeCases:
    def test_handles_broken_python_file(self):
        """Scanner should not crash on syntax errors."""
        result = scan_codebase(FIXTURES)
        # broken.py should still yield model refs via regex fallback
        model_ids = [ref.model_id for ref in result.model_references]
        assert "claude-3-opus-20240229" in model_ids

    def test_empty_file_does_not_break_scan(self):
        """Scanner should handle empty/comment-only files."""
        result = scan_codebase(FIXTURES)
        assert result.file_count > 0  # empty.py is counted
