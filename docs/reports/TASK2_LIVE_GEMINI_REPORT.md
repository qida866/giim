# GIIM Task 2 — real Gemini integration report

**Result: 2 PASS, 3 FAIL across the five authorized workflows.** Real Gemini, Google ADK, MCP and GIIM's REST API completed the conflicting-evidence and adversarial-citation workflows. The first three workflows exposed implementation problems; fixes now pass local regression tests, but those scenarios have not been rerun with Gemini. Final-code live acceptance of normal research, cross-lingual answers and insufficient-evidence handling remains **BLOCKED pending a new authorization**. The five-workflow allowance is exhausted; no further live requests were made.

Executed November 10, 2026 Pacific time (trace timestamps are November 11 UTC), on `feature/mcp-agent`, starting at `07218fbc9de95599780029ec33910b215d6a22f8`. Corrected implementation commit: `ee8e879bb2af503dd718964db6ed45d8e60d7660`. Documentation/evidence are committed afterward. This is an execution-based engineering report, not independent certification or evidence of production readiness.

## Actual system and scope

The test used real `gemini-3.5-flash-lite` through the Gemini Developer API, Google ADK **2.14.0**, Google GenAI **2.34.0**, MCP **2.3.0**, Pydantic **2.14.3**, and Python **3.11.15**. Authentication used the approved private file mounted read-only and loaded inside the analyst process. No ADC, Vertex AI, cloud deployment or paid embedding API was used.

The actual workflow was `Coordinator → Researcher LlmAgent → typed FunctionTools → official MCP stdio client/server → existing GIIM FastAPI → PostgreSQL / bge-m3 / Qdrant`, followed by the Coordinator's internal Writer, independent Verifier and deterministic citation gate. Coordinator is an ADK orchestration node, not an additional model call. Writer and Verifier use separate structured outputs and have no tools.

An isolated `giim-gemini-trial` Compose project used GIIM's actual API implementation and cached CPU bge-m3 with its own PostgreSQL and Qdrant volumes. It held **two authored events, five authored reports and five real vectors**. No restricted publisher corpus was provided to Gemini. This demonstrates the real protocol/model/backend path on controlled data, not general news accuracy, production-scale retrieval or fresh ingestion.

A preflight and postflight exercised all five read-only MCP tools. The live Researcher used `giim_search_events` and `giim_get_event` in A, B, D and E: **eight actual MCP calls**. C did not invoke tools. The other tool capabilities were checked without a model, not autonomously selected by Gemini during these five workflows.

## Workflow results

| Case | Scenario | Result | Model attempts / returned usage | MCP calls | Latency | Known response estimate |
|---|---|---|---:|---:|---:|---:|
| A | Normal event research with citations | FAIL: UUID serialization after Researcher | 3 / 3 | 2 | 17.302 s | $0.0019991 |
| B | Chinese query requesting multilingual reports | FAIL: local Writer SDK schema conversion | 4 / 3 | 2 | 17.605 s | $0.0020322, incomplete |
| C | Exact stock-market prediction 100 years ahead | FAIL: Writer HTTP 400 | 2 / 1 | 0 | 9.043 s | $0.0003288, incomplete |
| D | Contradictory storm attendance reports | PASS: both reports cited, uncertainty retained | 5 / 5 | 2 | 6.367 s | $0.0031144 |
| E | Deliberately corrupted event ID and URL | PASS: Verifier and deterministic gate reject; final refusal | 7 / 7 | 2 | 10.808 s | $0.0060380 |

Raw runner output classified generic execution errors as BLOCKED. This report classifies A–C as **FAIL** because implementation errors prevented their acceptance criteria. The exported results retain both classifications. Empty claims satisfy citation-safety checks vacuously; they do not make A–C successful answers or successful insufficient-evidence tests.

### A — normal research

Gemini searched for the synthetic AI laboratory, retrieved its event and returned a `set_model_response` call with the valid event UUID. ADK's terminal tool validated the Pydantic object, then attempted ordinary JSON encoding of `model_dump()` containing Python UUID objects. It raised `TypeError: Object of type UUID is not JSON serializable`. Writer and Verifier were not reached. The returned error fallback contains no claims.

The fix adds UUID field serializers while retaining UUID validation internally. A regression invokes the actual installed ADK terminal tool; an offline full ADK test exercises the tool-return path through Writer, Verifier and the gate. The initial failing tests are preserved.

