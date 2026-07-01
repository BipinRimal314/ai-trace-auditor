# AI Trace Auditor Best-In-Game Plan

**Created:** 2026-05-05  
**Scope:** Product-owner plan for making AI Trace Auditor the strongest practical open-source trace-to-compliance evidence tool in the current market.  
**Current product:** v0.16.1, Python CLI + MCP + GitHub Action + early web route, 301+ tests, EU AI Act / NIST / ISO / SOC 2 requirement registry, primary-source verification.

## Product Thesis

The common belief is: AI observability tools already solve trace governance because they collect traces, run evals, and show dashboards.

They solve a different problem. Langfuse, Phoenix, Arize, LangSmith, and OpenTelemetry help teams understand what happened. AI Trace Auditor should answer the question those tools do not answer directly:

> Given these traces, code paths, and system facts, what compliance evidence do we have, what obligations apply, what is missing, who must fix it, and what can we hand to an auditor?

That is the product. Not another trace viewer. Not another generic EU AI Act checklist. A translator from AI runtime behavior to auditor-ready evidence.

## Winning Position

AI Trace Auditor wins if it becomes the default local/open-source layer between:

```
Langfuse / Phoenix / OTel / LangSmith / raw provider logs
        -> AI Trace Auditor
        -> scoped obligations + evidence pack + CI gates + auditor export
```

The product should be boring in the best way: deterministic, source-cited, local-first, reproducible, and difficult to accuse of making things up.

## Market Reality

- The EU AI Act Service Desk states that from **2026-08-02**, AI agents that classify as high-risk are subject to Chapter III high-risk requirements; some high-risk systems embedded in regulated products move on the 2027 timeline.
- OpenTelemetry GenAI semantic conventions are still **Development** status, so field names and event schemas can drift.
- Phoenix and Arize are strong at tracing and evals. Langfuse is strong at LLM observability and enterprise compliance posture. AI Trace Auditor should not compete by displaying traces. It should compete by turning traces into legal/operational evidence.

## Product Gaps

### Gap 1: No First-Class Scoping Intake

Current state: the CLI accepts `--risk-level`, and docs mention Annex III scope checks, but the product does not yet feel like it knows the user.

Missing:

- Provider/deployer/importer/distributor role classification.
- High-risk Annex III pathway.
- Annex I embedded regulated product pathway.
- Chatbot / RAG / agent / HR / finance / education / biometric / law-enforcement profile.
- EU-market exposure.
- General-purpose AI model vs downstream AI system distinction.
- Output: obligation profile, not raw requirement dump.

Product requirement:

```
aitrace intake
aitrace intake --profile agent
aitrace audit traces.json --intake .aitrace-intake.yaml
aitrace scan ./repo --intake .aitrace-intake.yaml
```

### Gap 2: Obligation Coverage Is Too Trace-Centered

Trace evidence is the wedge, but best-in-game needs the full operating spine for AI systems.

Add or strengthen:

- Article 9: risk management system.
- Article 10: data governance.
- Article 11: technical documentation / Annex IV.
- Article 12: logging.
- Article 13: provider-to-deployer transparency.
- Article 14: human oversight.
- Article 15: accuracy, robustness, cybersecurity.
- Article 25: value-chain accountability.
- Article 26: deployer duties.
- Article 50: deployer-to-user transparency.
- Article 72: post-market monitoring.
- Article 73: serious incident reporting.

Product rule: separate **legal obligations**, **trace-supported evidence**, **manual evidence**, and **quality/security best practices**. Never let a percentage score imply legal compliance.

### Gap 3: Evidence Pack Is Not Yet The Main Product

Current product can generate reports and evidence packs, but the center of gravity is still “audit command output.”

The buyer wants an artifact:

- Executive summary.
- Scope/intake answer sheet.
- Obligation matrix.
- Evidence found.
- Evidence missing.
- Clause citation.
- Source quote verification.
- Risk/severity.
- Owner.
- Due date.
- Fix recommendation.
- Export: zip containing Markdown, JSON, PDF, Mermaid diagrams, raw trace summary, and reproducibility metadata.

Product requirement:

```
aitrace evidence-pack traces.json --intake .aitrace-intake.yaml --out evidence/
```

### Gap 4: Integrations Are File-First

File imports are useful for developers. Teams want pull-based connectors.

Prioritized connectors:

1. Langfuse API pull.
2. Phoenix / Arize OpenTelemetry export path.
3. LangSmith export.
4. OTel Collector receiver/exporter guide.
5. Datadog/New Relic later.

Product requirement:

```
aitrace import langfuse --project PROJECT --since 7d --out traces.jsonl
aitrace import phoenix --endpoint http://localhost:6006 --since 7d --out traces.jsonl
```

### Gap 5: No OTel GenAI Schema Adapter Layer

