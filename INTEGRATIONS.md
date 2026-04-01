# AI Trace Auditor -- Platform Integration Plan

## Current State

The tool has four file-based ingestors:
- **OTel** (`ingest/otel.py`): Parses OTLP JSON exports and flat span lists with `gen_ai.*` attributes
- **Langfuse** (`ingest/langfuse.py`): Parses Langfuse JSON file exports with `observations[]`
- **Claude Code** (`ingest/claude_code.py`): Parses `~/.claude/projects/*.jsonl` conversation traces
- **Raw API** (`ingest/raw_api.py`): Parses JSONL request/response logs

All ingestors implement the `TraceIngestor` Protocol (two methods: `can_parse`, `parse`) and output `list[NormalizedTrace]`. Auto-detection cascades through `INGESTORS` list in `ingest/detect.py`.

**Problem:** Users must manually export traces as files, then run the CLI. The tool cannot pull live data from where teams already store traces (Langfuse, Arize, OTel collectors) or intercept traces at runtime (LangChain, LlamaIndex callbacks).

**Goal:** Make compliance checking happen where the data already lives, not as a separate manual step.

---

## Architecture

### Two integration patterns

```
Pattern A: API Importer (pull traces from a remote platform)
┌──────────────────────┐     HTTP/REST      ┌──────────────────┐
│ Langfuse / Arize /   │ ◄───────────────── │  TraceImporter   │
│ OTel Collector       │                    │  (new protocol)  │
└──────────────────────┘                    └────────┬─────────┘
                                                     │
                                            list[NormalizedTrace]
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │ ComplianceAnalyzer│
                                            │ (existing engine) │
                                            └──────────────────┘

Pattern B: Callback Handler (intercept traces at runtime)
┌──────────────────────┐     Callback        ┌──────────────────┐
│ LangChain / LlamaIndex│ ───────────────── │ CallbackHandler  │
│ / CrewAI / Haystack  │  on_llm_end, etc.  │ (framework-specific)│
└──────────────────────┘                    └────────┬─────────┘
                                                     │
                                            NormalizedSpan (buffered)
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │ ComplianceAnalyzer│
                                            │ or JSONL export  │
                                            └──────────────────┘
```

### Package structure