### B — cross-lingual research

After the UUID fix, the Chinese question retrieved the authored event with English, Chinese and Spanish evidence and reached Writer. The SDK rejected the citation schema's `exclusiveMinimum` locally. The exact exception was reproduced offline against the same installed SDK: `ValidationError` in the legacy `Schema` representation. The original runtime recorded the error category rather than its full message, so attribution is based on this deterministic reproduction.

The fix exposes the equivalent integer JSON Schema constraint `minimum: 1`; local strict validation still rejects zero, negatives, booleans and strings. Successful multilingual evidence retrieval is observed, but no complete verified multilingual answer was produced. Do not describe this as a passed cross-lingual live test.

### C — insufficient evidence

Researcher marked the future-prediction request insufficient and did not search. Writer then received HTTP 400. Safe diagnostics captured `ClientError` and the status, but intentionally omitted provider error text and request bodies. The exact server-side rejected field is therefore **not established**.

The outgoing structured-output configuration was changed from the SDK's narrower legacy `response_schema` conversion to Google's documented `response_json_schema`, with JSON MIME type. Local Pydantic and deterministic validation remain active. D and E subsequently completed using this path. That supports compatibility of the corrected path, but does not replace a live rerun of C.

### D — conflicting evidence

All roles completed. Researcher flagged a contradiction; the real Verifier and deterministic gate both approved the attributed evidence with uncertainty. Final claims were exactly:

- “Authored Demo EN reported 12 people at the synthetic storm briefing.” Event `00000000-0000-0000-0000-000000000004`, article `401`, publisher `Authored Demo en`, URL `https://demo.example.org/4/1`.
- “Authored Demo FR reported 18 people at the synthetic storm briefing.” Same event, article `402`, publisher `Authored Demo fr`, URL `https://demo.example.org/4/2`.

These are authored fixture URLs, not independently fetched publisher pages. Both excerpts are English despite the second report's `fr` label; this case demonstrates preservation of disagreement, not French translation quality. The system did not resolve which attendance count was true.

### E — unsupported citation rejection

The harness deliberately changed the real Writer draft's event ID to an unknown UUID and its URL to `https://fabricated.example.org/no-evidence`, preserving actual model usage. It applied corruption again after the single permitted revision. This tests a hostile model-output boundary; it is **not evidence that Gemini spontaneously invented those exact citations**.

Both real Verifier passes rejected the drafts. Both deterministic checks rejected unknown evidence references, invalid citations, omitted evidence and missing uncertainty; the second also flagged an unsupported claim. The final result was an explicit insufficient-evidence refusal with **zero claims and zero fabricated citations exposed**. Other draft-quality problems were observed and correctly blocked; this is not a claim of perfect generation.

## Traces, usage and budget

The [82 actual trace events](../evidence/live-gemini/traces.jsonl) contain 18 role events, 21 model starts, 19 returned model-usage events, eight MCP events, three verification events, three failures and five completion events. [Role responses](../evidence/live-gemini/role-responses.json) contain actual model text/function-call payloads with thought signatures and thought parts omitted. [Results](../evidence/live-gemini/results.json) include final answers, checks and authored evidence; [trace summary](../evidence/live-gemini/trace-summary.json) is derived from the original traces.

| Budget measure | Observed |
|---|---:|
| End-to-end workflows | 5 of 5; no scenario repeated |
| Reserved model-call attempts | 21 of 50 |
| Responses with usage | 19 |
| Attempts without returned usage | 2 |
| Reported input tokens | 27,750 |
| Reported output tokens | 2,075 |
| Reported thinking tokens | 0 |
| Reported total tokens | 29,825 |
| Known-response cost subtotal | $0.0135125 |
| Cumulative conservative reservation, including missing usage | $0.1488018 |
| Complete actual estimated charge | Unknown; stored as null |

Pricing used was **$0.30/M input and $2.50/M output including thinking**, from Google's [pricing page](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite). This is an estimate, not a reconciled provider bill. The two unreported attempts were retained at their full pre-call reservations, not assumed free. B failed locally and C returned HTTP 400, but neither supplies a complete usage record.

Before each call the runner reserved a conservative byte-based input allowance plus a 1,000-token margin and up to 2,048 output tokens. It enforced ten calls per workflow, 50 total, a $0.95 reservation ceiling, disabled retries, and bounded tool calls/timeouts. After each failure, execution stopped. Continuations ran only previously unattempted cases after investigation, carrying prior counts, spending and full missing-usage reservations forward. The ledger never reset.

