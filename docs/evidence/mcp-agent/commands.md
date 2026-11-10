# Task 2 validation commands

Validation date: November 10, 2026. Tested code commit: `74b64d380078c05f7bdad0b69e6f0517b62e3801`. The fresh analyst image contains non-editable packages installed from this commit. Final docs/evidence are added afterward. All model calls were fake or mocked; no hosted requests were authorized or made.

Commands below record the final meaningful validations and earlier baseline checks. Development formatting/test iterations are not an additional benchmark. `$REPO` denotes the Task 2 worktree; the private sibling `mcp-validation` directory held an isolated Compose stack and random credentials, not committed files. No secret values or private configuration are reproduced here.

## SDK environment and clean installation

The independently installed development environment was frozen to `apps/agent/requirements.lock`. Exact replay of its pins, including test dependencies:

```sh
python3.11 -m venv .agent-venv
. .agent-venv/bin/activate
python -m pip install -r apps/agent/requirements.lock
python -m pip install --no-build-isolation --no-deps -e apps/mcp_server -e apps/agent
python -m pip check
```

Editable installation and `pip check` were smoke-tested in the SDK container. The final clean-image command was run from the worktree (Buildx metadata was redirected into the allowed workspace):

```sh
BUILDX_CONFIG=../mcp-validation/buildx docker build \
  -f apps/agent/Dockerfile -t giim-agent-task2:local .
docker run --rm giim-agent-task2:local ask 'AI laboratory' --demo --json
```

Both succeeded. The final Docker build's manifest list was `sha256:0d26653e5543836fded1ed8882d35f50f880e684f4011054df7c54b07893a120`. It used Python 3.11.15 and ran as UID 10001. The image build checks the pinned environment with `pip check`. SDK license/version evidence is in `sdk-metadata.json`; ADK's installed license file was additionally inspected.

## Original backend baseline and regression

The clean public base failed migrations/test collection because two imported model modules were missing; see `baseline-clean.txt`. Exact preexisting Phase 3 modules were restored independently in commit `1803317`; the root model-cache ignore was anchored. No original test was edited.

Run inside the isolated API environment, with a migrated `_test` database and cached bge-m3:

```sh
python -m pytest -q -m 'not integration'
```

Result: **121 passed, 11 deselected** (`baseline-fast.txt`). The wider no-billing selection was run before and after implementation, from the private validation directory:

```sh
docker compose -p giim-mcp-test -f compose.yml --env-file .env run --rm -T api \
  python -m pytest -q -k 'not test_chat_basic and not test_chat_with_system_message'
```

Baseline: **130 passed, 2 deselected**, one existing structlog warning (`backend-baseline-allowed.txt`). Final: **130 passed, 2 deselected**, same warning (`backend-regression.txt`). The two excluded live LLM integration tests were not modified, skipped in code or declared passing. They require separately authorized billable access. Tests exercised the isolated stack, not original GIIM data. The validation API reused the previously built Phase 3 dependency image with this branch's source mounted; the MCP/agent image was built fresh from its own Dockerfile.

## New tests and formatting

Initial MCP stage: **46 passed**, two third-party deprecation warnings (`mcp-stage.txt`). Runtime contract findings later added coverage for integer article IDs, actual today response wrapping, timestamps and current support. Final combined suite:

```sh
docker run --rm --entrypoint python giim-agent-task2:local \
  -m pytest -q -c /app/apps/agent/pyproject.toml \
  /app/apps/agent/tests /app/apps/mcp_server/tests
```

Result: **103 passed**, two uvicorn/websockets deprecation warnings, **24.02 seconds** (`agent-and-mcp-tests.txt`). Includes official in-process MCP, stdio subprocess, authenticated HTTP, real ADK Runner, CLI, ADK CLI and local ADK Web session API tests. No GUI visual check or paid model test is implied.

```sh
docker run --rm -v "$PWD:/workspace" -w /workspace --entrypoint sh giim-agent-task2:local \
  -c 'ruff check apps/agent apps/mcp_server scripts/summarize_runs.py scripts/sample_agent_evals.py && ruff format --check apps/agent apps/mcp_server scripts/summarize_runs.py scripts/sample_agent_evals.py && pip check'
GIIM_FIXTURE_PASSWORD=configuration_check_placeholder \
  GIIM_FIXTURE_MODEL_CACHE=/tmp/giim-model-cache \
  docker compose -f apps/mcp_server/tests/support/compose.yml config --quiet
git diff --check
```