API importers live in the core package (they're just HTTP clients, no framework dependencies):

```
src/ai_trace_auditor/
├── ingest/           # Existing file-based ingestors
├── importers/        # NEW: API-based importers
│   ├── __init__.py
│   ├── base.py       # TraceImporter protocol
│   ├── langfuse_api.py
│   ├── arize_api.py
│   └── otel_receiver.py
```

Callback handlers are separate pip packages (they pull in framework dependencies):

```
ai-trace-auditor-langchain/       # pip install ai-trace-auditor-langchain
├── src/ai_trace_auditor_langchain/
│   ├── __init__.py
│   └── handler.py                # Subclass of BaseCallbackHandler

ai-trace-auditor-llamaindex/      # pip install ai-trace-auditor-llamaindex
├── src/ai_trace_auditor_llamaindex/
│   ├── __init__.py
│   └── handler.py                # Subclass of SpanHandler

ai-trace-auditor-haystack/        # pip install ai-trace-auditor-haystack
├── src/ai_trace_auditor_haystack/
│   ├── __init__.py
│   └── tracer.py                 # Implementation of Tracer protocol
```

CrewAI uses LangChain under the hood, so `ai-trace-auditor-langchain` covers it automatically.

---

## Prerequisites (before any integration)

### 1. New `TraceImporter` protocol

File: `src/ai_trace_auditor/importers/base.py`

```python
"""Base protocol for API-based trace importers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from ai_trace_auditor.models.trace import NormalizedTrace


class ImportConfig(BaseModel):
    """Configuration for connecting to a trace platform."""
    
    api_url: str
    api_key: str | None = None
    secret_key: str | None = None  # Langfuse uses public + secret key pair
    project_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 1000
    tags: list[str] | None = None


class TraceImporter(Protocol):
    """Protocol for importing traces from external platforms via API."""

    def test_connection(self) -> bool:
        """Verify the API connection works. Return True if healthy."""
        ...

    def import_traces(self, config: ImportConfig) -> list[NormalizedTrace]:
        """Fetch and normalize traces from the platform."""
        ...

    @property
    def platform_name(self) -> str:
        """Human-readable platform name for CLI output."""
        ...
```

**Effort:** ~40 lines. No new dependencies.

### 2. New CLI `import` command

File: `src/ai_trace_auditor/cli.py` (add new command)

```
aitrace import langfuse --api-url https://cloud.langfuse.com --api-key pk-... --secret-key sk-... --since 2026-03-01
aitrace import arize --api-key ... --space-id ... --model-id ...
aitrace import otel --endpoint http://localhost:4318 --since 2026-03-01
```

The `import` command fetches traces via `TraceImporter`, then feeds them to the existing `ComplianceAnalyzer`. Same output as `aitrace audit` but no file needed.

**Effort:** ~80 lines (Typer subcommand group). No new dependencies.

### 3. Optional dependency groups in `pyproject.toml`

```toml
[project.optional-dependencies]
pdf = ["weasyprint>=62.0", "markdown>=3.5"]
langfuse = ["httpx>=0.27"]
arize = ["httpx>=0.27"]
all-importers = ["httpx>=0.27"]
```

`httpx` is the only new dependency (async-capable HTTP client). It replaces `requests` for modern Python.

---

## Platform 1: Langfuse (API Importer)

### What Langfuse is

Open-source LLM observability platform. Self-hostable or cloud (cloud.langfuse.com). Used by thousands of teams. Captures traces with generations (LLM calls), spans (operations), and events. Has scores (evaluations) per trace.

### Integration type

**API Importer** -- pull traces from Langfuse's REST API, convert to `NormalizedTrace`, run compliance analysis.

### Langfuse API

Base URL: `https://cloud.langfuse.com/api/public` (or self-hosted equivalent)

Authentication: HTTP Basic Auth with `publicKey:secretKey`

Key endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/public/traces` | GET | List traces with pagination |
| `GET /api/public/traces/{traceId}` | GET | Get single trace with observations |
| `GET /api/public/observations` | GET | List observations (spans/generations) |
| `GET /api/public/scores` | GET | List evaluation scores |

Query parameters for `/traces`:
- `page` (int): Page number (1-indexed)
- `limit` (int): Results per page (max 100)
- `userId` (string): Filter by user
- `name` (string): Filter by trace name
- `tags` (string[]): Filter by tags
- `fromTimestamp` (ISO 8601): Start time filter
- `toTimestamp` (ISO 8601): End time filter
- `orderBy` (string): Sort field

### Langfuse trace object structure

```json
{
  "id": "trace-abc123",
  "name": "chat-completion",
  "userId": "user-456",
  "sessionId": "session-789",
  "tags": ["production", "gpt-4"],
  "version": "1.2.0",
  "release": "2026-03-01",
  "input": {"messages": [...]},
  "output": {"content": "..."},
  "metadata": {"environment": "prod"},
  "observations": [
    {
      "id": "obs-001",
      "traceId": "trace-abc123",
      "type": "GENERATION",
      "name": "openai-chat",
      "model": "gpt-4-turbo",
      "modelParameters": {"temperature": 0.7, "maxTokens": 1000},
      "input": {"messages": [{"role": "user", "content": "..."}]},
      "output": {"content": "...", "tool_calls": [...]},
      "startTime": "2026-03-23T10:00:00Z",
      "endTime": "2026-03-23T10:00:02Z",
      "completionStartTime": "2026-03-23T10:00:01Z",
      "latency": 2.1,
      "inputTokens": 150,
      "outputTokens": 300,
      "totalTokens": 450,
      "inputCost": 0.0015,
      "outputCost": 0.009,
      "totalCost": 0.0105,
      "level": "DEFAULT",
      "statusMessage": null,
      "parentObservationId": null,
      "providedModelName": "gpt-4-turbo",
      "internalModel": "gpt-4-turbo-2024-04-09",
      "scores": [
        {"name": "helpfulness", "value": 0.85, "label": null, "comment": "Accurate response"}
      ]
    },
    {
      "id": "obs-002",
      "type": "SPAN",
      "name": "retrieval",
      "startTime": "...",
      "endTime": "...",
      "input": {"query": "..."},
      "output": {"documents": [...]}
    }
  ]
}
```

### Data mapping: Langfuse -> NormalizedSpan

The existing `LangfuseIngestor` in `ingest/langfuse.py` already handles this mapping for file exports. The API importer reuses the same `_parse_observation()` function. The only new code is the HTTP fetch + pagination logic.

| Langfuse field | NormalizedSpan field | Notes |
|---------------|---------------------|-------|
| `obs.id` | `span_id` | Direct |
| `obs.parentObservationId` | `parent_span_id` | Direct |
| `obs.type` (GENERATION/SPAN/EVENT) | `operation` | GENERATION->"chat", SPAN->"agent", EVENT->"event" |
| `obs.model` / `obs.providedModelName` | `model_requested` | Direct |
| `obs.internalModel` | `model_used` | Actual model version |
| Inferred from model name | `provider` | "gpt"->openai, "claude"->anthropic, etc. |
| `obs.startTime` | `start_time` | ISO 8601 parse |
| `obs.endTime` | `end_time` | ISO 8601 parse |
| `obs.latency` * 1000 | `duration_ms` | Seconds to ms |
| `obs.inputTokens` / `obs.promptTokens` | `input_tokens` | Direct |
| `obs.outputTokens` / `obs.completionTokens` | `output_tokens` | Direct |
| `obs.totalTokens` | `total_tokens` | Direct |
| `obs.inputCost` | `input_cost` | Direct |
| `obs.outputCost` | `output_cost` | Direct |
| `obs.totalCost` | `total_cost` | Direct |
| `obs.input` | `input_messages` | Wrapped in list |
| `obs.output` | `output_messages` | Wrapped in list |
| `obs.output.tool_calls` | `tool_calls` | Parsed to `ToolCall` |
| `obs.scores` | `evaluations` | Parsed to `Evaluation` |
| `obs.level == "ERROR"` | `error_type` | "error" |
| `obs.statusMessage` | `error_message` | Direct |
| `obs.modelParameters.temperature` | `temperature` | From modelParameters dict |
| `obs.modelParameters.maxTokens` | `max_tokens` | From modelParameters dict |

### Implementation

File: `src/ai_trace_auditor/importers/langfuse_api.py`

```python
class LangfuseImporter:
    """Import traces from Langfuse API."""

    platform_name = "Langfuse"

    def __init__(self, api_url: str, public_key: str, secret_key: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.auth = (public_key, secret_key)  # Basic auth

    def test_connection(self) -> bool:
        # GET /api/public/traces?limit=1

    def import_traces(self, config: ImportConfig) -> list[NormalizedTrace]:
        # Paginate through GET /api/public/traces
        # For each trace, observations are included inline
        # Reuse _parse_observation() from ingest/langfuse.py
        # Build NormalizedTrace with source_format="langfuse_api"
```

**Effort:** ~120 lines of new code + ~20 lines in CLI. One new dependency: `httpx`.

**Strategic value:** HIGH. Langfuse has 50K+ GitHub stars and is the default observability choice for LangChain/LlamaIndex/CrewAI users. A user who already has Langfuse can run `aitrace import langfuse` and get a compliance report without changing their existing setup.

**Partnership potential:** HIGH. Langfuse could list AI Trace Auditor as a "compliance integration" in their docs. The Langfuse team is actively building an integrations ecosystem.

---

## Platform 2: OpenTelemetry (OTLP HTTP Receiver + Enhanced Ingestor)

### What OTel GenAI is

OpenTelemetry's semantic conventions for GenAI define standardized attribute names for LLM operations. Released as part of OTel Semantic Conventions v1.28+. Adopted by: OpenLLMetry (Traceloop), Arize Phoenix, Haystack, LiteLLM (via callbacks), and the official `opentelemetry-instrumentation-openai` package.

### Integration type

Two sub-integrations:

1. **Enhanced ingestor** (already exists at `ingest/otel.py`): Handle more GenAI attribute variants
2. **OTLP HTTP receiver**: Accept traces pushed via standard OTLP HTTP protocol, so `aitrace` can act as a lightweight collector endpoint

### OTel GenAI Semantic Conventions (v1.28+)

Namespace: `gen_ai.*`

| Attribute | Type | Description |
|-----------|------|-------------|
| `gen_ai.system` | string | Provider: "openai", "anthropic", "cohere", etc. |
| `gen_ai.operation.name` | string | "chat", "text_completion", "embeddings" |
| `gen_ai.request.model` | string | Requested model name |
| `gen_ai.response.model` | string | Actual model used in response |
| `gen_ai.request.temperature` | float | Temperature parameter |
| `gen_ai.request.top_p` | float | Top-p parameter |
| `gen_ai.request.max_tokens` | int | Max tokens parameter |
| `gen_ai.request.seed` | int | Seed for reproducibility |
| `gen_ai.request.stop_sequences` | string[] | Stop sequences |
| `gen_ai.request.frequency_penalty` | float | Frequency penalty |
| `gen_ai.request.presence_penalty` | float | Presence penalty |
| `gen_ai.response.id` | string | Provider response ID |
| `gen_ai.response.finish_reasons` | string[] | Finish reasons |
| `gen_ai.usage.input_tokens` | int | Input/prompt tokens |
| `gen_ai.usage.output_tokens` | int | Output/completion tokens |
| `gen_ai.usage.total_tokens` | int | Total tokens |
| `gen_ai.tool.name` | string | Tool/function name |
| `gen_ai.tool.call.id` | string | Tool call ID |
| `gen_ai.tool.type` | string | Tool type |
| `gen_ai.provider.name` | string | Alias for gen_ai.system |

Content attributes (in span events, not span attributes):
| Event Attribute | Description |
|----------------|-------------|
| `gen_ai.input.messages` | Input messages (JSON array) |
| `gen_ai.output.messages` | Output messages (JSON array) |
| `gen_ai.system_instructions` | System prompt |

The existing `ingest/otel.py` already maps all of these. The enhancement needed is:

1. **Traceloop/OpenLLMetry variants**: Uses `traceloop.entity.name`, `traceloop.entity.input`, `traceloop.entity.output` alongside `gen_ai.*`. Some older versions use `llm.request.type` instead of `gen_ai.operation.name`.

2. **OTLP HTTP receiver**: A lightweight HTTP server that accepts POST to `/v1/traces` in OTLP JSON format. This lets `aitrace` act as a collector endpoint.

### Data mapping: Already complete

The existing `_parse_span()` in `ingest/otel.py` handles the full `gen_ai.*` namespace. The mapping is:

| OTel attribute | NormalizedSpan field |
|---------------|---------------------|
| `gen_ai.provider.name` / `gen_ai.system` | `provider` |
| `gen_ai.operation.name` | `operation` |
| `gen_ai.request.model` | `model_requested` |
| `gen_ai.response.model` | `model_used` |
| `startTimeUnixNano` | `start_time` |
| `endTimeUnixNano` | `end_time` |
| `gen_ai.usage.input_tokens` | `input_tokens` |
| `gen_ai.usage.output_tokens` | `output_tokens` |
| `gen_ai.request.temperature` | `temperature` |
| `gen_ai.request.top_p` | `top_p` |
| `gen_ai.request.max_tokens` | `max_tokens` |
| `gen_ai.request.seed` | `seed` |
| `gen_ai.response.id` | `response_id` |
| `gen_ai.response.finish_reasons` | `finish_reasons` |
| `gen_ai.input.messages` (event) | `input_messages` |
| `gen_ai.output.messages` (event) | `output_messages` |
| `gen_ai.tool.name` | `tool_calls[].name` |
| `error.type` / span status | `error_type` |

### Implementation: OTLP HTTP Receiver

File: `src/ai_trace_auditor/importers/otel_receiver.py`

Accepts POST `/v1/traces` with `Content-Type: application/json`, parses OTLP JSON, normalizes via existing `OTelIngestor.parse()`, optionally runs compliance analysis inline or buffers to a local file.

This does NOT require a full OTel Collector. It's a minimal HTTP endpoint (~80 lines using Python's `http.server` or `uvicorn`+`starlette` for async).

```
aitrace serve --port 4318
# Now configure your OTel exporter to point at http://localhost:4318
# Traces arrive, get compliance-checked, reports generated
```

**Effort:** ~150 lines (HTTP server + buffer + periodic analysis trigger). New optional dependency: `uvicorn` + `starlette` (only for `serve` command).

**Strategic value:** HIGH. Any team using OpenTelemetry for LLM observability (via Traceloop, OpenLLMetry, or direct instrumentation) can point their exporter at aitrace and get compliance reports without changing their code.

---

## Platform 3: LangChain (Callback Handler -- Separate Package)

### What LangChain's callback system is

LangChain uses a callback-based instrumentation system. Every LLM call, chain execution, tool invocation, and retriever query fires callbacks. Integrations subclass `BaseCallbackHandler` from `langchain_core.callbacks.base`.

### Key classes

```python
# langchain_core.callbacks.base
class BaseCallbackHandler:
    # LLM lifecycle
    def on_llm_start(self, serialized: dict, prompts: list[str], *, run_id: UUID, 
                     parent_run_id: UUID | None, tags: list[str] | None,
                     metadata: dict | None, **kwargs) -> None: ...
    
    def on_llm_new_token(self, token: str, *, run_id: UUID, **kwargs) -> None: ...
    
    def on_llm_end(self, response: LLMResult, *, run_id: UUID, 
                   parent_run_id: UUID | None, **kwargs) -> None: ...
    
    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None: ...
    
    # Chat model lifecycle  
    def on_chat_model_start(self, serialized: dict, messages: list[list[BaseMessage]],
                            *, run_id: UUID, parent_run_id: UUID | None,
                            tags: list[str] | None, metadata: dict | None,
                            **kwargs) -> None: ...
    
    # Chain lifecycle
    def on_chain_start(self, serialized: dict, inputs: dict, *, run_id: UUID, **kwargs) -> None: ...
    def on_chain_end(self, outputs: dict, *, run_id: UUID, **kwargs) -> None: ...
    
    # Tool lifecycle
    def on_tool_start(self, serialized: dict, input_str: str, *, run_id: UUID, **kwargs) -> None: ...
    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs) -> None: ...
    
    # Retriever lifecycle
    def on_retriever_start(self, serialized: dict, query: str, *, run_id: UUID, **kwargs) -> None: ...
    def on_retriever_end(self, documents: list[Document], *, run_id: UUID, **kwargs) -> None: ...

# langchain_core.outputs.llm_result
class LLMResult:
    generations: list[list[Generation]]  # Nested: [batch][alternatives]
    llm_output: dict | None  # Token usage, model info
    run: list[RunInfo] | None
    
class Generation:
    text: str
    generation_info: dict | None  # finish_reason, logprobs
    type: str  # "Generation" or "ChatGeneration"
    message: BaseMessage | None  # For ChatGeneration

class ChatGeneration(Generation):
    message: BaseMessage  # AIMessage with tool_calls, usage_metadata
```

### How existing integrations plug in

Langfuse's LangChain integration (`langfuse.callback.CallbackHandler`) subclasses `BaseCallbackHandler`. On `on_llm_start`, it creates a Langfuse generation. On `on_llm_end`, it updates with token counts and output. It tracks `run_id` -> Langfuse `observation_id` mapping for parent-child relationships.

Weights & Biases (`wandb.integration.langchain.WandbTracer`) does the same pattern: buffer data in `on_*_start`, flush on `on_*_end`.

### Data available in callbacks

| Callback | Data available |
|----------|---------------|
| `on_chat_model_start` | `serialized` (model name, params), `messages` (input), `run_id`, `parent_run_id`, `metadata`, `tags` |
| `on_llm_end` | `response.llm_output` (token_usage dict, model_name), `response.generations` (output text, finish_reason, tool_calls via AIMessage) |
| `on_llm_error` | `error` (exception type + message) |
| `on_tool_start` | `serialized` (tool name), `input_str` |
| `on_tool_end` | `output` (tool result string) |
| `on_chain_start/end` | Chain inputs/outputs (dict) |

From `response.llm_output` (OpenAI example):
```python
{
    "token_usage": {
        "prompt_tokens": 150,
        "completion_tokens": 300,
        "total_tokens": 450
    },
    "model_name": "gpt-4-turbo",
    "system_fingerprint": "fp_abc123"
}
```

From ChatGeneration with tool calls:
```python
generation.message  # AIMessage
generation.message.tool_calls  # [{"name": "search", "args": {...}, "id": "call_abc"}]
generation.message.usage_metadata  # {"input_tokens": 150, "output_tokens": 300, "total_tokens": 450}
```

### Data mapping: LangChain -> NormalizedSpan

| LangChain data | NormalizedSpan field | Source |
|---------------|---------------------|--------|
| `run_id` (UUID) | `span_id` | `on_chat_model_start` |
| `parent_run_id` | `parent_span_id` | `on_chat_model_start` |
| `serialized.get("_type")` / kwargs | `operation` | "chat" for chat models |
| `serialized.get("id")[-1]` or model_name | `provider` | Parse from class name: "ChatOpenAI"->"openai" |
| `serialized.get("kwargs", {}).get("model")` | `model_requested` | From serialized config |
| `response.llm_output.get("model_name")` | `model_used` | From LLM response |
| `datetime.now()` at `on_*_start` | `start_time` | Capture in handler |
| `datetime.now()` at `on_*_end` | `end_time` | Capture in handler |
| end - start | `duration_ms` | Computed |
| `llm_output["token_usage"]["prompt_tokens"]` | `input_tokens` | From llm_output |
| `llm_output["token_usage"]["completion_tokens"]` | `output_tokens` | From llm_output |
| `serialized.kwargs.temperature` | `temperature` | From serialized |
| `serialized.kwargs.max_tokens` | `max_tokens` | From serialized |
| `generation.generation_info.finish_reason` | `finish_reasons` | From generation_info |
| `messages` param | `input_messages` | From on_chat_model_start |
| `generation.message` content | `output_messages` | From on_llm_end |
| `generation.message.tool_calls` | `tool_calls` | Parsed to ToolCall list |
| `error.__class__.__name__` | `error_type` | From on_llm_error |
| `str(error)` | `error_message` | From on_llm_error |

### Implementation

Package: `ai-trace-auditor-langchain/`

```python
# ai_trace_auditor_langchain/handler.py

from langchain_core.callbacks.base import BaseCallbackHandler
from ai_trace_auditor.models.trace import NormalizedSpan, NormalizedTrace

class AITraceAuditorHandler(BaseCallbackHandler):
    """LangChain callback handler that captures traces for EU AI Act compliance."""
    
    name = "ai_trace_auditor"
    
    def __init__(
        self,
        output_path: str | Path | None = None,  # Write JSONL to file
        run_analysis: bool = False,              # Run compliance check on flush
        buffer_size: int = 100,                  # Flush after N spans
    ) -> None:
        self._pending: dict[str, dict] = {}  # run_id -> partial span data
        self._spans: list[NormalizedSpan] = []
        self._output_path = output_path
        self._run_analysis = run_analysis
        self._buffer_size = buffer_size
    
    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id, 
                            metadata, **kwargs):
        # Buffer: span_id, parent_span_id, model_requested, input_messages, start_time
    
    def on_llm_end(self, response, *, run_id, **kwargs):
        # Complete span: model_used, tokens, output, finish_reason, end_time
        # Add to self._spans
        # If len(self._spans) >= buffer_size: flush
    
    def on_llm_error(self, error, *, run_id, **kwargs):
        # Complete span with error_type, error_message
    
    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id, **kwargs):
        # Buffer tool call span
    
    def on_tool_end(self, output, *, run_id, **kwargs):
        # Complete tool call span
    
    def flush(self) -> list[NormalizedTrace]:
        # Group spans into traces (by root run_id)
        # Optionally write to JSONL
        # Optionally run ComplianceAnalyzer
        # Return traces
