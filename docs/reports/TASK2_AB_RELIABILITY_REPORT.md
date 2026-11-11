# Task 2 — A/B reliability fixes and proposed live verification

**Status: local implementation complete; new live A/B verification awaits explicit approval. No new Gemini API calls were made.** Historical live acceptance remains three of five scenarios passing: C/D/E passed, A was blocked by HTTP 503, and B failed the uncertainty gate. Those records are preserved. These changes do not establish a new real-model pass or production readiness.

Date: November 11, 2026 (America/Los_Angeles). Branch: `feature/mcp-agent`. Tested implementation commit: `83cd939ab49daebd3b1f0709b576e7fd0e0656ae`. The existing GIIM architecture, bge-m3, ingestion, clustering, search, databases and frontend are preserved.

## A — transient provider failures with explicit budgets

The recorded A failure was a Verifier `ServerError`, HTTP 503. Its exact upstream cause cannot be determined from the retained safe diagnostics. The controlled trial had SDK retries disabled; the ordinary model factory previously allowed SDK-managed retries that GIIM could not account for individually. Increasing that hidden retry count would risk understating model attempts and spending.

The new `RetryingModel` wraps each role inside the existing request-scoped runtime. It owns retries explicitly; SDK retries are set to one attempt at both client and request levels. Every extra attempt consumes the same workflow call/token budget, and the trial's inner meter reserves money and counts the attempt before the underlying SDK is invoked. No retry resets a ledger, starts a new workflow, or repeats a tool operation itself.

Retry policy:

- Retry HTTP **408, 429, 500, 502, 503 and 504**, recognized HTTPX/HTTPX2/aiohttp connection failures and provider timeouts.
- At most **two retries** per logical model invocation, hence at most three attempts, subject to the stricter shared workflow limits. `Limits.provider_retries` accepts only integers 0–2.
- Equal-jitter exponential backoff: first delay **0.25–0.5 seconds**, second **0.5–1 second**; the delay function has a four-second cap. No unbounded loop or automatic whole-workflow replay.
- Do not retry authentication/request/schema/validation/security errors, other non-allowlisted responses, cancellation, or failures after a partial response has been yielded.
- The existing wall-clock workflow deadline covers all attempts and sleeps. Call/token exhaustion prevents further attempts; the trial's monetary limit prevents another provider call. An exhausted request returns no claims.
- Preserve failed-attempt reservations. A successful retry does not supply the failed attempt's usage; full totals stay unknown when a record is missing.

This follows Google's [retry guidance](https://ai.google.dev/gemini-api/docs/troubleshooting). The pinned SDK implementation was inspected and exercised against a **local HTTP server** returning 503 then 200, with container networking disabled. Exactly two HTTP requests occurred, one visible retry was recorded, and structured JSON Schema survived SDK serialization. This is a real SDK integration test with a local stub, not a real Gemini call.

## B — explicit uncertainty without weakening evidence validation

The live failure showed Writer returning exact English/Chinese/Spanish excerpts with valid citations, but an explicit false uncertainty flag twice. Verifier approved both; the deterministic gate correctly refused publication. Merely trusting the model's approval or flipping the output flag in Python would conceal the problem.

Changes:

- The model-facing **`DraftOutput` requires an explicit strict boolean** `acknowledge_uncertainty`. Omission cannot silently become a default true value, and strings such as `"true"` are invalid. The internal `Draft` default remains available for existing internal construction; generated drafts are validated with `DraftOutput`.
- Writer and Verifier receive application-generated `validation_requirements` alongside, but separate from, the untrusted question/evidence fields. Multiple current sources require true even when they agree or are translations. All current evidence must be retained; citations and complete permitted excerpts must match the ledger.
- The Writer's native JSON Schema marks the field required and explicitly describes the request's true-value requirement when applicable. The implementation uses a documented boolean plus descriptions, **not an undocumented boolean enum/const** that might introduce another HTTP 400. Google's [structured-output guide](https://ai.google.dev/gemini-api/docs/structured-output) documents enums for strings/numbers; the boolean value rule is enforced locally.
- Instructions require separate attribution of disagreeing reports, prohibit filling evidence gaps and explain correction of `missing_uncertainty`. Verifier independently checks those requirements, including incomplete evidence and unsupported certainty.
- Coordinator rejects invalid generated drafts and traces that failure. It never silently supplies or changes the model's flag. Missing/false flags, omitted sources, unknown citations, unsupported excerpts and incomplete evidence still cannot produce a verified final answer.

