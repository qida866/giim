# Task 2 — approved A/B/C real Gemini retest

**Decision: Task 2 is not yet fully live-accepted or ready for a reliable five-scenario demonstration.** This round produced **one PASS (C), one FAIL (B), and one BLOCKED (A)**. Together with the preserved D/E successes, **three of the original five scenarios have passing real-model evidence**. A and B still require successful live verification.

Executed November 10, 2026 Pacific time; trace timestamps are November 11 UTC. Branch: `feature/mcp-agent`. A/B started from `b153bd9f508ed1a3cacc0a951057c3f0fa5c80dd`. The targeted instruction/schema-description fix applied before C is committed as `179b04ef6483b71ed71b19b4970bbfdf3ebf3d6e`. No deployment, push or merge occurred.

## Retest results

| Case | Result | Actual execution | Remaining issue |
|---|---|---|---|
| A: normal research | **BLOCKED** | Real Researcher searched through MCP and retrieved the correct event; Writer produced three attributed excerpts; Verifier call returned HTTP 503 | No completed Verifier response or deterministic validation; normal research remains unverified end to end |
| B: cross-lingual research | **FAIL** | Chinese query retrieved English/Chinese/Spanish evidence; all roles ran; both Writer drafts had correct quotes/citations but `acknowledge_uncertainty=false`; real Verifier approved both; deterministic gate rejected both | Targeted prompt/schema clarification passes local regression, but has not been live-verified on A/B |
| C: insufficient evidence | **PASS** | Researcher identified the unsupported future prediction; Writer returned empty claims; Verifier ran; deterministic gate required evidence and produced a deliberate final refusal | No factual answer expected; no HTTP 400 or execution error occurred |

Each scenario was attempted once, following the approved procedure. Execution stopped after A and B, followed by investigation; continuation selected only previously unattempted cases and carried all reservations/call counts forward. No extra paid replay was performed. The 30-call budget had headroom, but the approved procedure specified one attempt for each of A/B/C, so unused calls were not treated as authorization for additional workflow attempts.

## Actual failures, fixes and limitations

### A: provider HTTP 503, not the old serialization failure

Request `dc7de602-2ea8-4fc6-8693-4c0524111774` completed Researcher tool calls and its structured terminal response. The original UUID problem did not recur. Writer produced JSON containing all three exact multilingual excerpts with the valid event UUID, article IDs 101/102/103 and their source URLs.

The next model call, for Verifier, raised `ServerError` with HTTP status **503**. Safe diagnostics retained exception type/status and fixed schema/format indicators, excluding the raw provider message. This establishes a provider/server error, not its precise upstream cause or whether it would recur. There was no evidence of HTTP 400 in this round.

The trial deliberately disables provider retries. No local source change can be claimed to fix the upstream 503. The existing failure path returned no claims; its missing usage remained unknown and fully reserved. A's Writer draft also had the false uncertainty flag later seen in B, but A never reached the gate, so do not infer that A would otherwise have passed.

### B: correct retrieved citations, incomplete uncertainty compliance

Request `e4dc8e33-9e85-4574-b311-b9626e0dc40b` completed seven real model calls and two real MCP calls. The Researcher used the Chinese search query `人工智能实验室 开放`, retrieved the correct event, and identified the English, Chinese and Spanish reports. The draft quotes were:

- `The synthetic AI laboratory opened on Tuesday with 24 research desks.`
- `合成示例：人工智能实验室于周二开放，设有24个研究席位。`
- `El laboratorio sintético de inteligencia artificial abrió el martes con 24 puestos.`

Each matched its exact evidence-ledger excerpt and article/publisher/URL association. These are authored test sources, not restricted publisher content or independently fetched source webpages.

Writer explicitly set `acknowledge_uncertainty=false` in its first draft and again after receiving `missing_uncertainty` for repair. Both real Verifier outputs approved the draft. The deterministic gate rejected both iterations with **`missing_uncertainty`**, as intended. The final response had zero claims. Thus multilingual retrieval and draft citation matching worked, but a valid final grounded answer did not; B remains FAIL.

The original instructions said to acknowledge uncertainty with multiple sources, but did not explicitly distinguish this field from contradiction detection. Agreeing translations triggered an instruction-compliance gap. The model's internal reason is unknown; the observable defect is the false flag and Verifier approval despite the deterministic rule.

Targeted changes:

- `apps/agent/src/giim_agent/roles.py`: Writer must set the flag true for multiple sources **even when all reports agree or are translations**; `missing_uncertainty` must be repaired without altering quotes/citations. Verifier must reject a false flag under the same condition.
- `apps/agent/src/giim_agent/schemas.py`: the field's JSON Schema description now states the same rule. The field type/default and validation gate are unchanged.
- `apps/agent/tests/test_structured_tool.py`: new replay regression reproduces a false flag plus an approving model verdict, verifies that the deterministic gate supplies the repair error, and verifies publication only after the corrected draft passes. Existing repeated-omission tests still require refusal.

The implementation does not silently flip a model's output flag, relax citation checks, remove tests or label the refusal successful. The clarification is **implemented and locally tested**, not a verified live fix for A/B. The later C run tested the updated code only on the no-evidence path.

### C: successful refusal through all roles and the gate

Request `362a986f-664c-49b3-bd56-adb269fe9696` completed five model calls with usage. Researcher returned `insufficient=true` for the exact 100-year stock-market prediction. Writer supplied empty claims. Verifier approved the empty draft as containing no unsupported claims. The deterministic gate rejected factual publication with `missing_evidence`; after the bounded revision, the application returned:

> The available GIIM evidence is insufficient to provide a verified answer. No unsupported claims or citations are returned.

