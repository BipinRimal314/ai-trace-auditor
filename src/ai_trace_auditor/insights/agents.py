"""Multi-agent trace reconstruction and plan tracking.

Analyzes:
1. Agent tool calls from conversation traces — delegation patterns, types, cost
2. Plans from ~/.claude/plans/ — complexity, completion
3. Teams from ~/.claude/teams/ — structure, message volume
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Agent Analysis ──────────────────────────────────────────────────────────


@dataclass
class AgentCall:
    """A single Agent tool invocation."""
    session_id: str
    agent_id: str  # tool_use id
    description: str
    subagent_type: str  # "general-purpose", "Explore", "Plan", ""
    prompt_length: int
    run_in_background: bool
    timestamp: datetime | None


@dataclass
class AgentStats:
    """Aggregate statistics for agent usage."""
    total_calls: int
    by_type: list[tuple[str, int]]  # [(type, count), ...]
    background_count: int
    foreground_count: int
    avg_prompt_length: float
    longest_prompt: int
    sessions_using_agents: int
    total_sessions: int
    agent_adoption_rate: float  # sessions_using_agents / total_sessions


# ── Plan Analysis ───────────────────────────────────────────────────────────


@dataclass
class PlanSummary:
    """Parsed summary of an implementation plan."""
    filename: str
    title: str
    step_count: int
    has_context: bool
    has_steps: bool
    estimated_complexity: str  # "simple", "moderate", "complex"


@dataclass
class PlanStats:
    """Aggregate plan statistics."""
    total_plans: int
    avg_steps: float
    complexity_distribution: dict[str, int]  # {"simple": 3, "moderate": 5, ...}
    plans: list[PlanSummary]


# ── Team Analysis ───────────────────────────────────────────────────────────


@dataclass
class TeamMember:
    """A member of a Claude Code team."""
    name: str
    agent_type: str
    model: str


@dataclass
class TeamInbox:
    """Message statistics for a team agent's inbox."""
    agent_name: str
    message_count: int
    senders: dict[str, int]  # {sender_name: count}
    first_message: str | None
    last_message: str | None


@dataclass
class TeamSummary:
    """Summary of a Claude Code team."""
    name: str
    description: str
    members: list[TeamMember]
    inboxes: list[TeamInbox]
    total_messages: int


# ── Combined Report ─────────────────────────────────────────────────────────


@dataclass
class AgentReport:
    """Complete multi-agent intelligence report."""
    agent_stats: AgentStats
    plan_stats: PlanStats
    teams: list[TeamSummary]


# ── Parsers ─────────────────────────────────────────────────────────────────