**The deterministic ledger and citation validation implementation is unchanged.** Local tests cover false/missing flags, correction after a gate rejection, agreeing multilingual sources, conflicting sources, malicious instructions, unknown associations and unsupported claims. They cannot guarantee that Gemini will comply with the improved prompt on a future run; live A/B acceptance remains required.

## Observability and accounting

New JSONL events: `provider_error`, `provider_retry_scheduled`, `provider_retry`, `provider_recovered`, `provider_retry_stopped` and `provider_cancelled` where applicable. Events record role, bounded attempt number, HTTP status/type, retryability, delay and error latency; raw provider messages, headers and bodies are not copied. Existing role, MCP, verification and final completion events remain available. Invalid structured drafts now also emit a verification-failure event.

Completion summaries include provider-error count, retry-attempt count, recovery count and total model attempts. Returned-response tokens remain separate from attempts. If any attempted generation lacks usage, complete token/cost totals remain null. Final model latency includes retry/backoff elapsed time; failed-attempt latency is separately recorded. A budget-blocked local attempt can appear in runtime attempt traces without reaching the provider; the trial's pre-provider meter is authoritative for its spending/call reservations.

The trial acceptance check now permits a recovered transient error with explicitly accounted-for unknown usage, while still requiring real returned usage from each model role, verified final citations, relevant evidence and both verification approvals. It does not count missing usage as zero or treat an error fallback as success. Regression coverage removes the error accounting event and confirms that such missing usage cannot be accepted silently.

## Local verification

- Complete agent/MCP source suite: **175 passed**, three dependency warnings; see [final regression output](../evidence/ab-reliability/final-regressions.txt).
- Installed-package suite: **174 passed**, three dependency warnings, with network disabled and no source mount. Both local packages were rebuilt into `giim-agent-task2-ab-ready:local` over the existing pinned dependency image. The source suite has one additional end-to-end meter/accounting test added afterward; runtime code is the same.
- Original GIIM backend suite: **130 passed**, two existing paid-provider tests excluded, one existing warning. It used the isolated test database and cached bge-m3, not the application database. No tests were deleted, skipped or weakened to conceal failures. The existing SDK retry assertion changed from two to one because the explicit wrapper now owns retries; new tests assert the overall retry limits.
- Ruff check/format and `pip check` passed. [Source output](../evidence/ab-reliability/final-regressions.txt), [installed output](../evidence/ab-reliability/installed-tests.txt), [backend output](../evidence/ab-reliability/backend-tests.txt).
- **24/24 deterministic evaluation cases passed** with scripted models and network disabled. This is not a Gemini quality benchmark. [Evaluation](../evidence/ab-reliability/evaluation.json).
- Actual isolated REST API/MCP preflight passed all five tools with **zero model calls**. The exact two-event authored dataset was checked. [Preflight](../evidence/ab-reliability/preflight.json).

New regression scenarios include 503 recovery and exhaustion; all allowed status codes; non-retryable client/schema/security failures; transport timeouts across SDK transports; cancellation/deadline during backoff; no replay after partial response; jitter bounds; shared call/token/dollar limits; missing usage after recovery; actual SDK HTTP behavior; full ADK/MCP recovery with strict rejection of unsupported/omitted/conflicting claims; explicit strict uncertainty and no silent default; and fresh approval for the A/B-only profile.

The model SDK pins remain ADK **2.14.0**, GenAI **2.34.0**, MCP **2.3.0** and Pydantic **2.14.3**, on Python 3.11.15. No package upgrade is part of this fix. [Executed local commands](../evidence/ab-reliability/commands.md) are recorded separately from the proposed live command.

## Changed files

