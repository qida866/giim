# GIIM Task 2 engineering report

**Latest live acceptance follow-up:** [Final A/B verification](TASK2_FINAL_LIVE_ACCEPTANCE_REPORT.md) passed both remaining workflows with ten Gemini calls and $0.00785 estimated. All five original controlled scenarios now have passing real-model evidence across preserved rounds. Post-run checks passed 175 component and 130 backend tests. Live 503 recovery was not exercised; its bounded retry behavior passed local tests. The implementation report below is historical, including its original live-verification blockers.

**Follow-up acceptance audit:** see [TASK2_ACCEPTANCE_REPORT.md](TASK2_ACCEPTANCE_REPORT.md) for fresh executions, the irrelevant-evidence bug found in the fake Verifier, its fix, and the expanded 107-test result. This original implementation report remains a dated record of its stated commit and must not supersede the acceptance findings.

November 10, 2026. Branch: `feature/mcp-agent`. Validated implementation commit: **`74b64d380078c05f7bdad0b69e6f0517b62e3801`**. The documentation/evidence commit follows this code commit. See [exact commands and environment](../evidence/mcp-agent/commands.md), [usage guide](../mcp-agent.md) and [complete changed-file manifest](../evidence/mcp-agent/files-changed.txt).

## A. Executive summary

Implemented an independently installed official MCP server and Google ADK analyst over the existing Phase 3 GIIM REST API. Five read-only tools expose search, recent events, event evidence/history, observed coverage and readiness. The analyst has distinct Researcher, Coordinator and Verifier roles, typed outputs, real MCP communication, bounded execution, one revision, per-request evidence isolation, and deterministic checks that reject fabricated event/article/source references and unsupported quote text.

Locally verified: **103 new tests passed**, **130 original tests passed**, and **24/24 authored fake-model evaluation cases met their expected outcomes**. Two existing live-provider tests were deliberately not run because billable access was not authorized; no existing test was weakened. A separate actual-backend smoke exercised FastAPI, PostgreSQL, Qdrant and cached CPU bge-m3 with authored fixture records, then produced a gated answer through ADK and MCP.

**BLOCKED — MANUAL VERIFICATION REQUIRED:** live Gemini behavior/quality/usage, human ratings, production authentication/TLS deployment and visual inspection of the optional developer Web UI. None is represented as completed. No cloud resources, paid API calls, pushes, merges or production data changes were made.

## B. Architecture

The new packages live under `apps/mcp_server` and `apps/agent`, with a separate lock and non-root Docker image. The MCP server uses `httpx.AsyncClient` against a fixed route allowlist. It imports no backend, PostgreSQL or Qdrant internals. The Researcher uses ADK FunctionTools wrapping an official MCP client; stdio launches a dedicated MCP process. Official in-process and authenticated Streamable HTTP transport paths also pass tests.

The existing backend retains local bge-m3 dense query embeddings, Qdrant retrieval, PostgreSQL authority, HDBSCAN, LLM event review, revisions, deduplication, ingestion and frontend behavior. No Task 1 implementation was merged. A prerequisite public-release packaging defect required restoring two exact preexisting Phase 3 model modules and anchoring the `/models/` ignore rule; this is documented separately from Task 2 functionality.