```

Usage:
```python
from langchain_openai import ChatOpenAI
from ai_trace_auditor_langchain import AITraceAuditorHandler

handler = AITraceAuditorHandler(output_path="traces.jsonl")
llm = ChatOpenAI(model="gpt-4", callbacks=[handler])

# Use LLM normally
response = llm.invoke("What is compliance?")

# At end of session, get compliance report
traces = handler.flush()
```

**Effort:** ~250 lines handler + ~50 lines pyproject.toml/packaging. Dependencies: `langchain-core>=0.3`, `ai-trace-auditor>=0.12`.

**Strategic value:** HIGH. LangChain has 100K+ GitHub stars. This makes compliance checking zero-effort for LangChain users: add one callback, get a report.

**Partnership potential:** MEDIUM. LangChain has a partner integrations program. Listing requires a working integration + docs page.

---

## Platform 4: LlamaIndex (Span Handler -- Separate Package)

### What LlamaIndex's instrumentation system is

LlamaIndex v0.10+ uses an `instrumentation` module that replaces the legacy `CallbackManager`. The modern system uses `Dispatcher` (event bus) and `SpanHandler` (span lifecycle).

### Key classes

```python
# llama_index.core.instrumentation.span_handler
class BaseSpanHandler(BaseModel, Generic[T]):
    open_spans: dict[str, T]  # span_id -> span data
    completed_spans: dict[str, T]

    def span_enter(
        self, id_: str, bound_args: inspect.BoundArguments, 
        instance: Any | None = None, parent_id: str | None = None, 
        tags: dict[str, Any] | None = None, **kwargs
    ) -> str | None: ...
    
    def span_exit(
        self, id_: str, bound_args: inspect.BoundArguments,
        instance: Any | None = None, result: Any | None = None,
        **kwargs
    ) -> None: ...
    
    def span_drop(
        self, id_: str, bound_args: inspect.BoundArguments,
        instance: Any | None = None, err: BaseException | None = None,
        **kwargs
    ) -> None: ...