Because OTel GenAI conventions are Development status, AI Trace Auditor must treat schema drift as a product feature.

Missing:

- Schema version detection.
- Unknown-field inventory.
- Field coverage by semantic convention version.
- Adapter warnings when fields map imperfectly.
- Compatibility tests with fixture snapshots.

Product requirement:

```
aitrace schema-health traces.json
```

### Gap 6: Agent Oversight Is Not Sharp Enough Yet

Multi-agent DAG scoring exists. Now make it the AI-security bridge.

Agent oversight checks:

- Unauthorized tool call.
- Missing human approval for sensitive action.
- Tool-call escalation.
- Dangerous delegation chain.
- Circular delegation.
- Cross-agent liability shift.
- Exfiltration-like output behavior.
- Monitor disagreement.
- Policy bypass phrased as task decomposition.

Product requirement:

```
aitrace audit traces.json --profile agent --oversight
```

### Gap 7: No Killer Demo

The product needs one undeniable demo that explains itself in 90 seconds.

Build a sample LangGraph or CrewAI agent with:

- benign task,
- hidden risky behavior,
- incomplete trace logging,
- missing human approval,
- value-chain / multi-agent issue,
- before/after fix.

Demo flow:

```
aitrace scan samples/risky-agent --traces samples/risky-agent/traces/failing.jsonl --evidence-pack out/failing
aitrace scan samples/risky-agent --traces samples/risky-agent/traces/passing.jsonl --evidence-pack out/passing
aitrace diff out/failing/report.json out/passing/report.json
```

The README should show the before/after table. This is the product’s “oh, I get it” moment.

## Release Target: v0.17.0 “Scope To Evidence”

Goal: turn AI Trace Auditor from a powerful CLI into a guided compliance evidence workflow.

Ship these in v0.17.0:

1. Scoping intake.
2. Obligation profiles.
3. Evidence pack as first-class command.
4. Agent oversight profile v1.
5. Schema health report for OTel/GenAI traces.
6. Killer risky-agent demo.
7. README rewrite around “scope -> audit -> evidence -> fix -> prove.”

Do not ship hosted SaaS in this release. Do not build auth, billing, org dashboards, or team workflows yet. Those come after the local evidence loop is excellent.

## Architecture Plan

### New Domain Modules

Create:

```
src/ai_trace_auditor/intake/
src/ai_trace_auditor/profiles/
src/ai_trace_auditor/schema/
src/ai_trace_auditor/oversight/
```

Responsibilities:

- `intake/`: questionnaire model, YAML load/save, role/risk/scope inference.
- `profiles/`: maps intake answers to requirement filters and weights.
- `schema/`: trace schema version detection, unknown field inventory, OTel GenAI compatibility reporting.
- `oversight/`: agent-specific controls that produce findings independent of legal requirements.

### Existing Modules To Extend

- `cli.py`: add commands and wire flags.
- `models/`: add `IntakeProfile`, `ObligationProfile`, `SchemaHealthReport`, `OversightFinding`.
- `regulations/registry.py`: support profile-aware requirement filtering.
- `evidence/pack.py`: make evidence pack generation the primary artifact.
- `reports/`: add obligation matrix and schema health sections.
- `tests/`: fixture-driven tests for intake, profiles, schema health, oversight, and evidence pack.

## Implementation Plan

### Phase 0: Product Cleanup Before Feature Work

Outcome: reduce confusion before adding scope.

- [ ] Update README claim from “EU AI Act Articles 11, 12, 13, 25” to current reality: Articles 12, 19, 25, 50, Annex IV, NIST, ISO, SOC 2, best practices, plus generated docs/flow support.
- [ ] Remove stale roadmap contradictions: v0.16.0 vs v0.16.1, “PDF report output future” vs current PDF route.
- [ ] Move Claude Code analytics roadmap into `docs/legacy/claude-code-analytics-roadmap.md`.
- [ ] Make “coverage score is not compliance” visible in README quick start.

### Phase 1: Intake And Profiles

Outcome: product answers “what applies to me?” before audit.

- [ ] Add `models/intake.py`.
- [ ] Add `intake/questionnaire.py`.
- [ ] Add `intake/serializer.py`.
- [ ] Add `profiles/obligation_profile.py`.
- [ ] Add `profiles/rules.py`.
- [ ] Add CLI:
  - `aitrace intake`
  - `aitrace profile show .aitrace-intake.yaml`
  - `aitrace audit --intake .aitrace-intake.yaml`
  - `aitrace scan --intake .aitrace-intake.yaml`
- [ ] Tests:
  - chatbot non-high-risk -> Article 50 + GDPR + best practices, not Article 12/14.
  - HR high-risk -> Articles 9-15 + 25/26 + post-market monitoring.
  - agent profile -> adds oversight controls.