This is `status=insufficient_evidence`, not `status=error`. It is the expected safe outcome. `verified=false` and deterministic rejection are appropriate for a request that cannot support a factual answer. No MCP search was necessary for this impossible prediction; A/B and the read-only preflight exercised the actual MCP/backend path. The extra empty-draft revision is a bounded inefficiency, not a correctness failure; it was not refactored during this trial.

## Actual workflow and evidence

All calls used **Gemini Developer API `gemini-3.5-flash-lite`**, Google ADK 2.14.0, GenAI 2.34.0, MCP 2.3.0 and Pydantic 2.14.3. Coordinator is the ADK orchestration node; Researcher, internal Writer and Verifier are model agents. The official MCP client/server called the actual GIIM REST API backed by isolated PostgreSQL, cached CPU bge-m3 and Qdrant. No fake model was used for these live results.

[Actual trace events](../evidence/live-gemini-retest/traces.jsonl), [model role responses](../evidence/live-gemini-retest/role-responses.json), [answers and evidence](../evidence/live-gemini-retest/results.json), [per-case metrics](../evidence/live-gemini-retest/metrics.json) and [derived summary](../evidence/live-gemini-retest/trace-summary.json) are retained. There are **64 events**: three requests, 16 role events, 17 model starts, 16 returned usage events, four MCP calls, four gate-verification events, one failure and three completion events. Thought signatures and thought parts are excluded from exported responses. [Executed commands](../evidence/live-gemini-retest/commands.md) include both continuations and the offline regression run.

A has no verification event because its Verifier response failed. B has two `model_ok=true / deterministic_ok=false` events with `missing_uncertainty`. C has two such events with `missing_evidence`; the expected outcome is refusal. A raw final-answer citation check on empty claims passes vacuously and must not be interpreted as successful grounded-answer delivery.

## Usage and cost

| Case | Attempts / responses with usage | Reported input | Reported output | Reported total | Latency | Known cost estimate |
|---|---:|---:|---:|---:|---:|---:|
| A | 5 / 4 | 6,239 | 552 | 6,791 | 17.215 s | $0.0032517, incomplete |
| B | 7 / 7 | 11,886 | 948 | 12,834 | 15.012 s | $0.0059358 |
| C | 5 / 5 | 1,777 | 129 | 1,906 | 11.277 s | $0.0008556 |
| **Round total** | **17 / 16** | **19,902** | **1,629** | **21,531** | Per-request values above | **$0.0100431 known subtotal** |

Reported thinking tokens: zero. One model attempt has no returned usage; complete estimated cost remains **null/unknown**, not $0.0100431. The full cumulative reservation is **$0.1169647**, below the $0.30 ceiling. The round used 17 of 30 authorized model attempts; no reservation or call counter was reset during continuation. The first trial's spending is separate and unchanged.

Estimates use the approved [Google standard rates](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite): $0.30/M input and $2.50/M output including thinking. These are not reconciled provider charges or provider-enforced account limits. No paid search, cloud resources, hosted embeddings or extra services were used.

## Regression and preservation checks

- Before the targeted fix: **132 component tests passed**; after it: **133 passed**, with the same two dependency deprecation warnings. Ruff check/format and `pip check` passed. Both runs disabled networking. [Before](../evidence/live-gemini-retest/before-fix-tests.txt), [after](../evidence/live-gemini-retest/after-fix-tests.txt).
- The immediately preceding preparation reran **130 original backend tests**, with two paid-provider tests excluded. API, backend tests, migrations and frontend remain unchanged. This backend result was not rerun or relabeled as a post-fix run; the change was limited to agent instructions/schema metadata and a regression.
- All earlier D/E and first-round evidence hashes match the preparation manifest. Both authored event-detail responses match the preflight after the retest. [Preservation checks](../evidence/live-gemini-retest/preservation.json). This is normalized API-response equality, not a physical database snapshot assertion.
- Private credentials remained in the existing regular `0600`, ignored file mounted read-only. The key was not printed or passed as a command argument/value in Docker configuration. Exported evidence contains only authored data and fixed diagnostics. See [security review](../evidence/live-gemini-retest/security-review.json) for scan scope.
- `main` and `feature/gcp-deploy` refs are unchanged. No production data modifications, GCP deployment, GitHub push or branch merge occurred.

## Five-scenario acceptance matrix and next step

| Original scenario | Latest status | Evidence source |
|---|---|---|
| A: normal grounded research | **BLOCKED / not accepted** | This round: provider 503; final answer unverified |
| B: cross-lingual grounded answer | **FAIL / not accepted** | This round: missing uncertainty; targeted clarification requires live verification |
| C: insufficient evidence | **PASS** | This round: real-model refusal, all roles and gate exercised |
| D: conflicting reports | **PASS, preserved** | First round: valid attributed excerpts and uncertainty |
| E: unsupported citations | **PASS, preserved** | First round: deliberate corrupted draft rejected by model and deterministic checks |

This is cumulative evidence from different runs/code states, not a single five-case pass. D/E were not rerun after the instruction clarification; their successful records remain valid historical evidence, not proof of every later change. The project still needs **a separately authorized A/B live verification** of the clarified configuration. If an upstream 503 repeats, report it as blocked and retain its reservation; adding production retry/backoff behavior should be a deliberate, separately tested reliability change rather than silently increasing paid attempts.

Even after five passing scenarios, the demonstration remains limited to two authored events and five source reports. It does not establish general news relevance, multilingual recall, independent truth, publisher licensing beyond these fixtures, production uptime or load capacity. No five-of-five success or production readiness claim is supported yet.
