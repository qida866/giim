# Task 2 — A/B/C live Gemini retest approval package

**Status: approved and executed.** See the [retest report](TASK2_GEMINI_RETEST_REPORT.md). The three planned attempts are consumed; do not rerun these commands without further authorization. No additional Gemini calls were made during the preparation recorded below. Task 2 is not fully live-accepted. The first trial remains two passes and three failures; those records are preserved without reclassification.

## Failure review and regression coverage

| Original failure | Established cause / limit of evidence | Implemented fix | Regression evidence |
|---|---|---|---|
| A: normal research | ADK terminal `set_model_response` passed validated UUID objects to ordinary JSON encoding | UUID field serializers preserve internal validation and emit strings at the boundary | Actual SDK terminal tool tested for ResearchBundle and Draft; invalid UUID rejected; terminal Researcher response completes offline ADK/MCP workflow |
| B: cross-lingual | Pinned GenAI legacy Schema conversion rejects `exclusiveMinimum`; reproduced offline after the runtime error | Wire schema uses equivalent `minimum: 1` for a strict positive integer | All role schemas accepted by pinned SDK; zero, negative, boolean and string article IDs remain invalid |
| C: insufficient evidence | Writer returned HTTP 400; exact rejected server field was not retained and remains unknown | Writer/Verifier configuration uses native `response_json_schema` with JSON MIME type, clearing legacy `response_schema` | Both role configurations tested; Pydantic extra-field rejection retained; D/E already completed live with this configuration |

The runtime fixes are in `ee8e879`. Their source has not changed during this preparation. Local tests cannot prove that a future provider request will never return HTTP 400. The proposed round must show all three corrected live paths complete without that error. The original D/E successes are supporting compatibility evidence, not substitutes for A/B/C.

## Authorized scope being requested

Exactly the same three questions, once each:

1. **A:** What happened at the synthetic AI laboratory? Find the event and cite its reports.
2. **B:** 查找描述同一人工智能实验室开放事件的不同语言报道，并引用各个来源。
3. **C:** What will happen to the stock market exactly 100 years from now?

D and E are excluded by the runner's `retest-abc` profile. A separate approval phrase is mandatory; the previous five-workflow approval cannot unlock this profile. It has a new ledger and a new exclusive output directory, and cannot resume the original trial's ledger. Within-round continuation can only select unattempted A/B/C cases and must retain spending/call reservations.

The runner stops at the first failed/blocked case. Investigate and fix locally, then run regressions; do not automatically repeat a paid workflow or reset its budget. Any additional paid repeat beyond these three attempts needs a further explicit authorization. Unattempted cases may continue under this round's approval with the same cumulative ledger after investigation. No GCP deployment, production modifications, push or merge is included.

## Model, cost and credentials

- Model: **`gemini-3.5-flash-lite`**, ordinary Gemini Developer API generation.
- SDKs: Google ADK 2.14.0, Google GenAI 2.34.0, MCP 2.3.0, Pydantic 2.14.3, Python 3.11.15. No upgrades proposed.
- Maximum **30 model-call attempts total**, at most ten per workflow, retries disabled. At most one bounded Writer/Verifier revision per workflow.
- Maximum 2,048 output tokens per call; 80,000 conservative token reservations per workflow; 180-second workflow timeout and 20-second provider timeout.
- **Stop before the next call's reservation would reach $0.30 USD.** No next call is started when its projected cost would breach the limit. Missing usage retains the reservation and an unknown complete total.
- Conservative planning estimate: `3 × (80,000 × 0.30 + 10 × 2,048 × 2.50) / 1,000,000 + 30 × 1,000 × 0.30 / 1,000,000 = $0.2346`. Budget approximately **$0.24**, capped below **$0.30** by the runner. This intentionally overcounts output/input reservations and is not a provider-enforced billing cap. Prior observed costs suggest a few cents, but those incomplete runs are not a reliable charge forecast.

Google's [standard pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite) was rechecked: $0.30/M input and $2.50/M output including thinking. The [GenerateContent API](https://ai.google.dev/api/generate-content) exposes the native JSON Schema configuration. No paid search, Maps, caching, embeddings or cloud provisioning is enabled.

