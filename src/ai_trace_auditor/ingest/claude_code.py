"""Claude Code conversation trace parser.

Parses .jsonl files from ~/.claude/projects/ directories.
Each file is one conversation session with interleaved message types:
user, assistant, progress, system, file-history-snapshot, queue-operation.

Assistant messages contain the Anthropic API response with model, usage,
stop_reason, and content blocks (text, tool_use, tool_result).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ai_trace_auditor.models.trace import (
    NormalizedSpan,
    NormalizedTrace,
    ToolCall,
)


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _extract_tool_calls(content: list[dict[str, Any]]) -> list[ToolCall] | None:
    """Extract tool_use blocks from assistant message content."""
    calls = []
    for block in content:
        if block.get("type") == "tool_use":
            calls.append(
                ToolCall(
                    id=block.get("id"),
                    name=block.get("name", "unknown"),
                    type="function",
                    arguments=block.get("input"),
                )
            )
    return calls if calls else None


def _extract_text_content(content: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Extract text blocks as output messages."""
    texts = []
    for block in content:
        if block.get("type") == "text" and block.get("text"):
            texts.append({"role": "assistant", "content": block["text"]})
    return texts if texts else None


class ClaudeCodeIngestor:
    """Parses Claude Code conversation .jsonl files into NormalizedTraces."""

    def can_parse(self, data: dict[str, Any] | list[Any]) -> bool:
        if not isinstance(data, list) or len(data) == 0:
            return False
        # Check for Claude Code specific fields
        for item in data[:10]:
            if not isinstance(item, dict):
                continue
            if item.get("type") in ("user", "assistant", "progress", "system"):
                if "sessionId" in item and "uuid" in item:
                    return True
        return False

    def parse(self, data: dict[str, Any] | list[Any]) -> list[NormalizedTrace]:
        if isinstance(data, dict):
            return []
        if not isinstance(data, list):
            return []

        # Group by sessionId
        sessions: dict[str, list[dict[str, Any]]] = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue
            session_id = entry.get("sessionId")
            if not session_id:
                continue
            sessions.setdefault(session_id, []).append(entry)

        traces: list[NormalizedTrace] = []
        for session_id, entries in sessions.items():
            spans = self._extract_spans(entries)
            if not spans:
                continue

            # Build metadata from first entry
            first = entries[0]
            metadata: dict[str, Any] = {}
            for key in ("version", "gitBranch", "cwd", "permissionMode"):
                if first.get(key) is not None:
                    metadata[key] = first[key]

            traces.append(
                NormalizedTrace(
                    trace_id=session_id,
                    spans=spans,
                    source_format="claude_code",
                    metadata=metadata,
                )
            )

        return traces

    def _extract_spans(self, entries: list[dict[str, Any]]) -> list[NormalizedSpan]:
        """Convert assistant message entries into NormalizedSpans."""
        spans: list[NormalizedSpan] = []

        # Track user messages for input context
        last_user_content: list[dict[str, Any]] | None = None

        for entry in entries:
            msg_type = entry.get("type")

            if msg_type == "user":
                # Capture user message for pairing with next assistant response
                msg = entry.get("message", {})
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, str):
                    last_user_content = [{"role": "user", "content": content}]
                elif isinstance(content, list):
                    texts = [
                        {"role": "user", "content": b.get("text", "")}
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    last_user_content = texts if texts else None
                continue

            if msg_type != "assistant":
                continue

            msg = entry.get("message")
            if not isinstance(msg, dict):
                continue

            # Skip if no actual API response
            if msg.get("type") != "message":
                continue

            usage = msg.get("usage", {})
            content = msg.get("content", [])
            if not isinstance(content, list):
                content = []

            # Compute token counts
            input_tokens = _safe_int(usage.get("input_tokens"))
            cache_creation = _safe_int(usage.get("cache_creation_input_tokens"))
            cache_read = _safe_int(usage.get("cache_read_input_tokens"))
            output_tokens = _safe_int(usage.get("output_tokens"))

            # Total input includes cache tokens
            total_input = None
            if input_tokens is not None:
                total_input = input_tokens
                if cache_creation:
                    total_input += cache_creation
                if cache_read:
                    total_input += cache_read

            total_tokens = None
            if total_input is not None and output_tokens is not None:
                total_tokens = total_input + output_tokens

            # Map stop_reason to finish_reasons
            stop_reason = msg.get("stop_reason")
            finish_reasons = [stop_reason] if stop_reason else None

            # Extract tool calls and text content
            tool_calls = _extract_tool_calls(content)
            output_messages = _extract_text_content(content)

            # Determine operation type
            operation = "chat"
            if tool_calls:
                operation = "chat"  # Chat with tool use

            timestamp = _parse_timestamp(entry.get("timestamp"))

            spans.append(
                NormalizedSpan(
                    span_id=entry.get("uuid") or msg.get("id") or uuid.uuid4().hex[:16],
                    parent_span_id=entry.get("parentUuid"),
                    operation=operation,
                    provider="anthropic",
                    model_requested=msg.get("model"),
                    model_used=msg.get("model"),
                    start_time=timestamp,
                    end_time=timestamp,  # Claude Code doesn't log end separately
                    input_tokens=total_input,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    response_id=msg.get("id"),
                    finish_reasons=finish_reasons,
                    input_messages=last_user_content,
                    output_messages=output_messages,
                    tool_calls=tool_calls,
                    raw_attributes={
                        "usage": usage,
                        "session_id": entry.get("sessionId"),
                        "version": entry.get("version"),
                        "git_branch": entry.get("gitBranch"),
                        "service_tier": usage.get("service_tier"),
                        "inference_geo": usage.get("inference_geo"),
                        "cache_creation_input_tokens": cache_creation,
                        "cache_read_input_tokens": cache_read,
                    },
                )
            )

            # Clear user content after pairing
            last_user_content = None

        return spans
