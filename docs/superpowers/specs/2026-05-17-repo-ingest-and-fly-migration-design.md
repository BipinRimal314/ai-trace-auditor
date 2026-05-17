# AI Trace Auditor — Repo Ingestion & Fly.io Migration

**Date:** 2026-05-17
**Status:** Design approved, awaiting written-spec review before plan.

## Summary

Two changes to AI Trace Auditor:

1. Accept a public GitHub repo URL as input and produce a compliance report by combining the existing trace audit pipeline with a new governance-document checklist scan. The repo is treated as an evidence bundle, never as code to legally interpret.
2. Migrate hosting from Railway to Fly.io.

## Why

- Real compliance evidence regulators ask for is spread across both trace logs (Article 12, Article 19) and governance documents (Annex IV, Article 25, Article 50, ISO 42001, SOC 2 CC1). The current product only audits the first half. A repo input is the cheapest interface that covers both.
- v0.14.0 shipped 60% fabricated EU AI Act requirements because the abstraction-fabrication curve was ignored. Any repo-ingestion design must stay on the concrete end of that curve — file presence and literal-string content checks, not AST parsing or semantic code interpretation.
- Railway's free tier is the only reason we are still on it; Fly.io is a same-shape Docker host with better cost predictability and supports the longer-running operations (git clone, weasyprint) that repo ingestion needs.

## Non-Goals

- Static code analysis of LLM SDK calls. High abstraction, high fabrication risk. Excluded.
- Running cloned repo code to generate traces. Sandbox cost not justified at v1.
- Private repo support (PAT/OAuth). Public repos only in v1.
- Replacing the existing file-upload and sample-trace flows. Repo ingestion is additive.

## Architecture

One new top-level module under `src/ai_trace_auditor/`:

```
repo/
├── __init__.py
├── fetcher.py        # Shallow git clone to tmpdir with size + time caps
├── trace_finder.py   # Walk tree, classify JSON/JSONL by trace shape
├── doc_scanner.py    # Walk tree, evaluate governance-doc detectors
├── manifest.yaml     # Governance file patterns mapped to requirement IDs
└── report.py         # Combine trace audit + doc checklist into RepoAuditReport
```

Web layer adds one route — `POST /audit/repo` — and one template — `repo_results.html`. CLI gains one command — `aitrace audit-repo <url>`. No changes to existing regulation YAMLs, no changes to the existing audit pipeline.

### Why this boundary

`repo/` produces inputs (trace artifacts) for the existing audit pipeline and emits its own document-checklist output. It does not interpret legal text directly; that interpretation is captured statically in `manifest.yaml`, which is audited under the same Compliance Verification Gate as existing regulation YAMLs. Result: only one new claims surface, and it is auditable in the same way as the existing surfaces.

## The Governance Manifest

`repo/manifest.yaml` is the only new file containing legal claims. Every entry must satisfy the existing Compliance Verification Gate (`legal_text`, `verified_against_primary`, `framework_nature`, `compliance_tier`) plus a `detector` block.

Three detector kinds — and only three:

1. **`file_presence`** — filename matches any of N patterns (case-insensitive). Output: `found` / `not_found` plus the matching path.
2. **`content_contains`** — a file at one of N path patterns exists AND contains any string from a small literal allow-list (case-insensitive). Each `content_contains` detector entry specifies both `file_patterns` and `phrases`; scope is never "all files in the repo". Output: `found_with_phrase` / `found_without_phrase` / `not_found`.
3. **`config_key`** — a known config filename contains a known key. Output: `key_present` / `key_absent`. The detector never interprets the key's value as compliant; presence is treated only as evidence of capability, never of compliance.

Excluded by design: AST parsing, regex over source code, "LLM SDK call" detection, anything that infers purpose from variable or function names. These are the abstraction-curve traps that produced the v0.14.0 fabrications.

Output language for every check is forced into an unfabricatable form:

- *"File `MODEL_CARD.md` not found. Annex IV(2)(b) requires technical documentation of the AI system."*
- *"File `MODEL_CARD.md` found at `docs/model-card.md`. Reviewer must confirm contents satisfy Annex IV(2)(b)."*