- `apps/agent/src/giim_agent/retry.py`: explicit bounded provider retry wrapper.
- `budget.py`, `runtime.py`, `roles.py`: shared retry accounting, runtime integration, SDK retry suppression and instructions.
- `schemas.py`, `hooks.py`, `coordinator.py`: explicit model-output contract, request policy and invalid-draft tracing.
- `trace.py`: retry/error/recovery summary metrics.
- `apps/agent/tests/test_provider_retry.py`, `test_structured_tool.py`, `test_live_trial.py`, `test_observability.py`: regression coverage and updated SDK ownership assertion.
- `scripts/live_gemini_trial.py`: A/B-only profile, fresh approval phrase and explicit usage-accounting acceptance.
- This report and reviewed local evidence. Original API/backend tests, ledger, migrations and frontend are unchanged.

## Proposed live A/B round — approval required

Only **A: normal grounded research** and **B: cross-lingual retrieval**, one workflow attempt each. C/D/E will not run. The new round requires a fresh interlock; previous approvals cannot authorize it.

| Control | Proposed limit |
|---|---|
| Model | `gemini-3.5-flash-lite`, Gemini Developer API |
| Total model attempts | **20 maximum, including every provider retry** |
| Per workflow | 10 model attempts including retries; one Writer/Verifier repair |
| Per logical model invocation | Initial attempt plus at most two transient retries |
| Output | 2,048 tokens per attempt |
| Workflow timeout | 180 seconds including retries and delays |
| Context budget | 80,000 conservative token reservations per workflow |
| Estimated spending ceiling | **$0.20 USD**; refuse a call whose reservation would reach/exceed it |
| Planning estimate | **$0.1564**, approximately $0.16, with conservative margins |

Planning calculation, with retries already included in the 20-call total:

`2 × (80,000 × $0.30 + 10 × 2,048 × $2.50) / 1,000,000 + 20 × 1,000 × $0.30 / 1,000,000 = $0.1564`.

Prices are the reviewed [standard rates](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite): $0.30/M input and $2.50/M output including thinking. This is an application-side estimate/reservation limit, not a reconciled bill or provider-enforced account cap. Missing usage retains its full reservation and an unknown final charge.

**Stopping conditions:** stop before any call exceeds call/token/cost limits, on workflow timeout, on exhausted/non-retryable provider error, on failed scenario acceptance, or on a critical security issue. No automatic whole-workflow replay. B may continue after investigation only if it remains unattempted and all earlier reservations are carried forward. Any additional workflow attempt needs explicit authorization. Preserve all old evidence and write this round to a new exclusive directory.

Exact proposed command, **not executed**:

```sh
cd /Users/qida/Documents/Codex/2026-09-21/you-are-taking-over-my-existing/work/mcp-agent

GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=ab-only-max-20-model-calls-under-0.20-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --round retest-ab \
  --credential-file /run/secrets/gemini_api_key \
  --output /results/approved-ab-03 \
  > .runs/live-gemini/approved-ab-03-console.txt 2>&1
```

The existing Compose service uses the pinned SDK image and explicitly mounts the corrected agent source and trial script. The private credential stays read-only mounted; only its path appears in the command. The key was verified nonempty, regular, non-symlink, `0600` and Git-ignored without displaying it. The output directory was confirmed unused. No Google API call, credential validation against Google, cloud resource creation, deployment, push or merge was performed in this local work.

After approval: verify branch/clean state and budget configuration; run the command; inspect role responses, MCP calls, structured outputs and verification events; reconcile returned usage with all attempts and reservations; check source associations and uncertainty; perform no-model postflight and regression checks after any fix; update acceptance with actual PASS/FAIL/BLOCKED results. A temporary 503 that recovers can pass the workflow while its complete charge remains unknown. A refusal for A/B is a failure of their answer-delivery criteria, even when the safety gate worked.

## Preservation and remaining limitations

[Hash manifest](../evidence/ab-reliability/preservation.json) records unchanged prior live evidence. [Security review](../evidence/ab-reliability/security-review.json) states the exact scan scope. No credential values or restricted publisher content are included in reviewed artifacts. Original data and Git history remain intact; no branch merges or remote operations occurred.

The local HTTP tests prove SDK retry control and serialization against a stub, not Gemini availability or semantic compliance. Prompt/schema improvements still need live A/B proof; unknown provider charges require separate billing reconciliation. The full dependency stack was reused from a pinned local image rather than downloaded afresh. No claim of production uptime, broad multilingual recall, general hallucination elimination or five-of-five live acceptance is made.