# llama_index.core.instrumentation.events
class LLMCompletionStartEvent(BaseEvent):
    model_dict: dict
    prompt: str
    additional_kwargs: dict
    
class LLMCompletionEndEvent(BaseEvent):
    response: CompletionResponse
    prompt: str

class LLMChatStartEvent(BaseEvent):
    model_dict: dict
    messages: list[ChatMessage]
    additional_kwargs: dict
    
class LLMChatEndEvent(BaseEvent):
    response: ChatResponse
    messages: list[ChatMessage]

class EmbeddingStartEvent(BaseEvent):
    model_dict: dict

class EmbeddingEndEvent(BaseEvent):
    chunks: list[str]
    embeddings: list[list[float]]
```

The `Dispatcher` fires events. Handlers register via:
```python
import llama_index.core.instrumentation as instrument
dispatcher = instrument.get_dispatcher()
span_handler = AITraceSpanHandler()
dispatcher.add_span_handler(span_handler)
```

### Data available

From `LLMChatEndEvent.response` (ChatResponse):
```python
class ChatResponse:
    message: ChatMessage  # AI response
    raw: dict  # Raw API response (contains usage, model, etc.)
    additional_kwargs: dict
```

From `raw` dict (OpenAI example):
```python
{
    "id": "chatcmpl-abc",
    "model": "gpt-4-turbo",
    "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
    "choices": [{"finish_reason": "stop", "message": {...}}]
}
```

From `model_dict` in start events:
```python
{
    "model": "gpt-4-turbo",
    "temperature": 0.7,
    "max_tokens": 1000,
    "class_name": "OpenAI"  # Provider inference
}
```

### Data mapping: LlamaIndex -> NormalizedSpan

| LlamaIndex data | NormalizedSpan field | Source |
|----------------|---------------------|--------|
| `id_` from span_enter | `span_id` | span_enter parameter |
| `parent_id` from span_enter | `parent_span_id` | span_enter parameter |
| Event type (Chat/Completion/Embedding) | `operation` | Event class name |
| `model_dict.get("class_name")` | `provider` | Parse: "OpenAI"->"openai" |
| `model_dict.get("model")` | `model_requested` | From start event |
| `response.raw.get("model")` | `model_used` | From end event raw dict |
| `datetime.now()` at span_enter | `start_time` | Captured |
| `datetime.now()` at span_exit | `end_time` | Captured |
| `response.raw.usage.prompt_tokens` | `input_tokens` | From raw response |
| `response.raw.usage.completion_tokens` | `output_tokens` | From raw response |
| `model_dict.get("temperature")` | `temperature` | From model_dict |
| `model_dict.get("max_tokens")` | `max_tokens` | From model_dict |
| `response.raw.choices[0].finish_reason` | `finish_reasons` | From raw response |
| `messages` from start event | `input_messages` | Converted to dicts |
| `response.message` | `output_messages` | Converted to dict |
| `response.message.tool_calls` | `tool_calls` | If present |

### Implementation

Package: `ai-trace-auditor-llamaindex/`

```python
# ai_trace_auditor_llamaindex/handler.py

