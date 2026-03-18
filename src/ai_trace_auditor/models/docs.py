"""Data models for codebase scanning and Annex IV documentation generation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AIImport(BaseModel):
    """An AI SDK/library import detected in source code."""

    library: str  # "anthropic", "openai", "langchain", etc.
    module_path: str  # "anthropic.Anthropic", "openai"
    file_path: str
    line_number: int


class ModelReference(BaseModel):
    """An AI model identifier found in source code."""

    model_id: str  # "claude-3-opus-20240229", "gpt-4o"
    file_path: str
    line_number: int
    context: str  # surrounding code snippet


class VectorDBUsage(BaseModel):
    """A vector database connection detected in source code."""

    db_name: str  # "pinecone", "chromadb", "qdrant"
    module_path: str
    file_path: str
    line_number: int


class TrainingDataRef(BaseModel):
    """A reference to training/dataset loading in source code."""

    pattern: str  # "load_dataset", "read_csv", etc.
    file_path: str
    line_number: int
    context: str


class EvalScriptRef(BaseModel):
    """An evaluation/metrics script detected in source code."""

    file_path: str
    metrics_detected: list[str]  # ["accuracy_score", "f1_score"]


class DeploymentConfig(BaseModel):
    """A deployment artifact found in the codebase."""

    config_type: str  # "dockerfile", "compose", "kubernetes", "terraform"
    file_path: str
    contains_ai_deps: bool = False


class AIEndpoint(BaseModel):
    """An API endpoint that uses AI detected in source code."""

    framework: str  # "fastapi", "flask", "express"
    route: str  # "/api/chat"
    file_path: str
    line_number: int


class CodeScanResult(BaseModel):
    """Aggregated results from scanning a codebase for AI usage."""

    scanned_dir: str
    file_count: int
    scan_duration_ms: int
    ai_imports: list[AIImport] = []
    model_references: list[ModelReference] = []
    vector_dbs: list[VectorDBUsage] = []
    training_data_refs: list[TrainingDataRef] = []
    eval_scripts: list[EvalScriptRef] = []
    deployment_configs: list[DeploymentConfig] = []
    ai_endpoints: list[AIEndpoint] = []

    @property
    def providers(self) -> list[str]:
        """Unique AI providers/libraries detected."""
        return sorted({imp.library for imp in self.ai_imports})

    @property
    def models(self) -> list[str]:
        """Unique model identifiers detected."""
        return sorted({ref.model_id for ref in self.model_references})

    @property
    def has_ai_usage(self) -> bool:
        return bool(self.ai_imports or self.model_references)


class AnnexIVSection(BaseModel):
    """A single section of the Annex IV technical documentation."""

    section_number: int  # 1-9
    title: str
    content: str  # Markdown content
    auto_populated: bool = False
    confidence: str = "manual"  # "high", "medium", "low", "manual"


class AnnexIVDocument(BaseModel):
    """Complete Annex IV technical documentation package."""

    sections: list[AnnexIVSection]
    generated_at: datetime
    source_dir: str
    scan_result: CodeScanResult
    trace_enriched: bool = False

    @property
    def completion_pct(self) -> float:
        """Percentage of sections with auto-populated content."""
        if not self.sections:
            return 0.0
        auto = sum(1 for s in self.sections if s.auto_populated)
        return (auto / len(self.sections)) * 100
