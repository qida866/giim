# Task 2 — final controlled live Gemini acceptance

**Decision: all five original workflows now have passing real-Gemini evidence across the preserved test rounds.** The final authorized round ran only A and B, and both passed without repairs. This completes the requested five-scenario demonstration acceptance. It is not a claim of production readiness, a statistical reliability benchmark, or five fresh passes on one code revision.

Executed November 11, 2026, 20:18:45–20:19:22 UTC. Branch: `feature/mcp-agent`. Clean checkout at execution: **`cc080291c502ac31a7f7800e43358f9f96231e81`**, containing reliability implementation **`83cd939ab49daebd3b1f0709b576e7fd0e0656ae`**. This follow-up changes documentation/evidence only; no implementation fix was necessary. No deployment, push, merge or production-resource modification occurred.

## Results and budget

| Workflow | Result | Model attempts / limit | MCP calls | Input tokens | Output tokens | Total tokens | Estimated USD | Workflow latency |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A — normal research | **PASS** | 5 / 10 | 2 | 7,864 | 579 | 8,443 | $0.0038067 | 19.666 s |
| B — cross-lingual retrieval | **PASS** | 5 / 10 | 2 | 8,636 | 581 | 9,217 | $0.0040433 | 16.970 s |
| This round | **2/2 PASS** | **10 / 20** | **4** | **16,500** | **1,160** | **17,660** | **$0.0078500 / $0.20** | 36.637 s summed |

All ten attempts returned usage. Reported thinking tokens were zero. Conservative pre-call monetary reservations totaled **$0.072953**, also below the ceiling. The meter reserved before every provider invocation, including any retry, and would refuse a reservation reaching/exceeding $0.20 or attempt 21. The configured 180-second request deadline, ten-attempt per-workflow limit, two retries per logical invocation and one draft repair remained active. Neither retry nor repair was needed. No further paid requests were made after B completed.

