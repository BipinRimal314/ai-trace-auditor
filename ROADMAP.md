# AI Trace Auditor — Product Roadmap

Based on the full Claude Code data pipeline available at `~/.claude/`:

```
~/.claude/
├── projects/          # 44 project directories, 877 .jsonl conversation files (427 MB)
├── debug/             # 94 debug trace files (118 MB) — timestamped system logs
├── telemetry/         # Failed telemetry events (27 MB)
├── sessions/          # Active session metadata (PID, cwd, startedAt)
├── history.jsonl      # Global command history across all sessions
├── file-history/      # File modification snapshots per session
├── plans/             # 10+ implementation plans (Markdown)
├── teams/             # Team configs + agent inboxes
├── tasks/             # Task state per team
├── shell-snapshots/   # Shell environment captures
├── plugins/           # Installed plugin registry
└── settings/          # Permission rules, allowed tools, domain whitelists
```

We're currently ingesting only `projects/*.jsonl` (conversation traces). The roadmap below covers both new data sources and analytical capabilities.

---

## Phase 1: Cross-Project Intelligence (v0.4)

### What users get
"I use Claude Code across 15 projects. Show me the full picture."

### New capabilities

**1.1 Cross-project dashboard**
Currently `aitrace insights` analyzes one project directory. Users want to see all projects at once.

```
aitrace insights                    # all projects, summary view
aitrace insights --project Website  # filter to one project
aitrace insights --compare          # side-by-side project comparison
```

What to show per project:
- Total sessions, calls, tokens, estimated cost
- Date range (first seen → last active)
- Primary language/framework (inferred from file extensions in Read/Edit calls)
- Top files touched

What to show in comparison:
- Which project consumes the most tokens?
- Which project has the highest edit-to-read ratio (most iteration)?
- Where do you spend the most time vs. where does Claude do the most work?

**Data source:** Already available. `~/.claude/projects/` has 44 directories. Just iterate all of them.

**1.2 Project detection and naming**
The directory names like `-Users-bipinrimal-Downloads-Ekline-AgentsTest` are ugly. Detect the actual project name from:
- The last path segment (usually the repo name)
- `package.json` name field if it exists in the cwd
- `pyproject.toml` project name
- Git remote URL

Display as "AgentsTest" or "ekline-app", not the full escaped path.

**1.3 Time-series tracking**
Track how usage changes over time. Store a lightweight summary after each `aitrace insights` run:

```json
{"date": "2026-03-16", "project": "Website", "sessions": 3, "calls": 665, "tokens_in": 80000000, "tokens_out": 197000, "cost": 156.00}
```

Append to `~/.aitrace/history.jsonl`. On subsequent runs, show trends:
```
Website: 8,593 calls this month (+23% vs last month)
Cost: $2,064 (↓12% — sessions getting shorter and more focused)
```

---

## Phase 2: Debug Log Integration (v0.5)

### What users get
"What went wrong in that session, and how long did it take to recover?"

### New capabilities

**2.1 Debug log parser**
`~/.claude/debug/*.txt` contains timestamped system logs with:
- Permission rule loading and changes
- MCP server connections and failures
- Plugin loading
- Session startup/shutdown timing
- Error log entries

Parse these to extract:
- Session boot time (startup → first AI call latency)
- Permission configuration complexity (how many allow rules?)
- MCP connection failures and retries
- Error frequency and types

**2.2 Session health score**
Combine conversation traces + debug logs to score each session:

| Signal | What it indicates |
|--------|------------------|
| High error rate in debug log | Unstable environment |
| Many permission denials | Workflow friction from safety rules |
| Long gaps between AI calls | User thinking, or blocked? |
| Repeated Read→Edit→Read cycles on same file | Struggling with a change |
| Tool call failures (Bash exit code != 0) | Failed commands, environment issues |

Output: "Session health: 73/100. 4 failed bash commands, 2 permission blocks, 12-minute gap at 14:32 UTC."

**2.3 Error taxonomy**
Categorize errors across all sessions:
- Bash command failures (which commands fail most?)
- Permission denials (which tools get blocked most?)
- Build failures (npm/npx errors)
- Git conflicts
- File not found

Show: "Your top 3 friction points: npm build failures (23 occurrences), permission blocks on Write (8), git push rejections (5)."

---

## Phase 3: Workflow Optimization (v0.6)

### What users get
"How can I use Claude Code more effectively?"

### New capabilities

**3.1 Conversation efficiency scoring**
Not all sessions are equal. Measure:

