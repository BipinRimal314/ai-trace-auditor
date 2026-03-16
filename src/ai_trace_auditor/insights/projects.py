"""Cross-project discovery and naming for Claude Code traces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectInfo:
    """Discovered Claude Code project with resolved name."""
    dir_path: Path
    raw_name: str  # directory name as-is
    display_name: str  # human-readable project name
    cwd: str  # original working directory
    session_count: int
    total_size_bytes: int


def decode_project_dir_name(dir_name: str) -> str:
    """Decode a Claude Code project directory name back to a filesystem path.

    Claude Code encodes paths like /Users/bipin/Downloads/Website
    as -Users-bipin-Downloads-Website. The leading dash indicates root /.
    """
    if dir_name.startswith("-"):
        return "/" + dir_name[1:].replace("-", "/")
    return dir_name.replace("-", "/")


def detect_project_name(dir_path: Path) -> str:
    """Detect a human-readable project name from a Claude Code project directory.

    Strategy (in priority order):
    1. Read cwd from first session file and extract the last path segment
    2. Look for package.json, pyproject.toml in the cwd for a project name
    3. Fall back to the last meaningful segment of the decoded directory name
    """
    # Strategy 1: Get cwd from session data
    cwd = _get_cwd_from_sessions(dir_path)
    if cwd:
        # Use last path segment as project name
        name = Path(cwd).name
        if name and name != "/":
            return name

    # Strategy 2: Decode directory name and use last segment
    decoded = decode_project_dir_name(dir_path.name)
    segments = [s for s in decoded.split("/") if s]
    if segments:
        # Skip generic segments like "Users", "Downloads", username
        skip = {"Users", "Downloads", "home", "src", "app"}
        meaningful = [s for s in segments if s not in skip and not s.startswith(".")]
        if meaningful:
            return meaningful[-1]

    return dir_path.name


def _get_cwd_from_sessions(dir_path: Path) -> str | None:
    """Extract the working directory from the first session file."""
    for jsonl_path in sorted(dir_path.glob("*.jsonl"))[:1]:
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    cwd = obj.get("cwd")
                    if cwd:
                        return cwd
        except (json.JSONDecodeError, OSError):
            pass
    return None


def discover_projects(claude_dir: Path | None = None) -> list[ProjectInfo]:
    """Discover all Claude Code projects with session traces.

    Args:
        claude_dir: Path to ~/.claude/projects/. Auto-detected if None.

    Returns:
        List of ProjectInfo sorted by total size (largest first).
    """
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"

    if not claude_dir.exists():
        return []

    projects: list[ProjectInfo] = []
    for d in claude_dir.iterdir():
        if not d.is_dir():
            continue

        jsonl_files = list(d.glob("*.jsonl"))
        if not jsonl_files:
            continue

        total_size = sum(f.stat().st_size for f in jsonl_files)
        cwd = _get_cwd_from_sessions(d) or decode_project_dir_name(d.name)
        display_name = detect_project_name(d)

        projects.append(ProjectInfo(
            dir_path=d,
            raw_name=d.name,
            display_name=display_name,
            cwd=cwd,
            session_count=len(jsonl_files),
            total_size_bytes=total_size,
        ))

    projects.sort(key=lambda p: -p.total_size_bytes)
    return projects


def get_strip_prefix(project: ProjectInfo) -> str:
    """Get the path prefix to strip from file paths in reports."""
    if project.cwd and project.cwd != "/":
        cwd = project.cwd
        if not cwd.endswith("/"):
            cwd += "/"
        return cwd
    return ""
