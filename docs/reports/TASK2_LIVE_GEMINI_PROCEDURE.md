# Controlled live Gemini integration trial

> Follow-up: the approved trial is complete. See the [live integration report](TASK2_LIVE_GEMINI_REPORT.md): two scenarios passed and three failed. All five workflow slots were used; the commands below must not be rerun without a new approval.

Prepared November 10, 2026 on `feature/mcp-agent`, following acceptance commit `0342649161c4e07cedab4510dcccca197de9055e`.

**Awaiting explicit approval. LIVE GEMINI TEST: NOT VERIFIED. No billable calls were made during preparation.**

The proposed authorization is **at most five end-to-end analyst requests**, with **at most ten Gemini generation calls per request (50 total)** and a **$1 USD estimated API budget**. Five multi-agent workflows are not five individual provider HTTP calls. If the intended limit is five individual provider calls total, do not approve this procedure: that is insufficient to complete five Researcher/Writer/Verifier workflows, and the scope must be reduced. No automatic paid reruns or extra credential-test inference requests are included.

## Verified local connections and runtime

The existing system executes the real Google ADK Runner and custom Coordinator, Researcher `LlmAgent`, internal Writer `LlmAgent`, independent Verifier `LlmAgent`, official MCP client/subprocess server, and REST adapter. Only the Researcher has read-only tools. The live factory supplies the real ADK Gemini adapter for all three LLM roles. The Coordinator orchestrates their work in code; it does not have a fourth paid model.

The isolated `giim-gemini-trial` Compose project now runs the actual GIIM FastAPI implementation with its own PostgreSQL and Qdrant volumes. All migrations ran. Cached CPU bge-m3 generated five vectors locally. The original application and previous acceptance stacks were not reseeded or reconfigured. No host API/database ports are exposed by this new project. The analyst uses the isolated API container's network namespace and `http://127.0.0.1:8000` **inside that namespace**.

A no-model preflight started the real MCP server over stdio, discovered and invoked all five tools, performed actual multilingual semantic search, and checked the returned evidence against exact authored fixtures. It passed. The probe checks both expected event identities and every source's article ID, publisher, URL, language and excerpt. Unexpected records or missing data block a live run. The live run repeats preflight before constructing any Gemini model.

Installed and tested versions (kept unchanged):

| Component | Version |
|---|---|
| Python | 3.11.15 in the existing analyst image |
| `google-adk[mcp]` | 2.14.0 |
| `google-genai` | 2.34.0 |
| Official `mcp` SDK | 2.3.0 |
| Pydantic | 2.14.3 |

The installed SDK's `HttpRetryOptions.attempts` includes the original attempt: **1 disables retries**. The trial applies that setting to both adapter and per-request HTTP configuration. SDK construction, local integration and dependency consistency are verified; account entitlement, provider behavior and real model responses are not.