Existing credential file: `.runs/live-gemini/gemini_api_key` in this worktree. Verified regular, non-symlink, nonempty, `0600`, Git-ignored, with no contents displayed. It will be mounted read-only; the key value will not appear in command arguments or Docker environment configuration. Keep raw role responses/private logs under ignored `.runs`; export only reviewed authored evidence, excluding opaque thought signatures and any sensitive values.

## Exact proposed execution command — do not execute before approval

```sh
cd /Users/qida/Documents/Codex/2026-09-21/you-are-taking-over-my-existing/work/mcp-agent

GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=abc-only-max-30-model-calls-under-0.30-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --round retest-abc \
  --credential-file /run/secrets/gemini_api_key \
  --output /results/approved-abc-02 \
  > .runs/live-gemini/approved-abc-02-console.txt 2>&1
```

The Compose service mounts the current trial script and uses the previously tested pinned SDK image. The source mount explicitly loads the corrected agent code; the existing image's older installed agent must not be used without that mount. The runner's preflight checks the actual isolated API and exact authored dataset before any model call. Do not recreate/reseed original application data. If the fixture later ages out of its seven-day window, stop and review an isolated-fixture refresh before running; never weaken the dataset checks.

The original successful evidence remains in `docs/evidence/live-gemini/`, and original private runs remain under `.runs/live-gemini/approved-01*`. The retest output directory was confirmed absent. A [SHA-256 manifest](../evidence/live-gemini-retest-preparation/preserved-evidence.json) fingerprints all earlier reviewed evidence.

## Acceptance criteria and trace review

All three must show Coordinator, Researcher, Writer and Verifier role execution, returned real-model usage and deterministic verification events. A/B must additionally show actual `giim_search_events` and `giim_get_event` MCP calls, both model and deterministic approval, relevant event identity, and nonempty valid citations. Compare the complete event/article/publisher/URL association and exact permitted excerpt against this request's evidence ledger; no fabricated citations can pass. B must cite at least two retrieved languages, with all current evidence represented under existing gate rules.

C must return a deliberate insufficient-evidence response with no factual claims or citations, after Writer/Verifier/gate execution, not an execution-error fallback. Researcher may correctly refuse this impossible future prediction without a tool call; do not force irrelevant retrieval solely to inflate tool coverage. A/B and the no-model preflight verify the MCP path.

Record request IDs, role/function-call responses, MCP results, verification errors, revisions, model versions, latency, prompt/output/thinking tokens, estimates and unknown usage. Check for HTTP 400/other errors and partial response accounting. Preserve old failures and successful D/E traces, and produce an updated five-case acceptance matrix that references A/B/C from this round and D/E from the first round. Do not present these different executions as one fresh five-case run. Only after all five have passing real-model evidence can these five controlled acceptance scenarios be marked complete; broader quality and production readiness remain separate questions.

## Preparation verification

- Actual REST API/MCP preflight: all five tools passed; zero model calls. Both authored full event responses match the previous postflight.
- Component suite: **132 passed**, two existing dependency warnings; Ruff check/format and `pip check` passed with network disabled. See [component output](../evidence/live-gemini-retest-preparation/component-tests.txt) and [backend output](../evidence/live-gemini-retest-preparation/backend-tests.txt).
- Original backend suite: **130 passed, two paid-provider tests deselected, one existing warning**. Tests ran against the existing isolated test database, not the application database.
- Original API, backend tests, frontend and migrations have no diff from the previous delivery. No observed regression in the tested paths; this is not proof of all possible production behavior.
- Changes for this preparation are confined to the trial harness, its regression tests, expanded role-schema tests and this documentation/evidence. Existing runtime functionality and D/E evidence remain untouched.

Commands actually executed without additional Gemini calls:

```sh
# From the worktree; no key mount or live flags:
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --preflight --round retest-abc \
  --output /results/retest-preparation/preflight

# Network-disabled component tests:
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-live-verified:local \
  -c 'ruff format scripts/live_gemini_trial.py apps/agent/tests/test_live_trial.py apps/agent/tests/test_structured_tool.py && ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'

# From the private sibling work/mcp-validation directory:
docker compose -p giim-mcp-test -f compose.yml --env-file .env run --rm -T \
  -e GOOGLE_API_KEY= -e DEEPSEEK_API_KEY= \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  api python -m pytest -q -p no:cacheprovider \
  -k 'not test_chat_basic and not test_chat_with_system_message'
```