from llama_index.core.instrumentation.span_handler import BaseSpanHandler

class AITraceSpanHandler(BaseSpanHandler[NormalizedSpan]):
    """LlamaIndex span handler for EU AI Act compliance tracing."""
    
    class_name = "AITraceSpanHandler"
    
    def span_enter(self, id_, bound_args, instance=None, parent_id=None, **kwargs):
        # Create partial NormalizedSpan with span_id, parent_span_id, start_time
        # Store in self.open_spans
    
    def span_exit(self, id_, bound_args, instance=None, result=None, **kwargs):
        # Complete span with end_time, response data
        # Move from open_spans to completed_spans
    
    def span_drop(self, id_, bound_args, instance=None, err=None, **kwargs):
        # Complete span with error info
```

Also register an event handler for LLM-specific events to capture model details:
```python
from llama_index.core.instrumentation.event_handler import BaseEventHandler

class AITraceEventHandler(BaseEventHandler):
    def handle(self, event: BaseEvent, **kwargs):
        if isinstance(event, LLMChatStartEvent):
            # Enrich current span with model_dict info
        elif isinstance(event, LLMChatEndEvent):
            # Enrich current span with response data (tokens, model_used)
```

Usage:
```python
import llama_index.core.instrumentation as instrument
from ai_trace_auditor_llamaindex import AITraceSpanHandler, AITraceEventHandler

dispatcher = instrument.get_dispatcher()
dispatcher.add_span_handler(AITraceSpanHandler(output_path="traces.jsonl"))
dispatcher.add_event_handler(AITraceEventHandler())

# Use LlamaIndex normally
from llama_index.llms.openai import OpenAI
llm = OpenAI(model="gpt-4")
response = llm.chat([...])
```

**Effort:** ~200 lines (span handler + event handler) + ~50 lines packaging. Dependencies: `llama-index-core>=0.11`, `ai-trace-auditor>=0.12`.

**Strategic value:** MEDIUM-HIGH. LlamaIndex has 40K+ GitHub stars. Smaller than LangChain but the primary RAG framework. RAG pipelines in production are more likely to need compliance documentation.

---

## Platform 5: CrewAI (Via LangChain Callback)

### What CrewAI's system is

CrewAI uses LangChain under the hood for LLM calls. When you create a `CrewAI` agent with an LLM, it creates a LangChain `ChatModel` instance. All LLM calls go through LangChain's callback system.

CrewAI also has its own telemetry system (`crewai.telemetry`) that collects anonymized usage data, but this is not the integration point. The LLM call path is:

```
CrewAI Agent -> CrewAI Task -> LangChain ChatModel -> LLM Provider API
                                     ↓
                              LangChain Callbacks fire here
```

### Integration approach

No separate package needed. `ai-trace-auditor-langchain` works directly:

```python
from crewai import Agent, Task, Crew
from ai_trace_auditor_langchain import AITraceAuditorHandler

handler = AITraceAuditorHandler(output_path="crew_traces.jsonl")

agent = Agent(
    role="Researcher",
    goal="Find compliance gaps",
    llm="gpt-4",
    callbacks=[handler]  # LangChain callbacks are passed through
)

