# 2-Minute Demo Script

Recording script for the demo video/GIF linked from the README. Target: a
hiring manager or maintainer decides in two minutes whether this tool is real.

**Setup before recording:** fresh terminal, repo cloned, `pip install ai-trace-auditor`
already run (don't record the download bars), font size large enough for mobile.

---

## Beat 1 — The problem (0:00–0:15)

Say (or caption):

> "Your observability stack collects AI traces. The EU AI Act wants compliance
> evidence — transparency obligations start December 2026. Nothing translates
> one into the other. This does, locally, with no LLM in the loop."

## Beat 2 — One command (0:15–0:45)

```bash
aitrace audit examples/golden_path/sample_traces.json -o report.md --show-dag
```

Let the output scroll. Pause on:

- the trace summary (1 trace, 4 spans, multi-agent detected: 3 agents)
- "Loaded 72 requirements from EU AI Act, ISO 42001, ..."
- the coverage table (48 satisfied / 14 partial / 5 missing)
- the per-agent score table
- the Mermaid DAG at the end

## Beat 3 — The report is the product (0:45–1:30)

Open `report.md`, scroll slowly through ONE requirement — good pick:
`EU-AIA-12.1a` (event timestamps, SATISFIED, cites Article 12) — then ONE gap —
good pick: the temperature-parameter gap, showing the exact missing trace field
and the OTel attribute that fixes it.

Say:

> "Every check cites the article. Gaps come with the exact field to add.
> No LLM decides compliance — the checks are deterministic and the EU AI Act
> ones are validated verbatim against the official text in CI."

## Beat 4 — Scoping + CI (1:30–2:00)

```bash
aitrace audit examples/golden_path/sample_traces.json --profile chatbot
```

> "Profiles scope the audit to your system shape — chatbot, agent, RAG,
> high-risk — instead of dumping every requirement."

```bash
aitrace diff report-v1.json report-v2.json
```

> "And `diff` fails CI when coverage regresses. Install: pip install
> ai-trace-auditor. Everything stays local."

End card: repo URL + `pip install ai-trace-auditor`.

---

## Recording notes

- Total ≤ 2:10. If over, cut Beat 3 scrolling, never Beat 2.
- Record at 1080p minimum; GIF export at 12–15 fps is fine for the README.
- Suggested tools: `asciinema` + `agg` (terminal-only), or QuickTime + Gifski.
- Commit the GIF as `docs/demo.gif` and link it under the README's 60-Second
  Demo section.