- **Token efficiency**: output tokens / input tokens ratio. Low ratio = Claude is re-reading a lot of context for little output. Recommendation: break into smaller sessions or use more targeted prompts.
- **Tool success rate**: successful tool calls / total tool calls. Low rate = environment issues or wrong approach. Recommendation: fix environment setup.
- **Edit convergence**: how many edits before a file stabilizes (no more edits in the session). High count = iterating too much. Recommendation: provide clearer specs upfront.
- **Restart penalty**: how much context is re-read when starting a new session on the same project. High penalty = CLAUDE.md needs better project state documentation.

**3.2 Prompt pattern analysis**
Analyze user messages (from the `user` type entries) for patterns:
- Average prompt length (characters, not tokens)
- Ratio of questions vs. commands
- Use of context-setting vs. jumping straight to requests
- Frequency of corrections ("no, I meant...", "that's wrong", "undo that")

Output: "You average 45-character prompts. Sessions where you wrote 100+ character initial prompts had 30% fewer correction cycles."

No content is stored or transmitted. Analysis happens locally, results are aggregate statistics.

**3.3 File churn detection**
Identify files with high edit-then-revert patterns:
- File edited 10+ times in one session
- File where the final state is close to the initial state (wasted work)
- Files that get edited across many sessions (persistent complexity)

Recommendation: "tracker.html was edited 23 times across 5 sessions. Consider refactoring it or documenting its expected behavior in CLAUDE.md so Claude gets it right faster."

**3.4 Optimal session length**
Correlate session length with output quality metrics:
- Do longer sessions produce more tool failures? (context degradation)
- Is there a sweet spot where edit convergence is fastest?
- When does cache efficiency peak and decline?

Output: "Your most productive sessions are 1-3 hours. After 4 hours, your edit convergence rate drops 40% — Claude starts repeating approaches."

---

## Phase 4: Team & Multi-Agent Intelligence (v0.7)

### What users get
"How are agents and teams performing across my workspace?"

### New capabilities