### Phase 2: Evidence Pack First

Outcome: the zip folder becomes the product artifact.

- [ ] Promote evidence pack command:
  - `aitrace evidence-pack traces.json --intake .aitrace-intake.yaml --out evidence/`
- [ ] Evidence pack contents:
  - `00-executive-summary.md`
  - `01-scope-intake.md`
  - `02-obligation-matrix.csv`
  - `03-trace-evidence.md`
  - `04-agent-oversight.md`
  - `05-schema-health.md`
  - `06-fix-plan.md`
  - `report.json`
  - optional `report.pdf`
- [ ] Add owner/due-date fields as optional metadata, not a database.
- [ ] Tests verify files exist and contain clause IDs, evidence paths, and fix recommendations.

### Phase 3: Schema Health

Outcome: AI Trace Auditor becomes robust to OTel/GenAI drift.

- [ ] Add `schema/health.py`.
- [ ] Detect:
  - OTel GenAI-looking fields.
  - Langfuse export fields.
  - raw provider fields.
  - unknown/unmapped fields.
- [ ] Report:
  - mapped evidence fields.
  - unmapped but useful fields.
  - missing fields for selected obligation profile.
  - convention warning when schema is inferred from Development-status OTel GenAI fields.
- [ ] Add CLI:
  - `aitrace schema-health traces.json`
- [ ] Tests with OTel, Langfuse, raw JSONL fixtures.

### Phase 4: Agent Oversight Pack

Outcome: the product starts looking like AI security infrastructure, not only compliance paperwork.

- [ ] Add `oversight/findings.py`.
- [ ] Add deterministic checks:
  - sensitive tool called without approval span.
  - agent delegates to unknown agent.
  - circular delegation.
  - tool escalation after failure.
  - output contains secret-like token from hidden context fixture.
  - multi-agent chain has no clear responsible owner.
- [ ] Add severity:
  - `critical`, `high`, `medium`, `low`.
- [ ] Add report section and JSON output.
- [ ] Tests with multi-agent fixtures.

### Phase 5: Killer Demo

Outcome: one command explains the product.

- [ ] Create `samples/risky-agent/`.
- [ ] Include:
  - `README.md`
  - `traces/failing.jsonl`
  - `traces/passing.jsonl`
  - `.aitrace-intake.yaml`
  - generated `expected/failing-report.md`
  - generated `expected/passing-report.md`
- [ ] Add README before/after table.
- [ ] Add short demo script:
  - `python -m ai_trace_auditor scan samples/risky-agent --traces ...`
- [ ] Add test ensuring sample commands run.

### Phase 6: Integration Pullers

Outcome: reduce friction from “export a file manually.”

- [ ] Stabilize Langfuse importer.
- [ ] Add Phoenix/Arize import path through OTLP/exported JSON.
- [ ] Add documented OTel Collector recipe.
- [ ] Keep direct SaaS credentials optional and local-only.

## Priority Order

If energy is limited:

1. README/roadmap cleanup.
2. Intake/profile system.
3. Evidence pack command.
4. Risky-agent demo.
5. Agent oversight.
6. Schema health.
7. Integrations.

If the goal is career signal for 0Labs:

1. Agent oversight.
2. Risky-agent demo.
3. Schema health.
4. Evidence pack.
5. Intake/profile system.

If the goal is users:

1. Intake/profile system.
2. Evidence pack.
3. Risky-agent demo.
4. Integrations.
5. Schema health.
6. Agent oversight.

Recommended path: user path first, but design agent oversight into the profiles from day one.

## Definition Of “Best In Game For Now”

AI Trace Auditor reaches “best in game for now” when a new user can:

1. Install it.
2. Answer a scope questionnaire.
3. Import traces from a common source or run a sample.
4. Generate an evidence pack.
5. See exactly which obligations apply.
6. See which evidence exists and which is missing.
7. See source clauses and quote verification.
8. See agent oversight findings if the system is agentic.
9. Fix instrumentation.
10. Re-run and prove improvement with a diff.

Anything outside that loop can wait.

## Do Not Build Yet

- Auth.
- Billing.
- Multi-tenant org dashboard.
- Hosted trace storage.
- Legal advice chatbot.
- Generic compliance checklist blogware.
- LLM-generated legal conclusions.

These are attractive traps. The current moat is deterministic evidence translation.

## Resume/Career Payoff

After v0.17.0, the CV bullet becomes:

> Built AI Trace Auditor v0.17, a local-first compliance evidence engine that scopes EU AI Act obligations, imports LLM/agent traces, checks OTel/GenAI schema coverage, flags agent oversight failures, and generates auditor-ready evidence packs with primary-source clause verification.

That is stronger than “open-source compliance auditor.” It says product judgment, regulatory precision, AI trace engineering, and agent safety all at once.