The product never asserts a found file satisfies a requirement — only that the candidate evidence is present.

### Initial manifest seed (~12 entries)

- Annex IV(2)(a) general description — README presence
- Annex IV(2)(b) design specifications — MODEL_CARD / model card patterns
- Annex IV(2)(c) intended purpose — README contains intended-use language
- Annex IV(2)(d) third-party data and components — `THIRD_PARTY_NOTICES`, `DATA_SOURCES.md`, license file
- Article 12(1) logging capability — presence of OTEL/Langfuse/Arize config files
- Article 19 retention — config key for retention duration in known config files
- Article 25 value-chain liability — `SECURITY.md`, data-processing agreement docs
- Article 50 disclosure — README/UI text contains an entry from a small allow-list of AI-disclosure phrases
- ISO 42001 Clause 6 — `AI_POLICY.md`, `AI_GOVERNANCE.md` patterns
- ISO 42001 Clause 7.2 — `ROLES.md` or governance-role section in README
- SOC 2 CC1 — `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`
- SOC 2 CC7 — incident response document patterns

Each entry written `legal_text` first, then detector. Same discipline as the existing regulation YAMLs.

## Data Flow

### Web

1. User pastes `https://github.com/owner/repo` on `/audit` (new field alongside file upload + sample selector).
2. `POST /audit/repo` validates URL shape, calls `fetcher.clone(url)`.
3. `fetcher.clone` performs `git clone --depth=1` into `$REPO_TMPDIR/aitrace-repo-{uuid}/` (where `REPO_TMPDIR` defaults to `/tmp/aitrace` so the Fly volume is reused), enforces 50MB total cap and 30s timeout, deletes `.git/` post-clone, returns the path. Raises one of: `InvalidRepoURL`, `RepoTooLarge`, `RepoFetchTimeout`, `PrivateRepo`, `RepoNotFound`.
4. `trace_finder.find(path)` walks the tree. For each `.json` or `.jsonl` file under 5MB, sniffs the first object and classifies as OTEL-shape, Langfuse-shape, or chat-message-shape, otherwise ignores. Returns `list[TraceArtifact]`.
5. `doc_scanner.scan(path, manifest)` walks the tree once, evaluates each detector, returns `list[DocEvidence]`.
6. If `trace_finder` returned artifacts, concatenate and run the existing `audit_service.run_audit`. If none, the trace section of the report says "No trace artifacts found in repo. Documentation evidence only."
7. `report.combine` produces `RepoAuditReport` with three sections:
   - Trace audit (existing tiered scoring, or "no traces" notice)
   - Documentation evidence table (per requirement: present / absent / partial)
   - Restricted tiered score — only over requirements that were actually checkable
8. Render `repo_results.html`. PDF download path reuses the existing `/audit/pdf/{report_id}` route.
9. Tmpdir wiped on every exit path (success, exception, timeout).

### CLI

`aitrace audit-repo <url>` mirrors the web flow, prints the existing markdown report, exits non-zero if any deterministic check fails.

## Sandboxing

- Public repos only. Private repo support deferred to v2.
- Hard caps: 50MB total clone, 30s clone timeout, 60s scan timeout.
- No code execution. We only read files.
- `.git/` deleted post-clone.
- Tmpdir wiped on every exit path including exceptions (use `tempfile.TemporaryDirectory` context manager, plus an explicit `shutil.rmtree` in a `finally` for the rare cases where the context manager itself raises).

## Error Handling

Each typed error maps to a specific message rendered through the existing `error.html`:

| Error | HTTP | Message |
|---|---|---|
| `InvalidRepoURL` | 400 | "Not a valid GitHub repo URL. Expected `https://github.com/owner/repo`." |
| `RepoNotFound` | 404 | "Repository not found or not public. Trace Auditor v1 only supports public repos." |
| `PrivateRepo` | 403 | "Repository is private. Trace Auditor v1 only supports public repos." |
| `RepoTooLarge` | 413 | "Repo exceeds 50MB cap. Upload trace files directly instead." |
| `RepoFetchTimeout` | 504 | "Clone exceeded 30 seconds. Try a smaller repo." |
| Unexpected exception | 500 | Logged with full traceback; user sees generic "Audit failed" message. |