**4.1 Agent trace reconstruction**
When Claude Code spawns sub-agents (`Agent` tool calls), reconstruct the full agent tree:
- Which agents were spawned, by whom?
- How many tokens did each agent consume?
- Did agent results get used or ignored?
- Agent success rate (did the spawning conversation use the agent's output?)

Currently the `Agent` tool is the 7th most used tool (133 calls). Understanding agent delegation patterns reveals whether multi-agent usage is efficient or wasteful.

**4.2 Team inbox analysis**
`~/.claude/teams/` contains team configurations and agent inboxes. Parse:
- Which team agents exist?
- Message volume per agent
- Response patterns

**4.3 Plan tracking**
`~/.claude/plans/` contains implementation plans (10+ Markdown files). Parse:
- How many plans were created?
- How many reached completion? (compare plan steps to actual tool calls)
- Average plan complexity (number of steps)
- Plan adherence rate (did the session follow the plan?)

Output: "You created 10 plans. 7 were partially followed, 2 were fully executed, 1 was abandoned. Average plan has 8 steps; you follow ~5."

---

## Phase 5: Predictive & Proactive Features (v0.8+)

### What users get
"Don't just tell me what happened. Tell me what's coming."

### New capabilities

**5.1 Cost forecasting**
Based on usage trends, project next month's cost:
- Linear projection from recent sessions
- Seasonal patterns (weekday vs. weekend, sprint cycles)
- Per-project growth rates

"At current usage, March will cost ~$2,400. Website project is growing 15% month-over-month."

**5.2 Context window pressure**
Detect sessions approaching context limits:
- Track cumulative input tokens per session
- Flag when a session is likely being context-compressed
- Correlate context pressure with output quality

"3 of your last 10 sessions hit context compression. Sessions after compression had 2x more correction cycles."

**5.3 CLAUDE.md effectiveness scoring**
Compare sessions with and without CLAUDE.md context:
- Do sessions in projects with CLAUDE.md have fewer corrections?
- Which CLAUDE.md sections reduce unnecessary reads? (Claude doesn't re-discover what's documented)
- Suggest CLAUDE.md additions based on frequently re-read files

"Adding stage-simulator/App.tsx architecture notes to CLAUDE.md could save ~12 Read calls per session (based on 5 recent sessions)."

**5.4 Permission optimization**
Analyze permission rules from debug logs:
- Which allow rules are actually used? (remove unused ones)
- Which denials happen repeatedly? (candidate for auto-allow)
- Permission surface area score (how exposed is your setup?)

"You have 110 allow rules. 34 have never been triggered. 8 denials happened repeatedly for Bash(python3:*) — consider adding it."

---

## Improvements to Existing Features

### Insights command

**Better file path display**
Currently shows full absolute paths truncated with `...`. Instead:
- Strip the project root prefix (show `src/App.tsx` not `/Users/.../src/App.tsx`)
- Detect project root from the session's `cwd` field
- Group files by directory for a tree-like view

**Time zone support**
Hourly activity is currently UTC only. Add `--timezone` flag:
```
aitrace insights --timezone Asia/Kathmandu
```
Default: detect from system locale.

**Date range filtering**
```
aitrace insights --since 2026-03-01
aitrace insights --last 7d
aitrace insights --last 30d
```

**Output formats**
- `--format html` — self-contained HTML report with charts (Chart.js or inline SVG)
- `--format json` — already exists
- `--format csv` — for spreadsheet analysis

**Comparative insights**
```
aitrace insights --compare "last 7d" "previous 7d"
```
Shows delta: "AI calls: 1,200 (+15%). Cost: $340 (-8%). Edit convergence: improved 20%."

### Audit command

**Severity weighting**
Currently all requirements have equal weight in the overall score. Weight by severity:
- Mandatory requirements: 3x weight
- Recommended: 1x weight
- Best practice: 0.5x weight

**Requirement profiles**
Pre-built profiles for common use cases:
```
aitrace audit traces.json --profile chatbot
aitrace audit traces.json --profile agent
aitrace audit traces.json --profile rag-pipeline
```
Each profile adjusts which requirements apply and their weights.

**Delta reports**
Compare two reports:
```
aitrace audit traces-v1.json -o report1.json --report-format json
aitrace audit traces-v2.json -o report2.json --report-format json
aitrace diff report1.json report2.json
```
Shows: "3 requirements improved, 1 regressed, 14 unchanged."

### Ingest command

**Streaming ingestion**
For large trace files (your biggest is 27.8 MB), stream-parse instead of loading entire file into memory.

**Validation mode**
```
aitrace ingest traces.json --validate
```
Check trace quality without running analysis: "87% of spans have timestamps, 12% missing model_used, 3 spans have malformed content."

---

## Architecture Evolution

### Plugin system (v0.5+)
Allow custom analyzers via a plugin interface:
```python
from ai_trace_auditor.plugins import InsightPlugin

class MyCustomInsight(InsightPlugin):
    name = "sprint-velocity"

    def analyze(self, sessions: list[SessionSummary]) -> WorkflowPattern:
        # Custom logic
        return WorkflowPattern(...)
```

Register via `pyproject.toml` entry points. Enables company-specific insights without forking.

### Storage layer (v0.6+)
Currently everything is computed on-the-fly from raw files. For trend tracking and faster queries, add an optional SQLite cache:
```
~/.aitrace/
├── cache.db          # SQLite: sessions, daily summaries, trends
├── history.jsonl     # Append-only trend data
└── config.toml       # User preferences (timezone, default project)
```

### Web dashboard (v1.0)
Self-hosted HTML dashboard generated by `aitrace dashboard`:
- Opens in browser
- All data stays local (no server, no API)
- Interactive charts (daily usage, cost trends, tool distribution)
- Session timeline with drill-down
- File hotspot heatmap
- Exportable PDF for team sharing

---

## Priority Matrix

| Feature | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Cross-project dashboard | High | Low | v0.4 — next |
| Project name detection | Medium | Low | v0.4 |
| Time zone support | Medium | Low | v0.4 |
| Date range filtering | Medium | Low | v0.4 |
| Time-series tracking | High | Medium | v0.4 |
| Debug log parser | Medium | Medium | v0.5 |
| Session health score | High | Medium | v0.5 |
| Conversation efficiency | High | Medium | v0.6 |
| File churn detection | Medium | Low | v0.6 |
| Optimal session length | High | Medium | v0.6 |
| Agent trace reconstruction | Medium | Medium | v0.7 |
| Plan tracking | Medium | Medium | v0.7 |
| Cost forecasting | High | Low | v0.8 |
| CLAUDE.md effectiveness | High | High | v0.8 |
| Permission optimization | Medium | Medium | v0.8 |
| Web dashboard | High | High | v1.0 |
| Plugin system | Medium | High | v0.5+ |

---

## Competitive Positioning

No tool in the market does this. The closest:
- **Claude Code Analytics API** (Anthropic) — org-level metrics for Team/Enterprise plans. Per-developer productivity, not per-session workflow intelligence.
- **Cursor analytics** — basic token usage. No workflow patterns, no file hotspots, no efficiency scoring.
- **GitHub Copilot metrics** — acceptance rate, lines suggested. No conversation analysis, no cost breakdown.

AI Trace Auditor is the only tool that gives individual developers deep, local, private insight into how they use AI coding assistants. The data never leaves your machine.

That last point is the moat. Every competitor who tries to build this will need to collect your data to analyze it. We analyze it where it lives.