def analyze_agents(projects_dir: Path | None = None) -> AgentStats:
    """Analyze Agent tool calls across all conversation traces."""
    if projects_dir is None:
        projects_dir = Path.home() / ".claude" / "projects"

    calls: list[AgentCall] = []
    sessions_with_agents: set[str] = set()
    total_sessions = 0

    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        for fpath in proj_dir.glob("*.jsonl"):
            total_sessions += 1
            session_id = fpath.stem[:12]
            session_has_agent = False

            try:
                with open(fpath, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        obj = json.loads(line)
                        if obj.get("type") != "assistant":
                            continue
                        msg = obj.get("message", {})
                        if not isinstance(msg, dict):
                            continue
                        content = msg.get("content", [])
                        if not isinstance(content, list):
                            continue

                        ts = None
                        ts_str = obj.get("timestamp")
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            except ValueError:
                                pass

                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") != "tool_use" or block.get("name") != "Agent":
                                continue

                            inp = block.get("input", {})
                            if not isinstance(inp, dict):
                                continue

                            session_has_agent = True
                            calls.append(AgentCall(
                                session_id=session_id,
                                agent_id=block.get("id", "")[:12],
                                description=inp.get("description", "")[:80],
                                subagent_type=inp.get("subagent_type", "") or "general-purpose",
                                prompt_length=len(inp.get("prompt", "")),
                                run_in_background=bool(inp.get("run_in_background")),
                                timestamp=ts,
                            ))
            except (json.JSONDecodeError, OSError):
                continue

            if session_has_agent:
                sessions_with_agents.add(session_id)

    type_counts = Counter(c.subagent_type for c in calls)
    bg_count = sum(1 for c in calls if c.run_in_background)
    prompt_lengths = [c.prompt_length for c in calls]

    return AgentStats(
        total_calls=len(calls),
        by_type=type_counts.most_common(),
        background_count=bg_count,
        foreground_count=len(calls) - bg_count,
        avg_prompt_length=sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0,
        longest_prompt=max(prompt_lengths) if prompt_lengths else 0,
        sessions_using_agents=len(sessions_with_agents),
        total_sessions=total_sessions,
        agent_adoption_rate=len(sessions_with_agents) / total_sessions if total_sessions > 0 else 0,
    )


def analyze_plans(plans_dir: Path | None = None) -> PlanStats:
    """Analyze implementation plans from ~/.claude/plans/."""
    if plans_dir is None:
        plans_dir = Path.home() / ".claude" / "plans"

    if not plans_dir.exists():
        return PlanStats(total_plans=0, avg_steps=0, complexity_distribution={}, plans=[])

    plans: list[PlanSummary] = []

    for path in sorted(plans_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            title = _extract_plan_title(text)
            steps = _count_plan_steps(text)
            has_context = "## Context" in text or "## context" in text
            has_steps = steps > 0

            if steps <= 3:
                complexity = "simple"
            elif steps <= 8:
                complexity = "moderate"
            else:
                complexity = "complex"

            plans.append(PlanSummary(
                filename=path.name,
                title=title,
                step_count=steps,
                has_context=has_context,
                has_steps=has_steps,
                estimated_complexity=complexity,
            ))
        except OSError:
            continue

    complexity_dist = Counter(p.estimated_complexity for p in plans)
    avg_steps = sum(p.step_count for p in plans) / len(plans) if plans else 0

    return PlanStats(
        total_plans=len(plans),
        avg_steps=avg_steps,
        complexity_distribution=dict(complexity_dist),
        plans=plans,
    )


def _extract_plan_title(text: str) -> str:
    """Extract the plan title from Markdown."""
    for line in text.splitlines()[:5]:
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            # Remove "Plan:" prefix if present
            if title.lower().startswith("plan:"):
                title = title[5:].strip()
            return title[:80]
    return "(untitled)"


def _count_plan_steps(text: str) -> int:
    """Count distinct steps/phases/tasks in a plan."""
    step_patterns = [
        r"^###\s+\d",           # ### 1. Something
        r"^###\s+Step",         # ### Step 1
        r"^###\s+Phase",        # ### Phase 1
        r"^\d+\.\s+\*\*",      # 1. **Bold step**
        r"^-\s+\[[ x]\]",      # - [ ] checklist item
        r"^###\s+[A-Z]",       # ### Capitalized heading (sub-section)
    ]

    count = 0
    for line in text.splitlines():
        line = line.strip()
        for pattern in step_patterns:
            if re.match(pattern, line):
                count += 1
                break

    return count


def analyze_teams(teams_dir: Path | None = None) -> list[TeamSummary]:
    """Analyze team configurations and inbox messages."""
    if teams_dir is None:
        teams_dir = Path.home() / ".claude" / "teams"

    if not teams_dir.exists():
        return []

    results: list[TeamSummary] = []

    for team_dir in sorted(teams_dir.iterdir()):
        if not team_dir.is_dir():
            continue

        config_path = team_dir / "config.json"
        if not config_path.exists():
            continue

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Parse members
        members = []
        for m in config.get("members", []):
            members.append(TeamMember(
                name=m.get("name", "unknown"),
                agent_type=m.get("agentType", ""),
                model=m.get("model", ""),
            ))

        # Parse inboxes
        inboxes: list[TeamInbox] = []
        inbox_dir = team_dir / "inboxes"
        total_messages = 0

        if inbox_dir.exists():
            for inbox_path in sorted(inbox_dir.glob("*.json")):
                agent_name = inbox_path.stem
                try:
                    data = json.loads(inbox_path.read_text(encoding="utf-8"))
                    if not isinstance(data, list):
                        continue

                    msg_count = len(data)
                    total_messages += msg_count

                    senders: dict[str, int] = Counter()
                    first_ts = None
                    last_ts = None

                    for msg in data:
                        if isinstance(msg, dict):
                            sender = msg.get("from", "unknown")
                            senders[sender] += 1
                            ts = msg.get("timestamp")
                            if ts:
                                if first_ts is None:
                                    first_ts = ts
                                last_ts = ts

                    inboxes.append(TeamInbox(
                        agent_name=agent_name,
                        message_count=msg_count,
                        senders=dict(senders),
                        first_message=first_ts,
                        last_message=last_ts,
                    ))
                except (json.JSONDecodeError, OSError):
                    continue

        results.append(TeamSummary(
            name=config.get("name", team_dir.name),
            description=config.get("description", "")[:120],
            members=members,
            inboxes=inboxes,
            total_messages=total_messages,
        ))

    return results


def build_agent_report(
    projects_dir: Path | None = None,
    plans_dir: Path | None = None,
    teams_dir: Path | None = None,
) -> AgentReport:
    """Build the complete multi-agent intelligence report."""
    return AgentReport(
        agent_stats=analyze_agents(projects_dir),
        plan_stats=analyze_plans(plans_dir),
        teams=analyze_teams(teams_dir),
    )