crew = Crew(agents=[agent], tasks=[...])
result = crew.kickoff()
```

CrewAI v0.41+ also supports `callbacks` at the Crew level:
```python
crew = Crew(
    agents=[...],
    tasks=[...],
    callbacks=[handler]  # Applied to all agents
)
```

### Additional CrewAI-specific data

CrewAI adds metadata that LangChain callbacks don't capture:
- Agent role and goal
- Task description
- Delegation chain (which agent delegated to which)
- Memory state (if enabled)

To capture these, we can optionally read from CrewAI's internal state in the callback:
```python
def on_chain_start(self, serialized, inputs, *, run_id, metadata, **kwargs):
    # metadata may contain {"agent_role": "...", "task": "..."}
    # CrewAI injects this via LangChain's metadata propagation
```

**Effort:** 0 lines (uses LangChain handler). Optionally ~30 lines to add CrewAI-specific metadata extraction.

**Strategic value:** MEDIUM. CrewAI has 25K+ GitHub stars. Multi-agent systems are more likely to be classified as high-risk (autonomous decision-making). The compliance need is real.

**Partnership potential:** MEDIUM. We already submitted a compliance guide PR to CrewAI's repo. Converting that to "install this callback" is a natural next step.

---

## Platform 6: Haystack (Tracer -- Separate Package)

### What Haystack's tracing system is

Haystack 2.x uses a `Tracer` protocol for observability. The system is pipeline-centric: every `Pipeline.run()` creates a trace with spans for each component execution.

### Key classes

```python
# haystack.tracing
class Tracer(Protocol):
    def trace(self, operation_name: str, parent_span: Span | None = None, 
              tags: dict[str, Any] | None = None) -> contextmanager[Span]: ...
    
    def current_span(self) -> Span | None: ...

class Span(Protocol):
    def set_tag(self, key: str, value: Any) -> None: ...
    def set_content_tag(self, key: str, value: Any) -> None: ...
    def raw_span(self) -> Any: ...
    def get_correlation_data_for_logs(self) -> dict[str, Any]: ...

# Built-in tracer backends
class OpenTelemetryTracer:  # Uses OTel SDK
class LoggingTracer:  # Logs to Python logging
```

Haystack's OpenTelemetry backend already uses `gen_ai.*` attributes. So if a team uses Haystack with OTel tracing enabled, the existing `OTelIngestor` in aitrace already handles their data.

### When a separate package matters

If users want runtime compliance checking without OTel infrastructure:

```python
# haystack_integration
from haystack.tracing import Tracer, Span

class AITraceAuditorTracer:
    """Haystack tracer that captures spans for compliance analysis."""
    
    def trace(self, operation_name, parent_span=None, tags=None):
        # Create span, yield it, on exit complete it
        # Buffer NormalizedSpan
```

### Data available from Haystack spans

Haystack components set tags during execution:
```python
# From ChatGenerator component:
span.set_tag("haystack.component.type", "ChatGenerator")
span.set_tag("haystack.component.input.model", "gpt-4")
span.set_content_tag("haystack.component.input.messages", [...])
span.set_content_tag("haystack.component.output.replies", [...])
span.set_tag("haystack.component.output.meta", {"usage": {"prompt_tokens": 100, ...}})
```

### Data mapping: Haystack -> NormalizedSpan

| Haystack tag | NormalizedSpan field |
|-------------|---------------------|
| span context ID | `span_id` |
| parent span context | `parent_span_id` |
| `haystack.component.type` | `operation` (ChatGenerator->"chat") |
| `haystack.component.input.model` | `model_requested` |
| output meta `model` | `model_used` |
| span start time | `start_time` |
| span end time | `end_time` |
| output meta `usage.prompt_tokens` | `input_tokens` |
| output meta `usage.completion_tokens` | `output_tokens` |
| `haystack.component.input.messages` | `input_messages` |
| `haystack.component.output.replies` | `output_messages` |

**Effort:** ~180 lines. Dependencies: `haystack-ai>=2.0`, `ai-trace-auditor>=0.12`.

**Strategic value:** MEDIUM. Haystack has 20K+ GitHub stars. Strong in enterprise RAG deployments (SAP, Airbus use it). Enterprise users are more likely to need EU AI Act compliance.

**Partnership potential:** HIGH. We already submitted a compliance guide PR to Haystack. The deepset team (Haystack maintainers) is German and acutely aware of EU AI Act implications. They would likely promote a compliance integration.

---

## Platform 7: Arize / Phoenix (API Importer)

### What Arize Phoenix is

Open-source LLM observability tool by Arize AI. Uses OpenTelemetry under the hood. Self-hostable via `phoenix.otel`. Stores traces in a local or remote database. Has a REST API and Python client for export.

### Integration type

**API Importer** -- pull spans from Phoenix's REST API or use the Python client.

### Phoenix API

The Phoenix server exposes:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /v1/spans` | GET | List spans with filters |
| `GET /v1/traces` | GET | List traces |
| `POST /v1/traces` | POST | Ingest OTLP traces (same as OTel collector) |
| `GET /v1/datasets` | GET | List evaluation datasets |

Python client:
```python
import phoenix as px

client = px.Client(endpoint="http://localhost:6006")

# Get spans as DataFrame
spans_df = client.get_spans_dataframe(
    filter_condition="span_kind == 'LLM'",
    start_time=datetime(2026, 3, 1),
    end_time=datetime(2026, 3, 23),
)

# Columns: name, span_kind, status_code, status_message, start_time, end_time,
#           attributes.llm.model_name, attributes.llm.token_count.prompt,
#           attributes.llm.token_count.completion, attributes.input.value,
#           attributes.output.value, context.trace_id, context.span_id,
#           parent_id
```

### Key: Phoenix uses OTel internally

Phoenix stores everything as OTel spans with `gen_ai.*` (or the older OpenInference `llm.*`) attributes. This means:

1. If users export from Phoenix as OTLP JSON, the existing `OTelIngestor` already works.
2. The API importer just needs to fetch spans and convert from Phoenix's DataFrame/JSON format.

### Phoenix attribute variants (OpenInference)

Phoenix's default instrumentation uses the OpenInference semantic conventions, which predate the OTel GenAI conventions:

| OpenInference attribute | OTel GenAI equivalent | NormalizedSpan field |
|------------------------|----------------------|---------------------|
| `llm.model_name` | `gen_ai.request.model` | `model_requested` |
| `llm.invocation_parameters` | various `gen_ai.request.*` | `temperature`, `max_tokens`, etc. |
| `llm.token_count.prompt` | `gen_ai.usage.input_tokens` | `input_tokens` |
| `llm.token_count.completion` | `gen_ai.usage.output_tokens` | `output_tokens` |
| `llm.token_count.total` | `gen_ai.usage.total_tokens` | `total_tokens` |
| `input.value` | `gen_ai.input.messages` (event) | `input_messages` |
| `output.value` | `gen_ai.output.messages` (event) | `output_messages` |
| `llm.provider` | `gen_ai.system` | `provider` |
| `openinference.span.kind` | `gen_ai.operation.name` | `operation` |

