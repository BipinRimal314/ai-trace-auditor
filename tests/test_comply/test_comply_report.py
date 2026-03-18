"""Tests for the unified compliance report renderer."""

from pathlib import Path

from ai_trace_auditor.comply.runner import run_full_compliance
from ai_trace_auditor.reports.comply_report import ComplyReporter

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_CODEBASE = FIXTURES / "sample_codebase"


class TestComplyReporter:
    def _get_package(self):
        return run_full_compliance(SAMPLE_CODEBASE)

    def test_renders_without_error(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert isinstance(md, str)
        assert len(md) > 500

    def test_contains_title(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "EU AI Act Compliance Package" in md

    def test_contains_coverage_summary_table(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "Article 12" in md
        assert "Article 11" in md
        assert "Article 13" in md
        assert "GDPR Article 30" in md

    def test_contains_annex_iv_sections(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        for i in range(1, 10):
            assert f"Section {i}:" in md

    def test_contains_mermaid_diagram(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "```mermaid" in md
        assert "graph LR" in md

    def test_contains_ropa_table(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "Record of Processing Activities" in md
        assert "Processing Activity" in md

    def test_contains_next_steps(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "Next Steps" in md

    def test_contains_detected_providers(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "Anthropic" in md
        assert "OpenAI" in md

    def test_write_creates_file(self, tmp_path: Path):
        pkg = self._get_package()
        output = tmp_path / "compliance.md"
        ComplyReporter().write(pkg, output)
        assert output.exists()
        content = output.read_text()
        assert "EU AI Act" in content

    def test_write_split_creates_directory(self, tmp_path: Path):
        pkg = self._get_package()
        output_dir = tmp_path / "compliance"
        created = ComplyReporter().write_split(pkg, output_dir)
        assert output_dir.is_dir()
        assert len(created) >= 3  # summary + article-11 + article-13 + mermaid

    def test_split_contains_expected_files(self, tmp_path: Path):
        pkg = self._get_package()
        output_dir = tmp_path / "compliance"
        created = ComplyReporter().write_split(pkg, output_dir)
        names = [f.name for f in created]
        assert "compliance-summary.md" in names
        assert "article-11-docs.md" in names
        assert "article-13-flows.md" in names
        assert "data-flow.mermaid" in names

    def test_split_files_are_nonempty(self, tmp_path: Path):
        pkg = self._get_package()
        output_dir = tmp_path / "compliance"
        created = ComplyReporter().write_split(pkg, output_dir)
        for f in created:
            assert f.stat().st_size > 0, f"{f.name} is empty"

    def test_tagline_present(self):
        pkg = self._get_package()
        md = ComplyReporter().render(pkg)
        assert "One codebase. One command. Three articles." in md