No silent failures. Every exit path either returns a report or renders an explicit error.

## Testing

Three layers, matching the existing 301-test suite discipline.

### Unit tests

- `test_fetcher.py` — happy path against a checked-in tiny fixture repo, size cap exceeded, timeout, invalid URL, private/404 response, `.git` stripped after clone, tmpdir cleaned on exception. Mock `subprocess.run` where a real git call is impractical.
- `test_trace_finder.py` — fixtures for each classifier shape (OTEL, Langfuse, raw chat JSONL); false-positive guard (`package.json` is not a trace); file-size guard; malformed JSON returns empty rather than crashes.
- `test_doc_scanner.py` — one fixture repo tree per detector kind. Verifies `file_presence` matches any pattern variant, `content_contains` is case-insensitive and respects the allow-list, `config_key` finds keys in `.env.example` / YAML / TOML.
- `test_manifest.py` — every manifest entry passes the Compliance Verification Gate and has a well-formed detector. Same validator shape as existing regulation-YAML tests.

### Integration tests

Three checked-in fixture repos under `tests/fixtures/repos/`:

- `repo-with-traces/` — has `traces.jsonl` plus `MODEL_CARD.md`. Expect: trace audit runs, doc checklist mostly green.
- `repo-docs-only/` — governance docs present, no traces. Expect: "no traces" notice, doc checklist runs.
- `repo-bare/` — empty README only. Expect: doc checklist mostly red, trace section absent, no crash.

### Web tests

- `test_server_repo.py` — `POST /audit/repo` happy path, missing `repo_url`, invalid URL, fetch error renders `error.html` with correct status, PDF download works on repo audit reports.

Coverage target stays at 80%, matching project norms.

## Deployment Migration: Railway → Fly.io

### Files added

- `fly.toml` at project root: region `iad`, internal port 8001, `http_service` with `auto_stop_machines = true` and `min_machines_running = 0` for cost.

### Files modified

- `Dockerfile` — add `git` to the `apt-get install` line; confirm `[pdf]` extras are installed.

### Env vars (set via `fly secrets set`)

- `PORT` — set automatically by Fly.
- `PDF_TMPDIR=/tmp/aitrace`
- `REPO_TMPDIR=/tmp/aitrace`
- `MAX_REPO_BYTES=52428800`
- `REPO_FETCH_TIMEOUT=30`

### Volume

One persistent volume mounted at `/tmp/aitrace` (1GB) for clone scratch space. Not strictly required, but cleaner than relying on tmpfs sizing.

### Deploy commands

```bash
fly launch --no-deploy
fly volumes create aitrace_tmp --size 1
fly secrets set PDF_TMPDIR=/tmp/aitrace REPO_TMPDIR=/tmp/aitrace MAX_REPO_BYTES=52428800 REPO_FETCH_TIMEOUT=30
fly deploy
```

### Cutover

1. Deploy to Fly.
2. Verify `/`, `/audit`, `/audit/run` with a known sample trace, `/audit/repo` with a known public repo, PDF download.
3. Update DNS/CNAME — decision deferred to deploy time (custom subdomain vs `fly.dev` URL).
4. Update `CLAUDE.md` deployment section.
5. Tear down Railway service only after Fly is observed stable for one week.

### Rollback

`railway.toml` remains in the repo until Fly is observed stable for one week. If Fly fails, `railway up` reverts.

## Out of Scope (Explicit)

- Private repo authentication.
- Repo size beyond 50MB.
- Any form of code execution from cloned repos.
- AST or semantic interpretation of source code.
- Automated DNS migration (manual decision at cutover time).
- Multi-region Fly deployment.

## Open Questions

None blocking. DNS choice (custom subdomain vs `fly.dev`) deferred to cutover.