### Implementation

File: `src/ai_trace_auditor/importers/arize_api.py`

Two approaches:
1. **REST API**: Fetch from `/v1/spans`, parse JSON, map to NormalizedSpan
2. **Python client**: Use `px.Client().get_spans_dataframe()`, iterate rows

The REST approach is preferred (no dependency on `arize-phoenix` package).

```python
class ArizePhoenixImporter:
    """Import traces from Arize Phoenix via REST API."""
    
    platform_name = "Arize Phoenix"
    
    def __init__(self, endpoint: str = "http://localhost:6006") -> None:
        self.endpoint = endpoint.rstrip("/")
    
    def import_traces(self, config: ImportConfig) -> list[NormalizedTrace]:
        # GET /v1/spans with time range filter
        # Map OpenInference attributes to NormalizedSpan
        # Group by trace_id
```

Also enhance `ingest/otel.py` to recognize OpenInference attributes as fallbacks:
```python
# In _parse_span():
provider = (
    all_attrs.get("gen_ai.provider.name") 
    or all_attrs.get("gen_ai.system")
    or all_attrs.get("llm.provider")  # OpenInference fallback
)
```

**Effort:** ~130 lines (API client + attribute mapping) + ~20 lines OTel ingestor enhancement. New dependency: `httpx` (shared with Langfuse importer).

**Strategic value:** MEDIUM. Arize Phoenix has 8K+ GitHub stars. Smaller than Langfuse but growing fast, especially in ML teams that also use Arize's commercial platform. Enterprise teams using Arize are serious about production AI.

---

## Priority Matrix and Phases

### Phase 1: Highest Value, Lowest Effort (April 2026)

| # | Integration | Type | Effort (LOC) | Dependencies | Strategic Value |
|---|-------------|------|-------------|--------------|-----------------|
| 1 | **TraceImporter protocol + CLI `import` command** | Core prerequisite | ~120 | None | Enables all API importers |
| 2 | **Langfuse API importer** | API pull | ~120 | httpx | HIGH -- largest observability user base |
| 3 | **OTel ingestor enhancement** (OpenInference fallbacks) | Enhancement | ~30 | None | HIGH -- covers Phoenix, Traceloop, OpenLLMetry |

Phase 1 total: ~270 lines of code, 1 new dependency (httpx as optional).

**Why this order:** Langfuse covers the most users immediately. The OTel enhancement is tiny but unlocks Phoenix/Traceloop data. Together, these two integrations cover an estimated 60-70% of teams that do LLM observability.

### Phase 2: Medium Effort, High Value (May 2026)

| # | Integration | Type | Effort (LOC) | Dependencies | Strategic Value |
|---|-------------|------|-------------|--------------|-----------------|
| 4 | **LangChain callback handler** | Separate package | ~300 | langchain-core | HIGH -- 100K+ stars, runtime compliance |
| 5 | **LlamaIndex span handler** | Separate package | ~250 | llama-index-core | MEDIUM-HIGH -- dominant RAG framework |
| 6 | **OTLP HTTP receiver** (`aitrace serve`) | Core feature | ~150 | uvicorn, starlette | HIGH -- accepts traces from any OTel pipeline |

Phase 2 total: ~700 lines across 3 packages/features.

**Why this order:** LangChain first (largest user base). LlamaIndex second (RAG-specific, enterprise). OTel receiver third (infrastructure play, enables "continuous compliance monitoring").

### Phase 3: Ecosystem Play (June 2026)

| # | Integration | Type | Effort (LOC) | Dependencies | Strategic Value |
|---|-------------|------|-------------|--------------|-----------------|
| 7 | **Arize Phoenix API importer** | API pull | ~130 | httpx (shared) | MEDIUM -- ML teams, enterprise |
| 8 | **Haystack tracer** | Separate package | ~180 | haystack-ai | MEDIUM -- enterprise RAG, German market |
| 9 | **CrewAI documentation** | Docs only | ~20 | None (uses LangChain handler) | MEDIUM -- multi-agent compliance |

Phase 3 total: ~330 lines + documentation.

---

## Changes to Existing Code

### 1. New directory: `src/ai_trace_auditor/importers/`

```
importers/
├── __init__.py          # Exports: LangfuseImporter, ArizePhoenixImporter
├── base.py              # TraceImporter protocol + ImportConfig model
├── langfuse_api.py      # Langfuse REST API client
├── arize_api.py         # Arize Phoenix REST API client
└── otel_receiver.py     # OTLP HTTP receiver (lightweight server)
```

### 2. Enhancement: `src/ai_trace_auditor/ingest/otel.py`

Add OpenInference attribute fallbacks in `_parse_span()`:

```python
# Line ~206, after existing gen_ai.* lookups:
provider = (
    all_attrs.get("gen_ai.provider.name") 
    or all_attrs.get("gen_ai.system")
    or all_attrs.get("llm.provider")          # OpenInference
)
model_requested = (
    all_attrs.get("gen_ai.request.model")
    or all_attrs.get("llm.model_name")         # OpenInference
)
input_tokens = _safe_int(
    all_attrs.get("gen_ai.usage.input_tokens")
    or all_attrs.get("llm.token_count.prompt")  # OpenInference
)
# ... similar for output_tokens, total_tokens
```

### 3. Enhancement: `src/ai_trace_auditor/ingest/detect.py`

Add new format hints for API-imported data:

```python
format_map = {
    "otel": OTelIngestor,
    "langfuse": LangfuseIngestor,
    "claude_code": ClaudeCodeIngestor,
    "raw": RawAPIIngestor,
    "langfuse_api": LangfuseIngestor,  # API-fetched data reuses same parser
    "arize": OTelIngestor,              # Phoenix data is OTel-compatible
}
```

### 4. New CLI commands in `src/ai_trace_auditor/cli.py`