All passed. Compose interpolation used a noncredential placeholder only for `config --quiet`, never a database password in a running container. The portable harness was configuration-validated; its seed/smoke scripts were executed against the actual validation stack described next.

## Actual GIIM API / semantic-search smoke

An explicitly guarded helper seeded **one authored event, three articles and three real bge-m3 vectors** in the fresh isolated test stores. The helper is outside the MCP runtime and refuses nonempty stores. No ingestion or paid API was used. Its first developmental attempt found the absent vector collection, then a missing fixture `time_quality` field; the helper and the three authored fixture payloads were corrected before final validation. These were harness defects, not backend regressions. The original databases were never seeded or altered.

```sh
docker run --rm --network container:giim-mcp-test-api \
  -e GIIM_API_URL=http://127.0.0.1:8000 \
  -e GIIM_SMOKE_OUTPUT=/results/actual-api-smoke.json \
  -v "$PWD/.runs/task2-policy-final:/results" --entrypoint python giim-agent-task2:local \
  /app/apps/mcp_server/tests/support/api_smoke.py
```

PASS: all five tools, integer article IDs, timestamps, revisions, a Chinese query through actual bge-m3/Qdrant, and a three-source grounded ADK answer with fake models. See `actual-api-smoke.json`. The test store contains only authored reports. This is a contract/integration smoke, not a retrieval quality benchmark. `openapi-task2.json` was captured from this branch's running API; no Task 1 route changes were merged.

## Reproducible evaluation and trace summary

Run after the final code commit with only documentation/evidence edits pending (`dirty_worktree=true`); Git metadata was explicitly supplied to the image, which does not include `.git`:

```sh
mkdir -p .runs/task2-policy-final
docker run --rm -v "$PWD/.runs/task2-policy-final:/results" \
  -e GIIM_EVAL_COMMIT=74b64d380078c05f7bdad0b69e6f0517b62e3801 -e GIIM_EVAL_DIRTY=1 \
  --entrypoint python giim-agent-task2:local -m giim_agent.eval \
  --output /results/evaluation.json --trace-dir /results/traces
docker run --rm -v "$PWD/.runs/task2-policy-final:/results" --entrypoint python giim-agent-task2:local \
  scripts/summarize_runs.py /results/traces
docker run --rm -v "$PWD/.runs/task2-policy-final:/results" --entrypoint python giim-agent-task2:local \
  scripts/sample_agent_evals.py /results/evaluation.json --output /results/human-review.json
```

**24/24 expected deterministic outcomes:** 10 verified excerpt answers, 14 expected refusals, zero execution errors. Files: `evaluation-fake.json`, `evaluation-table.txt`, `trace-summary.json`, `human-review-unrated.json`. Only authored data and aggregate trace statistics were exported; raw traces remain ignored. Ten sampled cases remain explicitly **unrated**. Fake-model token/cost measurements are null. Evaluation ran locally while regression tooling was also active; timings are reproducibility observations, not isolated-load performance measurements.

## Security and repository checks

Local read-only Python inspection scanned candidate files plus reachable Git blob contents for provider/private-key/credential-URL patterns and exact values from available private credential configuration. Values were never printed. Findings were reviewed as templates/tests or historical development examples; no current local credential matched. See the bounded claims and caveats in `security-review.json`.

```sh
git diff 651ffbc -- tests requirements.lock pyproject.toml apps/api/src/api frontend scripts/pipeline.py
git check-ignore .runs/probe .adk/probe .agent-venv/probe apps/agent/.env
git show-ref --verify refs/heads/main
git show-ref --verify refs/heads/feature/gcp-deploy
git show-ref --verify refs/remotes/origin/main
git status --short
```

The diff selection was empty. Main remained `28edc62816d44254d7b5b532beaeec421762bb34`; Task 1 remained `4e7b93135432d1885083822c764b8ac4c8d9feb7`; cached `origin/main` remained `651ffbc1a038c76c7c0d74be30bcc2b4538faf4d`. No branch merge, history rewrite, remote push or cloud deployment occurred. The final documentation commit follows the tested implementation commit.