Model: **`gemini-3.5-flash-lite`**, with that same version identifier returned in every response. The estimate uses standard text input **$0.30/M** and output including thinking **$2.50/M**, reconfirmed against [Google's pricing page](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite) on November 11. Calculation: `(16,500 × 0.30 + 1,160 × 2.50) / 1,000,000 = $0.00785`. This is a usage-based estimate, not an invoice or provider-enforced account cap. Historical unknown-usage charges remain unknown; this new round does not resolve them.

The [results](../evidence/live-gemini-final-ab/results.json), [per-role metrics](../evidence/live-gemini-final-ab/metrics.json), [38 trace events](../evidence/live-gemini-final-ab/traces.jsonl) and [actual role responses](../evidence/live-gemini-final-ab/role-responses.json) are retained separately from all previous evidence. Hidden thought parts/signatures are excluded; observable function calls, structured outputs, final answers and usage are retained.

## Actual agent and tool execution

The real Google ADK workflow used a custom deterministic Coordinator, Gemini Researcher, internal Gemini Writer and Gemini Verifier. The Coordinator is an ADK orchestration node, not another Gemini model call. Researcher FunctionTools communicate through the official MCP client and subprocess server to GIIM's actual FastAPI REST API. The dedicated local trial stack uses PostgreSQL, Qdrant and cached CPU **bge-m3**. It contains two authored synthetic events and five authored reports, not restricted publisher content.

Both requests followed this observed sequence:

1. Coordinator started Researcher; Gemini selected `giim_search_events` through MCP.
2. Gemini selected `giim_get_event` for the retrieved AI-laboratory UUID through MCP.
3. Researcher returned structured event IDs, evidence sufficiency and contradiction flags.
4. Coordinator invoked Writer, which returned three exact attributed excerpts and explicit `acknowledge_uncertainty: true` in its native JSON structured output.
5. Gemini Verifier returned `ok: true`, empty unsupported claims and empty missing citations.
6. Coordinator's unchanged deterministic validator independently approved the evidence associations and uncertainty, then rendered the verified extractive answer. Revision count was zero.

### A — normal research

Question: “What happened at the synthetic AI laboratory? Find the event and cite its reports.” Request ID: **`3a9e902b-88ad-4bfe-a59f-c557369a352a`**.

Actual search query: `synthetic AI laboratory`, seven-day window, limit five. Both MCP calls succeeded. The answer cited all three current EN/ZH/ES reports about Tuesday's opening and 24 research desks. Every event ID, article ID, publisher, URL and complete permitted excerpt matched the request's evidence ledger. Both verification approvals were true with no errors.

### B — cross-lingual retrieval

Question: “查找描述同一人工智能实验室开放事件的不同语言报道，并引用各个来源。” Request ID: **`70956173-ff13-4db8-ae2c-8e94130e7cbe`**.

Actual search query: `人工智能 实验室 开放`, seven-day window, limit five. The same event was retrieved through GIIM semantic search. Researcher explicitly identified English, Chinese and Spanish reports. Writer preserved all three original-language excerpts and explicitly set the uncertainty flag true; Verifier and the deterministic gate both approved. The output is multilingual evidence, not a generated Chinese translation of the complete answer.

Both answers used event **`00000000-0000-0000-0000-000000000001`** with these exact associations:

| Article | Publisher | Source URL | Language |
|---|---|---|---|
| 101 | Authored Demo en | `https://demo.example.org/1/1` | English |
| 102 | Authored Demo zh | `https://demo.example.org/1/2` | Chinese |
| 103 | Authored Demo es | `https://demo.example.org/1/3` | Spanish |

These are authored fixture URLs, not live publisher pages. Validation establishes exact membership in retrieved API evidence, not independent website truth or URL availability. Final answers include the explicit caveat that reports may disagree and do not establish independent confirmation or certainty. No output flags were silently repaired in Python, and no citation or evidence requirement was weakened.

## Verification of the two fixes

**Uncertainty and structured output: live PASS for both requests.** The prior B failure returned a false uncertainty flag twice; this round's actual Writer payloads explicitly returned true on their first draft. The required strict boolean contract, application-provided validation requirements and Writer/Verifier instructions were active. All native JSON responses were accepted by Gemini; no HTTP 400 occurred in this round. This validates the tested model/schema combination, not every possible future schema or model version.

**Transient retry recovery: implemented and locally PASS; not exercised by real Gemini in this round.** No 503, other provider error, retry or recovery event occurred. A now passes Verifier execution, but that is not evidence of live 503 recovery. The regression suite again passed temporary 503 recovery, exhaustion, jitter, shared call/token/dollar caps, permanent-error rejection, cancellation and partial-response handling. Its pinned real-SDK 503→200 test uses a local HTTP stub with external networking disabled. No extra paid calls were made to induce an error.

## Cumulative five-workflow acceptance

| Original workflow | Latest passing evidence | Result | Scope |
|---|---|---|---|
| A — normal research | This final A/B round | **PASS** | Three grounded source citations, explicit uncertainty, both gates approve |
| B — cross-lingual retrieval | This final A/B round | **PASS** | Chinese query retrieves EN/ZH/ES evidence; all sources retained |
| C — insufficient evidence | [A/B/C retest](TASK2_GEMINI_RETEST_REPORT.md), request `362a986f-664c-49b3-bd56-adb269fe9696` | **PASS, preserved** | Impossible forecast refused with no claims; all roles ran, no MCP retrieval; gate rejected missing evidence |
| D — conflicting evidence | [Initial live round](TASK2_LIVE_GEMINI_REPORT.md), request `502793b8-389f-4c06-b637-6718fca5bda5` | **PASS, preserved** | Disagreeing 12/18-person reports retained and attributed with uncertainty |
| E — unsupported citation rejection | [Initial live round](TASK2_LIVE_GEMINI_REPORT.md), request `311da00e-e671-42b5-b0fc-73d9923b81b8` | **PASS, preserved** | Harness corrupted real Writer citations; real Verifier and deterministic gate rejected them, final claims empty |

C/D/E were not rerun or charged in this round. Their passing evidence comes from earlier code revisions. E is deliberate fault injection, not proof of a spontaneous model hallucination; C is a successful safe refusal, not a verified factual answer. Historical failed A/B/C attempts remain recorded as failures/blocks. Five-of-five means each original scenario has a passing real-model observation across these rounds, not 100% reliability over all attempts or broad real-news accuracy.

## Regression and preservation checks

- **175 agent/MCP tests passed**, three dependency deprecation warnings, 33.86 seconds. Ruff check, format check (49 files) and `pip check` passed. External networking was disabled and no live-model credential environment was configured. The workspace bind mount includes ignored local files; the tests did not load the private key for model use. [Output](../evidence/live-gemini-final-ab/regressions.txt).
- **130 original backend tests passed**, two existing paid-provider tests deselected, one existing structlog warning, 3.98 seconds. They used the separate isolated regression database and cached bge-m3. No tests were deleted, weakened or relabeled. [Output](../evidence/live-gemini-final-ab/backend-tests.txt).
- Actual API/MCP preflight and postflight passed all five capabilities with zero additional model calls: recent events, semantic search, event detail, coverage and readiness. Complete normalized details for both authored events were identical before/after. This is an API-data comparison, not a physical database snapshot. [Preflight](../evidence/live-gemini-final-ab/preflight.json), [postflight](../evidence/live-gemini-final-ab/postflight.json).
- Previous live evidence and local reliability evidence remain byte-for-byte intact, checked by SHA-256. Main remains `28edc62816d44254d7b5b532beaeec421762bb34`; Task 1 remains `4e7b93135432d1885083822c764b8ac4c8d9feb7`. [Preservation manifest](../evidence/live-gemini-final-ab/preservation.json).
- Private key remains regular, non-symlink, nonempty, mode `0600` and Git-ignored. Candidate tracked/unignored files were checked for the available actual key/private fixture password and high-confidence secret patterns without printing values. No matches were found. This is a scoped worktree scan, not a new full historical security audit. [Security review](../evidence/live-gemini-final-ab/security-review.json).

SDKs observed at execution: Google ADK **2.14.0**, Google GenAI **2.34.0**, MCP **2.3.0**, Pydantic **2.14.3**. The pinned local dependency image was reused, with current agent sources mounted read-only. The exact [executed commands](../evidence/live-gemini-final-ab/commands.md) include the live approval interlock, source mount, no-model postflight and regressions. The prior **24/24 scripted evaluation** remains documented in the [reliability report](TASK2_AB_RELIABILITY_REPORT.md); it was not rerun or presented as a Gemini benchmark here.

## Remaining limits and reproducibility

The two-event synthetic corpus establishes real integration and controlled behavior, not broad bge-m3 recall, publisher permissions, source truth, general multilingual quality, adversarial robustness, production availability or measured uptime. Output remains strictly extractive. Optional developer Web UI, human ratings, production authentication/TLS deployment and load testing remain outside this verification. Dependency deprecation warnings remain non-fatal. Older attempts missing usage still require separate billing reconciliation.

A future live demonstration must use fresh explicit paid-call authorization, a new exclusive output directory and an up-to-date authorized fixture window. Do not blindly rerun the completed command, reset its ledger, overwrite evidence, or delete/reseed existing data to refresh timestamps. Model aliases and pricing can change; recheck them before a new round. The retained artifacts support a no-charge walkthrough now.

Resume-safe statement: **“Built and tested a Google ADK/MCP analyst over GIIM's real semantic-search API, with deterministic source validation and budget-aware retries; all five controlled live-Gemini scenarios achieved passing evidence across staged runs. Final targeted verification used 10 model calls, with 175 component and 130 backend regressions passing.”** Do not replace “controlled scenarios” with a general accuracy, production-scale or zero-hallucination claim.