Current official references checked during preparation: [ADK Gemini integration](https://google.github.io/adk-docs/agents/models/google-gemini/), [ADK 2.14.0](https://github.com/google/adk-python/releases/tag/v2.14.0), [GenAI 2.34.0](https://github.com/googleapis/python-genai/releases/tag/v2.34.0), [MCP 2.3.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0).

## Model, authentication and budget

Model: **`gemini-3.5-flash-lite`**, the implementation's existing default, explicitly pinned for this trial. It supports function calling and structured outputs according to Google's [model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite). This is ordinary Gemini Developer API generation, not the separately named streaming Live API.

Google's [standard Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite), checked November 10, lists **$0.30 / million input tokens** and **$2.50 / million output tokens including thinking**. No Search/Maps grounding, browsing, code execution, explicit caching, batch, priority inference, cloud service or paid embedding API is enabled. All model evidence comes from the five read-only GIIM tools.

| Limit | Enforcement |
|---|---|
| Analyst requests | Fixed list of five, sequential, one attempt per scenario |
| Model generation calls | Runtime maximum ten per workflow; shared trial counter maximum 50 |
| Provider retries | Disabled; one attempt per model call |
| Output | 2,048 tokens per call, one candidate |
| Context reservation | Existing byte-based input/output reservation capped at 80,000 per workflow |
| MCP | Existing maximum three tool rounds, five details, nine tool calls per workflow |
| Repair | At most one in-workflow revision; no rerun of a scenario |
| Time | 20-second provider timeout; 180-second workflow timeout |
| Estimated spending | Reserve conservatively before every call; stop before cumulative reservation would exceed $0.95 |
| Actual returned usage | Record prompt, output and thinking counts; stop if missing or above reservation/output allowance |
| Failure | Stop on the first FAIL or BLOCKED result and mark remaining cases BLOCKED |

A conservative planning estimate using the runtime limits is:

`5 × (80,000 × $0.30 + 10 × 2,048 × $2.50) / 1,000,000 + 50 × 1,000 × $0.30 / 1,000,000 = $0.391`

This intentionally overcounts input/output reservations and includes a 1,000-input-token margin per call. Plan for **approximately $0.40 or less**, with a **$1 estimated-budget authorization ceiling**. This is not a measured charge or a provider-enforced account spending cap. Tokenization, provider changes, errors after server-side generation and billing adjustments can differ; missing usage is not treated as zero. The runner stops rather than silently consuming the remaining allowance. Recheck prices before approving a substantially later run.

Authentication is a **Gemini Developer API key**, passed explicitly to the GenAI client with `vertexai=False`. No Application Default Credentials, service-account file, GCP deployment, or production resource modification is needed. Use an existing authorized project/key in [Google AI Studio](https://aistudio.google.com/apikey). Current [key documentation](https://ai.google.dev/gemini-api/docs/api-key) supports authorization keys; unrestricted standard keys are rejected. Do not create a new billable project or enable billing as part of this procedure without separate approval.

| Setting | Required value / handling |
|---|---|
| `GOOGLE_API_KEY` | Loaded inside the analyst process from a private, read-only mounted file; never passed as a command argument or Docker environment value |
| `GIIM_ENABLE_LIVE_GEMINI` | `1` only in the explicitly approved live command |
| `GIIM_LIVE_TRIAL_APPROVAL` | Exact trial authorization phrase shown below; operator interlock, not a substitute for human approval |
| `GIIM_API_URL` | Isolated API's loopback origin; runner pins it to the dedicated container namespace |
| `GIIM_AGENT_MODEL` | Factory explicitly pins `gemini-3.5-flash-lite`; no variable required |
| `GIIM_RESEARCHER_MODEL`, `GIIM_VERIFIER_MODEL` | Do not set; any different effective model is rejected |
| `GIIM_MODEL_PRICES` | Runner passes the reviewed prices directly; no variable required |
| `GIIM_MCP_PUBLISHER_CAPS` | Runner supplies only authored-demo caps, maximum 500 characters |
| Vertex/enterprise flags | Unneeded; direct adapter explicitly selects Developer API |

## Five scenarios and acceptance criteria

All records are authored synthetic material. The backend, embedding model, vector search, transports, orchestration and proposed Gemini calls are real. This demonstrates actual model integration without representing a real-news accuracy benchmark or sending private publisher content to Google.

| Case | Exact question / intervention | PASS criteria |
|---|---|---|
| A: normal research | `What happened at the synthetic AI laboratory? Find the event and cite its reports.` | Researcher searches and retrieves actual event 1; relevant verified answer has valid event/article/publisher/URL/exact-excerpt associations; all roles execute and usage is captured. |
| B: cross-lingual retrieval | `查找描述同一人工智能实验室开放事件的不同语言报道，并引用各个来源。` | Chinese question produces valid citations for at least two source languages sharing event 1; evidence is retrieved through real bge-m3/Qdrant. |
| C: insufficient evidence | `What will happen to the stock market exactly 100 years from now?` | Explicit insufficient-evidence answer, zero claims/citations, no unrelated excerpts presented as verified; all roles and measured usage recorded. |
| D: conflicting evidence | `Compare the contradictory attendance reports for the synthetic storm briefing.` | Event 4's 12-person and 18-person reports both appear with their separate source citations; Researcher flags contradictions and output preserves uncertainty. No invented resolution. |
| E: unsupported citation | `What happened at the synthetic AI laboratory? Verify the source citations.` | After a real Writer response, the harness replaces one event ID and URL with controlled fabricated values on each draft attempt. The real Verifier rejects and the deterministic gate independently rejects the unknown reference. No fabricated citation reaches the final answer. |

E is a deliberate fault-injection experiment, not a claim that Gemini spontaneously hallucinated. Both the original real model usage and the injected response are recorded privately. If the Writer emits no usable draft, the injection was not exercised and the case cannot pass. A repaired or refused unrelated failure is not sufficient proof of citation-gate behavior. If a test fails, fix on `feature/mcp-agent`, rerun local affected tests, and request a new bounded authorization before any additional paid retry beyond this fixed batch.

The product currently produces verified source excerpts, not free-form analytical synthesis. D demonstrates contradiction recognition and attributed preservation within that contract. A human review of relevance, refusal reasoning and contradiction handling remains part of the final report.

## Exact commands

Run from the feature worktree root. In this session that is:

```sh
cd /Users/qida/Documents/Codex/2026-09-21/you-are-taking-over-my-existing/work/mcp-agent
```

Already completed safely: local stack creation, migrations, authored seeding and no-model MCP preflight. Private stack configuration is `.runs/live-gemini/fixture.env`; it contains only the disposable stack's generated database credential and local paths. Never print it or run expanded `docker compose config` without `--quiet`. The existing local images are reused, with current API code mounted read-only. No original application volume is mounted into this stack.

To check the existing stack without paid inference:

```sh
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env ps
```

For recreation on a new machine, configure an equivalent private `fixture.env` with `GIIM_FIXTURE_PASSWORD` (random), `GIIM_LIVE_API_IMAGE` (locally built current API image), `GIIM_FIXTURE_MODEL_CACHE` (existing bge-m3 cache), and `GIIM_TRIAL_OUTPUT` (private absolute directory). Build the analyst image locally as in the acceptance guide if missing. Only on a fresh stack, execute:

```sh
docker compose -p giim-gemini-trial -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env up -d --no-build postgres qdrant api
docker compose -p giim-gemini-trial -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env exec -T api alembic upgrade head
docker compose -p giim-gemini-trial -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env exec -T \
  -e GIIM_TASK2_FIXTURE_ALLOW=isolated-empty-test-stack api python /support/seed_live_api.py
```

**Do not repeat seeding here:** it was completed. The seed rejects nonempty stores; that refusal was also executed and verified. It cannot point to the original database name. If vector insertion succeeds and SQL commit fails, do not bypass guards or clear stores; investigate the disposable stack separately.

Credential setup, entered by the user in their own terminal (not chat), writes a new private file without placing the key in command arguments or shell history:

```sh
python3 - <<'PY'
import getpass
import os
from pathlib import Path
path = Path('.runs/live-gemini/gemini_api_key')
value = getpass.getpass('Gemini API key (hidden): ').strip()
if not value:
    raise SystemExit('No key supplied; nothing written.')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(value + '\n')
print('Private credential file created; key not displayed.')
PY
```

This file is ignored by Git. The key is mounted only into the analyst process; it is not shared with the GIIM API, database, Qdrant or MCP subprocess. Do not import the application's `.env` into the analyst. Credential validity and permissions remain unverified until the approved trial; no separate paid "hello" call is needed.

**Proposed billable command — DO NOT EXECUTE UNTIL EXPLICITLY APPROVED:**

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=five-workflows-max-50-model-calls-under-1-usd \
  analyst --live --credential-file /run/secrets/gemini_api_key \
  --output /results/approved-01
```

The output directory is created exclusively, so repeating this command cannot silently start another paid batch. Do not change the output directory to bypass that guard. Starting fewer than five scenarios due to a failure does not automatically authorize repeated calls. Future approval must explicitly cover any rerun.

After the approved run (local summary only):

```sh
docker run --rm --network none \
  -v "$PWD/.runs/live-gemini:/results:ro" \
  --entrypoint python giim-agent-task2-accepted:local \
  scripts/summarize_runs.py /results/approved-01/traces
```

## Evidence, reports and current status

Private artifacts under `.runs/live-gemini/approved-01/` will include:

- `preflight.json`: actual MCP tools, reviewed evidence identities and installed SDK versions.
- `traces/*.jsonl`: Coordinator/Researcher/Writer/Verifier execution, MCP arguments and latency, model counts and token usage, estimated cost, deterministic checks, revisions, final status and errors.
- `results.json`: each scenario's PASS/FAIL/BLOCKED checks, source-linked final answer, evidence bundle, private structured role responses, fault-injection record, model-call count, reserved estimate and observed usage estimate.

Raw traces and role responses remain private and redacted; no reasoning-chain disclosure is requested. The MCP child receives no Gemini key. The final reviewed `docs/reports/TASK2_LIVE_GEMINI_REPORT.md` will contain sanitized outcomes, exact commands, per-case model/tool counts, latency, usage, cost estimates, relevance review, failures/fixes and remaining limitations. It will clearly distinguish actual Gemini results from earlier mocked tests. It will not be created with fabricated live results before execution.

Current readiness:

| Requirement | Status | Evidence / remaining issue |
|---|---|---|
| Actual GIIM REST API ↔ MCP | PASS | All five tools invoked on two-event authored dataset; exact source checks passed. |
| Live model wiring / pinned SDK configuration | PASS | Inspected real factory and installed SDK; no retries, model pin and opt-in guards locally tested. |
| Local trial controls and existing component regressions | PASS | [115 passing component tests](../evidence/live-gemini-preparation/local-tests.txt), including eight new trial-control cases; two existing dependency deprecation warnings. No paid provider used. |
| Real Gemini authentication and generation | BLOCKED | Awaiting explicit approval and private key provisioning. |
| Scenarios A–E live outcomes | BLOCKED | Not executed; no real model success claimed. |
| Live traces, measured tokens and costs | BLOCKED | Generated only after authorization; estimates above are planning calculations. |

The local test command was:

```sh
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-accepted:local \
  -c 'ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'
```

The successful no-model API preflight command was:

```sh
docker compose -p giim-gemini-trial -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T analyst \
  --preflight --output /results/preflight
```

[Preflight output](../evidence/live-gemini-preparation/preflight.txt) and [readiness inventory](../evidence/live-gemini-preparation/readiness.json) are saved. Runtime code under `apps/agent/src/`, `apps/mcp_server/src/` and `apps/api/` is unchanged by this preparation. The earlier 130-test backend result remains the acceptance baseline; it was not rerun for this harness-only change.

No production resources, main branch, Task 1 worktree, remote repository or existing data were modified. New work consists only of the dedicated trial harness, tests, authored fixture/seed/Compose support and this procedure. No cloud deployment, merge or push occurred.