Historical completion events for B/C originally contained partial sums. A local observability fix now returns null for incomplete totals and corrects summaries of older traces without rewriting the original events. In the summary, three requests have complete pricing; one verified answer and one expected refusal explain why the raw verification rate is 1/5 while scenario acceptance is 2/5. Neither ratio is a general accuracy benchmark.

## Local fixes and verification

Changed implementation files:

- `apps/agent/src/giim_agent/schemas.py`: JSON-safe UUID serialization and equivalent positive-integer wire schema.
- `apps/agent/src/giim_agent/hooks.py`: native JSON Schema structured-output configuration.
- `apps/agent/src/giim_agent/trace.py` and `stats.py`: explicit missing-attempt accounting and incomplete cost/token totals.
- `scripts/live_gemini_trial.py`: guarded continuation of unattempted scenarios, carried reservations and safe exception diagnostics.
- `apps/agent/tests/test_structured_tool.py`, `test_live_trial.py`, `test_observability.py`: SDK-path, schema, budget, redaction and accounting regressions.
- `apps/agent/Dockerfile`: include the trial script required by the packaged tests.

**128 component tests passed**, with two existing dependency deprecation warnings. Ruff checks/format checks and `pip check` passed, with network disabled. The separate [24/24 deterministic evaluation](../evidence/live-gemini/mocked-evaluation.json) used scripted models and authored keyword-routed fixtures; it is not Gemini quality evidence. [Regression output](../evidence/live-gemini/final-regressions.txt) and initial failure reproductions are retained.

The original API code, migrations, frontend and existing backend tests were not modified. The prior acceptance report records 130 original no-billing backend tests passing; that entire suite was not rerun for these agent-only fixes. The live tests themselves used the actual API, database and embedding/vector stack.

An incremental image rebuilt and installed both packages over the existing pinned dependency image; its **128 installed-package tests passed** in 27.13 seconds with network disabled and no source mounts. See [installed regression output](../evidence/live-gemini/installed-regressions.txt). A separate clean Docker build was blocked because its dependency layer was not cached and network was deliberately disabled; clean dependency download/build reproducibility was not reverified. The existing accepted image was preserved under its original tag. [Exact execution commands](../evidence/live-gemini/commands.md) distinguish live commands already executed from offline regression commands. They are an audit record, not authorization to run another paid trial.

## Security and data preservation

The credential file was verified nonempty, regular, non-symlink, mode `0600` and Git-ignored, without displaying it. It was read inside the authorized process and never placed in CLI arguments, tracked configuration or image build context. Private run directories and credential/config files remain ignored. The [security review](../evidence/live-gemini/security-review.json) found no exact available credential values or high-confidence key patterns in 296 tracked/unignored files, and no current Gemini key in 677 reachable historical Git blobs (post-commit check). This targeted check is not a complete audit of all historical secrets or publisher licensing. Public-review evidence contains only authored synthetic content; opaque thought signatures were excluded.

Read-only MCP tools and deterministic event/article/publisher/URL/excerpt checks remained active. [Before/after data checks](../evidence/live-gemini/data-preservation.json) show identical full normalized MCP event-detail responses for both authored events. This is not a physical database snapshot equality claim. The original application stacks and data were not modified by these workflows.

No production deployment, GCP resource creation, remote Git push, merge or force-push occurred. `main` remains `28edc62816d44254d7b5b532beaeec421762bb34`; `feature/gcp-deploy` remains `4e7b93135432d1885083822c764b8ac4c8d9feb7`.

## Remaining work and defensible achievements

A new, separately approved trial should rerun **A, B and C only**, with the corrected code, a fresh explicit call/cost allowance and the same private credential mechanism. Existing approval must not be reused for those workflows. Reconcile provider billing separately if an exact charge is required. Broader multilingual quality, real-news relevance, evolving-event analysis, adversarial robustness beyond this injection, production load and deployment remain unverified by this trial.

Accurate resume wording: “Implemented a bounded Google ADK analyst using an MCP server over a semantic-news REST API; demonstrated live Gemini conflict-preserving citations and deterministic rejection of corrupted citations on authored data, with 128 passing component tests and per-call budget/usage tracing.” Do not claim five live scenarios passed, a general hallucination-prevention guarantee, broad multilingual accuracy or production deployment.
