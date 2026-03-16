"""Workflow optimization analysis.

Analyzes Claude Code conversation traces for efficiency patterns:
- Conversation efficiency (token ratio, tool success rate, edit convergence)
- Prompt patterns (length, corrections, question vs command ratio)
- File churn detection (high-iteration files, cross-session churn)
- Optimal session length correlation
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ConversationEfficiency:
    """Efficiency metrics for a single session."""
    session_id: str
    date: str
    ai_calls: int
    duration_hours: float

    # Token efficiency
    input_tokens: int
    output_tokens: int
    token_ratio: float  # output / input (higher = more productive)

    # Tool success
    tool_calls_total: int
    tool_calls_failed: int
    tool_success_rate: float  # 0.0-1.0

    # Edit convergence
    files_edited: int
    total_edits: int
    avg_edits_per_file: float
    high_churn_files: list[str]  # files with 5+ edits

    # Corrections
    correction_count: int
    correction_rate: float  # corrections / total user messages


@dataclass
class FileChurn:
    """File churn analysis across sessions."""
    path: str
    total_edits: int
    session_count: int  # how many sessions touched this file
    avg_edits_per_session: float
    max_edits_in_session: int
    total_reads: int
    read_edit_ratio: float  # reads / edits


@dataclass
class PromptStats:
    """Aggregate prompt pattern statistics."""
    total_prompts: int
    avg_length_chars: float
    median_length_chars: int
    short_prompts: int  # < 50 chars
    medium_prompts: int  # 50-200 chars
    long_prompts: int  # 200+ chars
    question_count: int  # prompts containing ?
    command_count: int  # imperative prompts
    correction_count: int  # "no", "undo", "wrong", "instead"
    question_ratio: float
    correction_ratio: float


@dataclass
class SessionLengthBucket:
    """Performance metrics grouped by session length."""
    label: str  # "< 1h", "1-2h", etc.
    session_count: int
    avg_token_ratio: float
    avg_tool_success: float
    avg_edits_per_file: float
    avg_corrections: float


@dataclass
class WorkflowReport:
    """Complete workflow optimization report."""
    # Per-session efficiency
    sessions: list[ConversationEfficiency]
    avg_token_ratio: float
    avg_tool_success: float
    avg_edits_per_file: float

    # File churn (cross-session)
    high_churn_files: list[FileChurn]

    # Prompt patterns
    prompt_stats: PromptStats

    # Session length analysis
    length_buckets: list[SessionLengthBucket]
    optimal_length: str  # recommendation

    # Recommendations
    recommendations: list[str]


# Correction patterns (case-insensitive)
CORRECTION_PATTERNS = re.compile(
    r"\b(no[,.]?\s+(not that|I meant|don'?t|instead)|"
    r"that'?s wrong|undo that|revert|go back|"
    r"actually[,.]?\s+(I want|let'?s|do)|"
    r"wait[,.]?\s+no|never\s*mind|scratch that|"
    r"stop[,.]?\s+(don'?t|no)|wrong approach)\b",
    re.IGNORECASE,
)

COMMAND_PATTERNS = re.compile(
    r"^(create|build|write|add|remove|delete|fix|update|change|"
    r"move|rename|install|run|deploy|push|commit|implement|refactor|"
    r"make|set up|configure)\b",
    re.IGNORECASE,
)


def analyze_workflow(project_dir: Path) -> WorkflowReport:
    """Run full workflow analysis on a Claude Code project directory."""
    files = sorted(project_dir.glob("*.jsonl"))
    if not files:
        raise ValueError(f"No .jsonl files found in {project_dir}")

    all_sessions: list[ConversationEfficiency] = []
    cross_session_edits: dict[str, list[int]] = defaultdict(list)  # file -> [edits per session]
    cross_session_reads: dict[str, int] = Counter()
    all_prompt_lengths: list[int] = []
    total_questions = 0
    total_commands = 0
    total_corrections = 0
    total_prompts = 0

    for fpath in files:
        result = _analyze_session_workflow(fpath)
        if result is None:
            continue

        session, edits_per_file, reads_per_file, prompts = result
        all_sessions.append(session)

        # Aggregate cross-session file data
        for fp, count in edits_per_file.items():
            cross_session_edits[fp].append(count)
        for fp, count in reads_per_file.items():
            cross_session_reads[fp] += count

        # Aggregate prompt stats
        for p in prompts:
            length = len(p)
            all_prompt_lengths.append(length)
            total_prompts += 1
            if "?" in p:
                total_questions += 1
            if COMMAND_PATTERNS.match(p.strip()):
                total_commands += 1
            if CORRECTION_PATTERNS.search(p):
                total_corrections += 1

    if not all_sessions:
        raise ValueError(f"No analyzable sessions found in {project_dir}")

    # Compute averages
    avg_token_ratio = (
        sum(s.token_ratio for s in all_sessions) / len(all_sessions)
        if all_sessions else 0.0
    )
    avg_tool_success = (
        sum(s.tool_success_rate for s in all_sessions) / len(all_sessions)
        if all_sessions else 0.0
    )
    avg_edits = (
        sum(s.avg_edits_per_file for s in all_sessions) / len(all_sessions)
        if all_sessions else 0.0
    )

    # File churn analysis
    churn_files: list[FileChurn] = []
    for fp, edit_counts in cross_session_edits.items():
        total_edits = sum(edit_counts)
        if total_edits < 5:
            continue
        reads = cross_session_reads.get(fp, 0)
        churn_files.append(FileChurn(
            path=fp,
            total_edits=total_edits,
            session_count=len(edit_counts),
            avg_edits_per_session=total_edits / len(edit_counts),
            max_edits_in_session=max(edit_counts),
            total_reads=reads,
            read_edit_ratio=reads / total_edits if total_edits > 0 else 0,
        ))
    churn_files.sort(key=lambda f: -f.total_edits)

    # Prompt stats
    sorted_lengths = sorted(all_prompt_lengths)
    median_len = sorted_lengths[len(sorted_lengths) // 2] if sorted_lengths else 0
    prompt_stats = PromptStats(
        total_prompts=total_prompts,
        avg_length_chars=sum(all_prompt_lengths) / len(all_prompt_lengths) if all_prompt_lengths else 0,
        median_length_chars=median_len,
        short_prompts=sum(1 for l in all_prompt_lengths if l < 50),
        medium_prompts=sum(1 for l in all_prompt_lengths if 50 <= l < 200),
        long_prompts=sum(1 for l in all_prompt_lengths if l >= 200),
        question_count=total_questions,
        command_count=total_commands,
        correction_count=total_corrections,
        question_ratio=total_questions / total_prompts if total_prompts > 0 else 0,
        correction_ratio=total_corrections / total_prompts if total_prompts > 0 else 0,
    )

    # Session length buckets
    length_buckets = _compute_length_buckets(all_sessions)
    optimal = _determine_optimal_length(length_buckets)

    # Recommendations
    recs = _generate_recommendations(
        all_sessions, avg_token_ratio, avg_tool_success,
        avg_edits, churn_files, prompt_stats, optimal,
    )

    return WorkflowReport(
        sessions=sorted(all_sessions, key=lambda s: -s.token_ratio),
        avg_token_ratio=avg_token_ratio,
        avg_tool_success=avg_tool_success,
        avg_edits_per_file=avg_edits,
        high_churn_files=churn_files[:15],
        prompt_stats=prompt_stats,
        length_buckets=length_buckets,
        optimal_length=optimal,
        recommendations=recs,
    )


def _analyze_session_workflow(
    fpath: Path,
) -> tuple[ConversationEfficiency, dict[str, int], dict[str, int], list[str]] | None:
    """Analyze a single session for workflow metrics.

    Returns (session_metrics, edits_per_file, reads_per_file, prompt_texts)
    """
    ai_calls = 0
    input_tokens = 0
    output_tokens = 0
    tool_total = 0
    tool_failed = 0
    edits_per_file: dict[str, int] = Counter()
    reads_per_file: dict[str, int] = Counter()
    prompts: list[str] = []
    corrections = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    session_id = fpath.stem[:12]
    date_str = "?"

    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)

                # Track timestamps
                ts_str = obj.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except ValueError:
                        pass

                msg_type = obj.get("type")

                # User messages: extract prompt text
                if msg_type == "user":
                    msg = obj.get("message", {})
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip():
                            prompts.append(content.strip())
                            if CORRECTION_PATTERNS.search(content):
                                corrections += 1
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "").strip()
                                    if text:
                                        prompts.append(text)
                                        if CORRECTION_PATTERNS.search(text):
                                            corrections += 1
                    continue

                if msg_type != "assistant":
                    continue

                msg = obj.get("message", {})
                if not isinstance(msg, dict) or msg.get("type") != "message":
                    continue

                ai_calls += 1
                usage = msg.get("usage", {})
                inp = (usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                out = usage.get("output_tokens") or 0
                input_tokens += inp
                output_tokens += out

                # Analyze tool calls
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    if not isinstance(tool_input, dict):
                        tool_input = {}

                    tool_total += 1

                    fp = tool_input.get("file_path", "")

                    if tool_name == "Edit" and fp:
                        edits_per_file[fp] += 1
                    elif tool_name == "Read" and fp:
                        reads_per_file[fp] += 1

                # Check for tool results indicating failure
                # (tool_result entries come as separate messages in Claude Code traces)

    except (json.JSONDecodeError, OSError):
        return None

    if ai_calls == 0:
        return None

    if first_ts:
        date_str = first_ts.strftime("%Y-%m-%d")

    duration = 0.0
    if first_ts and last_ts:
        duration = (last_ts - first_ts).total_seconds() / 3600

    token_ratio = output_tokens / input_tokens if input_tokens > 0 else 0
    tool_success = (tool_total - tool_failed) / tool_total if tool_total > 0 else 1.0

    files_edited = len(edits_per_file)
    total_edits = sum(edits_per_file.values())
    avg_edits_pf = total_edits / files_edited if files_edited > 0 else 0
    high_churn = [fp for fp, count in edits_per_file.items() if count >= 5]

    correction_rate = corrections / len(prompts) if prompts else 0

    session = ConversationEfficiency(
        session_id=session_id,
        date=date_str,
        ai_calls=ai_calls,
        duration_hours=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        token_ratio=token_ratio,
        tool_calls_total=tool_total,
        tool_calls_failed=tool_failed,
        tool_success_rate=tool_success,
        files_edited=files_edited,
        total_edits=total_edits,
        avg_edits_per_file=avg_edits_pf,
        high_churn_files=high_churn,
        correction_count=corrections,
        correction_rate=correction_rate,
    )

    return session, dict(edits_per_file), dict(reads_per_file), prompts


def _compute_length_buckets(sessions: list[ConversationEfficiency]) -> list[SessionLengthBucket]:
    """Group sessions by duration and compute avg metrics per bucket."""
    buckets_def = [
        ("< 30min", 0, 0.5),
        ("30min-1h", 0.5, 1),
        ("1-2h", 1, 2),
        ("2-4h", 2, 4),
        ("4-8h", 4, 8),
        ("8h+", 8, 999),
    ]

    results: list[SessionLengthBucket] = []
    for label, lo, hi in buckets_def:
        bucket = [s for s in sessions if lo <= s.duration_hours < hi]
        if not bucket:
            continue

        results.append(SessionLengthBucket(
            label=label,
            session_count=len(bucket),
            avg_token_ratio=sum(s.token_ratio for s in bucket) / len(bucket),
            avg_tool_success=sum(s.tool_success_rate for s in bucket) / len(bucket),
            avg_edits_per_file=sum(s.avg_edits_per_file for s in bucket) / len(bucket),
            avg_corrections=sum(s.correction_count for s in bucket) / len(bucket),
        ))

    return results


def _determine_optimal_length(buckets: list[SessionLengthBucket]) -> str:
    """Determine the optimal session length based on metrics."""
    if not buckets:
        return "Not enough data"

    # Score each bucket: higher token ratio and lower corrections = better
    best_label = buckets[0].label
    best_score = 0.0

    for b in buckets:
        if b.session_count < 2:
            continue
        # Composite score: token efficiency + tool success - correction penalty
        score = b.avg_token_ratio * 1000 + b.avg_tool_success - b.avg_corrections * 0.1
        if score > best_score:
            best_score = score
            best_label = b.label

    return best_label


def _generate_recommendations(
    sessions: list[ConversationEfficiency],
    avg_token_ratio: float,
    avg_tool_success: float,
    avg_edits: float,
    churn_files: list[FileChurn],
    prompt_stats: PromptStats,
    optimal_length: str,
) -> list[str]:
    """Generate actionable workflow recommendations."""
    recs: list[str] = []

    # Token efficiency
    if avg_token_ratio < 0.002:
        recs.append(
            f"Low token efficiency ({avg_token_ratio:.4f} output/input ratio). "
            "Claude is re-reading a lot of context for little output. "
            "Try shorter, more focused sessions or break large tasks into sub-tasks."
        )

    # Edit convergence
    if avg_edits > 4:
        recs.append(
            f"High average edits per file ({avg_edits:.1f}). "
            "Claude is iterating heavily on files. Provide clearer specs upfront "
            "or describe the expected behavior in CLAUDE.md."
        )

    # File churn
    if churn_files:
        worst = churn_files[0]
        if worst.total_edits > 20:
            recs.append(
                f"\"{worst.path}\" has been edited {worst.total_edits} times across "
                f"{worst.session_count} sessions. Consider breaking it into smaller "
                "modules or adding architecture notes to CLAUDE.md."
            )

    # Corrections
    if prompt_stats.correction_ratio > 0.1:
        pct = prompt_stats.correction_ratio * 100
        recs.append(
            f"{pct:.0f}% of your prompts are corrections. Sessions with fewer "
            "corrections correlate with longer initial prompts that set clear context."
        )

    # Prompt length
    if prompt_stats.avg_length_chars < 30:
        recs.append(
            f"Average prompt is only {prompt_stats.avg_length_chars:.0f} characters. "
            "Slightly longer prompts with context reduce back-and-forth."
        )

    # Optimal session length
    recs.append(
        f"Your most efficient session length is {optimal_length} based on "
        "token efficiency and correction rates."
    )

    return recs