```python
# New subcommand group
import_app = typer.Typer(name="import", help="Import traces from external platforms.")
app.add_typer(import_app)

@import_app.command(name="langfuse")
def import_langfuse(
    api_url: str = typer.Option("https://cloud.langfuse.com", help="Langfuse API URL"),
    public_key: str = typer.Option(..., envvar="LANGFUSE_PUBLIC_KEY"),
    secret_key: str = typer.Option(..., envvar="LANGFUSE_SECRET_KEY"),
    since: str | None = typer.Option(None, help="Start date (YYYY-MM-DD)"),
    limit: int = typer.Option(1000, help="Max traces to fetch"),
    output: Path | None = typer.Option(None, "-o", help="Save normalized traces"),
    audit: bool = typer.Option(False, help="Run compliance audit on imported traces"),
): ...

@import_app.command(name="arize")
def import_arize(
    endpoint: str = typer.Option("http://localhost:6006"),
    since: str | None = typer.Option(None),
    audit: bool = typer.Option(False),
): ...

@app.command()
def serve(
    port: int = typer.Option(4318, help="OTLP receiver port"),
    audit_interval: int = typer.Option(300, help="Seconds between compliance checks"),
): ...
```

### 5. `pyproject.toml` updates

```toml
[project.optional-dependencies]
pdf = ["weasyprint>=62.0", "markdown>=3.5"]
langfuse = ["httpx>=0.27"]
arize = ["httpx>=0.27"]
serve = ["uvicorn>=0.30", "starlette>=0.38"]
importers = ["httpx>=0.27"]
all = ["weasyprint>=62.0", "markdown>=3.5", "httpx>=0.27", "uvicorn>=0.30", "starlette>=0.38"]
```

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Langfuse API changes (v2 -> v3) | API importer breaks | Pin to documented v2 public API endpoints; add integration test that runs against Langfuse cloud |
| LangChain callback interface changes | Handler breaks | Pin to `langchain-core>=0.3,<0.4`; the BaseCallbackHandler interface has been stable since LangChain v0.2 |
| LlamaIndex instrumentation API instability | Handler breaks | The new instrumentation module (v0.10+) is explicitly marked as stable public API; pin `llama-index-core>=0.11` |
| Phoenix OpenInference vs OTel GenAI attribute divergence | Wrong field mapping | Support both attribute namespaces with fallback chain (try gen_ai.* first, then llm.*) |
| Large trace volumes from API import | Memory issues, slow analysis | Stream-parse responses; add `--limit` flag; implement pagination with cursor-based fetching |
| Callback handlers in hot path | Performance overhead in production | Buffer spans in memory, flush asynchronously; provide `async` handler variants; keep per-span overhead under 1ms |
| httpx dependency conflict | Version conflict with user's existing httpx | Use generous version range (>=0.27); httpx has a stable API |

---

## Testing Strategy

### Unit tests (per integration)

Each integration gets its own test file with fixture data:

```
tests/
├── test_importers/
│   ├── test_langfuse_api.py     # Mock HTTP responses, verify NormalizedSpan mapping
│   ├── test_arize_api.py        # Mock HTTP responses
│   └── test_otel_receiver.py    # Mock OTLP POST requests
├── test_ingest/
│   └── test_otel.py             # Add OpenInference attribute test cases
```

For callback handler packages:
```
ai-trace-auditor-langchain/tests/
├── test_handler.py              # Mock LangChain LLMResult, verify span capture
├── fixtures/
│   └── sample_llm_result.json   # Fixture data
```

### Integration tests (optional, require live services)

```bash
# Requires a running Langfuse instance
LANGFUSE_PUBLIC_KEY=pk-test LANGFUSE_SECRET_KEY=sk-test \
  pytest tests/integration/test_langfuse_live.py

# Requires a running Phoenix instance
pytest tests/integration/test_phoenix_live.py
```

### Verification checklist per integration

- [ ] `can_parse()` correctly identifies platform data
- [ ] All available fields map to NormalizedSpan
- [ ] Missing fields produce `None` (not errors)
- [ ] Token counts are accurate (test against known fixture)
- [ ] Error spans are captured with error_type and error_message
- [ ] Parent-child relationships preserved (parent_span_id)
- [ ] Timestamps are timezone-aware (UTC)
- [ ] Large payloads don't OOM (stream/paginate)
- [ ] Compliance analysis produces same results whether data came from file or API import

---

## Success Criteria

- [ ] `aitrace import langfuse` works end-to-end: fetch traces, run audit, produce report
- [ ] `aitrace import arize` works against a Phoenix instance
- [ ] `aitrace serve` accepts OTLP traces and produces compliance reports
- [ ] `ai-trace-auditor-langchain` captures all LLM call data in a LangChain application
- [ ] `ai-trace-auditor-llamaindex` captures all LLM call data in a LlamaIndex application
- [ ] Documentation page for each integration with copy-paste setup instructions
- [ ] All integrations produce the same `NormalizedTrace` format -- compliance analysis is integration-agnostic
- [ ] Zero new dependencies in the core package for file-based analysis (httpx only for `import` commands)
```

---

The file is ready at the path: **`/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/INTEGRATIONS.md`**

## Key files referenced in this plan

Existing codebase (read during research):

- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/ingest/base.py` -- the `TraceIngestor` Protocol that all new integrations extend
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/models/trace.py` -- `NormalizedSpan` and `NormalizedTrace`, the universal internal models (37 fields)
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/ingest/detect.py` -- auto-detection cascade and `ingest_file()` entry point
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/ingest/langfuse.py` -- existing Langfuse file parser with `_parse_observation()` that the API importer will reuse
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/ingest/otel.py` -- existing OTel parser with `gen_ai.*` attribute mapping that needs OpenInference fallbacks
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/analysis/engine.py` -- `ComplianceAnalyzer` that all integrations feed into
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/src/ai_trace_auditor/comply/runner.py` -- `run_full_compliance()` orchestrator
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/pyproject.toml` -- package config that needs optional dependency groups
- `/Users/bipinrimal/Downloads/Website/Projects/ai-trace-auditor/ROADMAP.md` -- existing roadmap (Phase 3 mentions Langfuse, Arize, Datadog integrations)

New files to create (execution plan):

- `src/ai_trace_auditor/importers/base.py` -- `TraceImporter` protocol + `ImportConfig`
- `src/ai_trace_auditor/importers/langfuse_api.py` -- Langfuse REST API client
- `src/ai_trace_auditor/importers/arize_api.py` -- Arize Phoenix REST API client
- `src/ai_trace_auditor/importers/otel_receiver.py` -- OTLP HTTP receiver
- Separate repos: `ai-trace-auditor-langchain/`, `ai-trace-auditor-llamaindex/`, `ai-trace-auditor-haystack/`

The total estimated effort across all three phases is approximately 1,300 lines of new code plus three separate packages. Phase 1 alone (the highest-impact slice) is approximately 270 lines and one new dependency.