See the [architecture diagram and trust boundaries](../mcp-agent.md#architecture-and-actual-execution). The default analyst is deliberately extractive: it returns attributed excerpts, not unconstrained generated synthesis or translation.

## C. Files changed

The [full manifest](../evidence/mcp-agent/files-changed.txt) enumerates all **81 paths: 76 added, five modified, zero deleted** against public base `651ffbc1a038c76c7c0d74be30bcc2b4538faf4d`. Major groups:

- `apps/mcp_server/`: independent package, schemas, REST adapter, normalization, strict inputs, transports, authored fixtures, protocol/security tests, optional fresh-stack smoke harness.
- `apps/agent/`: ADK roles/root workflow, fake/live model factory, gateway, evidence ledger, limits/callbacks, CLI/ADK entry, trace/redaction/statistics, 24-case evaluator, lock, Dockerfile and tests.
- `scripts/summarize_runs.py`, `scripts/sample_agent_evals.py`: private-trace aggregation and ten-case unrated human sampling.
- `.gitignore`, `.dockerignore`: trace/session/environment exclusions and packaging correction.
- `apps/api/src/models/event_revision.py`, `operations.py`: restore missing files already required by Phase 3 imports; no new schema or migration.
- README, architecture/licensing docs, reconnaissance, integration guide, this report and reviewed evidence artifacts.

Original tests, API dependency files, ingestion/search/clustering/publication services, frontend and migrations were not edited. No files were deleted from the base.

## D. Implemented MCP tools

All five tools have read-only/idempotent annotations, strict Pydantic inputs, typed structured responses, safe errors and bounded sizes. The route allowlist enforces capability restrictions independently of annotations.

| Tool | Inputs | Output / implementation |
|---|---|---|
| `giim_get_today_events` | window 24h/3d/7d, limit 1–25, optional language | Ranked API event cards with UUID, title/summary, actual timestamps, counts/languages/status. Language is a disclosed post-filter of at most 50 records. |
| `giim_search_events` | query 1–300, optional window, limit 1–20 | Existing semantic event order plus available source metadata. No invented similarity scores. Null window uses seven days. |
| `giim_get_event` | UUID | Current event, integer article/evidence IDs, publisher/URL/time/language, policy-limited excerpt, current support and compact revisions. |
| `giim_get_coverage` | none | Observed 24-hour coverage; unsupported global totals explicitly null. |
| `giim_check_ready` | none | API and exposed storage health; search readiness remains unknown when the base API does not expose model loading. |

Envelope: `{ok, data, error, truncated}`. The [guide](../mcp-agent.md#mcp-tool-contracts) specifies complete fields and REST mappings. `tools/list` exposes full JSON schemas. Default timeout is 10 seconds with one jittered retry for eligible failures. Structured response size is at most 20,000 bytes plus small protocol overhead. Unknown publisher excerpts are withheld; explicitly approved publisher caps cannot exceed 500 characters.

Card summaries are null with an explicit policy reason: upstream summaries can contain publisher fallback text without per-source rights information. Three additional protocol tests verify that recent-event, search and detail summaries cannot bypass the excerpt policy. Authorized detail-source excerpts still work; the existing API/frontend is untouched.

## E. Actual multi-agent workflow

1. A fresh request creates an ADK in-memory session, MCP connection, budget, trace and evidence ledger.
2. The Researcher chooses MCP tools. Search discovers IDs; full-detail calls are restricted to discovered IDs and record current evidence.
3. The custom Coordinator passes the ledger into session state and invokes its internal Writer LlmAgent for a structured draft.
4. A separate Verifier LlmAgent checks relevance, citations, support, conflicts and uncertainty using independent instructions/schema.
5. Python validates event/article/URL/publisher associations and exact authorized excerpt text against the immutable request evidence, even if the Verifier approves everything.
6. Any unresolved failure allows one revision, then refusal with no claims. Accepted output preserves all retrieved current support, attributes disagreements and explicitly acknowledges uncertainty.

There are four ADK nodes implementing three requested roles. Writer and Verifier have no tools. Fake `BaseLlm` emits real SDK function calls; it does not bypass the Runner, gateway, MCP server, REST transport, state or validation. Tests cover malicious approvals, repaired and irreparable citations, stale history, tool loops, malformed arguments, missing evidence and concurrent session isolation.

## F. Test results

| Verification | Result | Evidence |
|---|---|---|
| Clean public base | Failed import/migration because required model modules were absent | `baseline-clean.txt` |
| Restored baseline fast selection | 121 passed, 11 deselected | `baseline-fast.txt` |
| Restored baseline no-billing selection | 130 passed, 2 deselected, one existing warning | `backend-baseline-allowed.txt` |
| Final original regression selection | 130 passed, 2 deselected, same warning | `backend-regression.txt` |
| Final MCP + ADK suite | 103 passed, two dependency deprecation warnings, 24.02 s | `agent-and-mcp-tests.txt` |
| Real-backend smoke | All five tools and grounded three-source answer passed | `actual-api-smoke.json` |
| Ruff / format / pip dependency consistency | Passed; 44 Python files already formatted | `configuration-checks.txt` |
| Fresh analyst Docker build / installed-wheel demo | Passed, non-root runtime | `commands.md` |
| Portable fixture Compose | Configuration check passed; full second-stack build not repeated | `commands.md` |

All evidence paths above are under `docs/evidence/mcp-agent/`. [Exact commands](../evidence/mcp-agent/commands.md) include container commands, selected backend test exclusions, build metadata and the evaluation invocation.

Remaining unrun tests: `test_chat_basic` and `test_chat_with_system_message`, both existing live LLM integrations. They were excluded by the invocation's explicit `-k` expression, not changed in source. No remaining observed test failures. The structlog warning predates Task 2; uvicorn/websockets warnings arise in the new HTTP transport test's dependencies.

Development findings were fixed before final validation: initial adapter fixtures had UUID article IDs, wrong timestamp names and an unwrapped today list; actual API inspection/smoke exposed these mismatches. New contract regressions use integer article IDs, correct timestamp fields and the actual object wrapper. The optional seed helper also needed a collection initialization and verified-time payload field; no original GIIM data was involved.

The three new summary-policy tests initially failed because each parametrized case registered two unused mock routes. The mocks were scoped to the requested route while retaining strict call assertions; all policy assertions already held. This test-setup correction is preserved in a separate local commit rather than rewriting history.

## G. Evaluation results and limits

Dataset: `authored-giim-agent-v1` (see the exact version string in the JSON), 24 questions, eight categories, three cases each. Model: `giim-fake-v1`. The structured [evaluation](../evidence/mcp-agent/evaluation-fake.json) records actual timestamp, tested commit and build-checkout provenance (documentation/evidence edits pending). A [readable table](../evidence/mcp-agent/evaluation-table.txt) lists every case.

**24/24 expected outcomes:** ten verified attributed-excerpt answers and fourteen expected insufficient-evidence responses. Faults intentionally exercise fabricated source/event/article IDs, omitted disagreements, malicious source instructions, forbidden tools, malformed inputs and call limits. Current-event tests exclude superseded historical evidence. Multilingual cases use authored EN/ZH/ES/FR text and scripted fixture routing.

These are deterministic engineering tests, not a measured 100% answer accuracy, live-model result, multilingual recall benchmark or proof of general prompt-injection immunity. A separate Chinese-query smoke used real bge-m3 and Qdrant over only three authored articles; it establishes integration, not broad retrieval quality. Ten samples were exported for human inspection with `human_rating=null`; **human review was not performed**.

Live Gemini evaluation: **BLOCKED — MANUAL VERIFICATION REQUIRED**. No result or expected improvement is fabricated.

## H. Security and licensing

- Fixed read-only REST routes; no ingestion/admin tool, direct storage client, arbitrary URL fetch, file or shell tool. Only Researcher may call the five tools; callback and gateway enforce this independently.
- Hard limits: three tool rounds, five full details, nine calls, ten model calls, two drafts, 2,048 output tokens/call, 65 KB context, conservative 120,000-token reservation and 60-second default deadline.
- Event/article/publisher/URL/excerpt checks use current-request data only. Missing/truncated current evidence, fabricated references, omitted support and untrusted instruction patterns fail closed. Models cannot change the ledger or budget.
- Streamable HTTP binds loopback by default, validates Host/Origin, rejects wildcard origins, and requires a >=32-character bearer token for non-loopback exposure. TLS proxy, identity lifecycle and multi-user production authorization remain operator responsibilities.
- MCP subprocess does not inherit model, database or admin credentials. Secret patterns and known environment values are redacted from trace/log fields; raw third-party errors and article excerpts are not logged. Trace files are private and ignored. Arbitrary personal information may still appear in questions, so traces must remain private.
- Local value matching and pattern review found **no active local credential match** in candidate files or reachable history. Historical development credential examples and already-public notes remain in the preserved history; no history rewrite was performed. The scanner is not a comprehensive security/vulnerability certification; see [scope and findings](../evidence/mcp-agent/security-review.json).
- New committed datasets and exported samples are authored synthetic content. Unknown publisher excerpts default to withheld. Hosted-provider data terms and per-publisher permission require separate review. No license was added; direct SDK license observations are recorded in [licensing](../licensing.md#task-2-extension-review--november-10-2026).

## I. Performance and costs

Across the 24 fake-model evaluation requests, recorded p50 was **0.518 s** and p95 **0.550 s**, nearest-rank method. Mean tool calls were **1.958**, mean revisions **0.417**. Ten requests passed answer verification; fourteen intentionally refused. The 41.7% verified-answer rate is expected for this adversarial test mix and must not be marketed as accuracy. No execution errors or incomplete traces were recorded.

These timings measure a local Docker run with synthetic HTTP fixtures and scripted models, while other validation activity was running. They are neither Gemini latency nor an isolated-load benchmark. See [trace aggregates](../evidence/mcp-agent/trace-summary.json).

Fake-model measured tokens, tokens/second and estimated cost are **null**, not invented zero-usage measurements. The implementation records provider-reported prompt/output/thinking/total usage when available and calculates an estimate only when all required usage and operator-configured prices exist. Actual billing is not collected; no paid calls were made. Configured pricing may need extension for provider caching/tier rules.

## J. Remaining manual steps

1. Approve a live Gemini test and configure a private API key/current model/rates. Review allowed data and provider terms first; set both the environment opt-in and CLI `--live` (or ADK live setting).
2. Run a small authorized live test of relevance, structured output/tool use, independent verification, refusals, latency and actual reported usage. Record a separate result set; do not overwrite fake evidence.
3. Complete the ten unrated human samples, then assemble fresh independently adjudicated real-world evaluation data with appropriate rights.
4. If remote deployment is desired, separately review TLS/Host forwarding, token distribution/rotation, authentication, retention, resource limits and sustained load. Do not expose ADK Web as a public service.
5. Optionally inspect MCP Inspector and the ADK browser UI manually. API/protocol round trips are already tested; visual UX was not reviewed.
6. Review the feature branch and approve any eventual merge/push. This task did neither. Select a project code license separately if desired.

## K. Known limitations

Live Gemini availability and quality are unverified. The extractive gate intentionally forbids new factual synthesis/translation and may refuse useful answers when any current source is missing, disallowed, truncated, unverified-time or instruction-like. It cannot establish publisher truth, complete retrieval or semantic relevance on its own. The injection detector is heuristic; the capability and evidence boundaries provide additional protections, not universal attack immunity.

Coverage totals are limited to existing API aggregates; search readiness is unknown without model-loaded state. Event details are bounded to 100 articles and 20 revisions; no pagination expansion is performed by the agent. Language filtering of recent events is bounded and non-exhaustive. No conversational evidence memory, multi-tenant service, production deployment, load test or human-quality benchmark is claimed. The local lock is version-pinned without package hashes; the direct-dependency license review is not a complete transitive audit.

The optional test seed crosses two stores without a distributed transaction and is only for a new disposable stack; interruption can leave fixture vectors. Use a distinct fresh project rather than deleting existing data. The portable Compose file has only been configuration-validated; the same script-level workflow passed on the original isolated validation stack.

## L. Resume-safe claims

Supported by code and local evidence:

- Built five read-only MCP tools over a multilingual FastAPI news-intelligence backend, exposing semantic event search, current evidence, revisions, coverage and readiness through official MCP transports.
- Implemented a Google ADK Researcher/Coordinator/Verifier workflow with real MCP tool calls, structured state, one bounded revision and per-request evidence isolation; validated with scripted models through the real ADK runtime.
- Engineered deterministic event/article/URL/publisher and exact-excerpt validation that rejects fabricated references in tested adversarial cases, even when a model verifier approves them.
- Added bounded execution, private JSONL traces, measured-token hooks and configurable cost estimation, with 103 new passing automated tests and 24 reproducible synthetic scenarios.
- Validated integration against isolated PostgreSQL, Qdrant and cached bge-m3 using authored multilingual reports while preserving 130 original passing no-billing regression tests.

Do **not** claim production deployment, live Gemini accuracy, eliminated hallucinations, universal injection resistance, measured cost savings, independent human benchmark performance or broad multilingual recall. The requested phrase "evidence-grounded LLM generation" is supportable only with the qualification that the live adapter is implemented but the demonstrated generation is scripted and the final accepted output is extractive.

## M. Git summary

Branch: **`feature/mcp-agent`**, independent worktree from public `origin/main` at `651ffbc1a038c76c7c0d74be30bcc2b4538faf4d`.

Local implementation commits:

- `1803317`: restore missing preexisting Phase 3 model modules and record clean-base failure.
- `1fa54be`: initial read-only MCP implementation and transport tests.
- `5352656`: correct contracts against the actual running API; add smoke harness.
- `972518d`: complete ADK analyst, safeguards, tracing and evaluations.
- `58c1055`: prevent card summaries from bypassing publisher excerpt policy.
- **`74b64d380078c05f7bdad0b69e6f0517b62e3801`**: scope summary-policy mock routes; final code/test commit validated by the recorded image/tests/evaluation.

This report and evidence are committed afterward as documentation. The delivered branch-tip SHA is printed in the final handoff (and can be checked with `git log -1 --format=%H`); a committed file cannot embed its own future commit hash.

Local main remains **`28edc62816d44254d7b5b532beaeec421762bb34`**. Task 1 remains **`4e7b93135432d1885083822c764b8ac4c8d9feb7`**. Neither was modified or merged. Cached `origin/main` is unchanged. No remote push, force-push, history rewrite, cloud deployment, paid model call or deletion of existing work/data occurred.
