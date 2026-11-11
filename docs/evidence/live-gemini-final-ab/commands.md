# Executed final A/B verification commands

Executed after explicit approval on November 11, 2026. Model: `gemini-3.5-flash-lite`. One attempt of each workflow, 20 model attempts including retries maximum, $0.20 estimated ceiling. Results: A PASS, B PASS, ten calls, $0.00785 estimated. No further live calls were made. This is an execution record, not authorization to repeat it.

## Live A/B round

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

Exit 0. Current agent code was mounted over the previously pinned SDK image; the Compose file also mounts the current trial script. The key value never appears in a command, report or committed file. Pre-call checks confirmed a clean feature branch, unused output directory, private key metadata/ignore status and preservation hashes. No resume or workflow replay occurred.

## Postflight — zero model calls

```sh
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --preflight --round retest-ab --output /results/ab-final-postflight \
  > .runs/live-gemini/ab-final-postflight-console.txt 2>&1
```

Exit 0. All five MCP capabilities and the exact two-event authored dataset passed; live flags were absent and the trial did not load a Gemini credential. Normalized complete event-detail data matched the preflight exactly.

## Agent/MCP regression, formatting and dependency checks

```sh
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-ab-ready:local \
  -c 'ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check' \
  > .runs/live-gemini/ab-final-regressions.txt 2>&1
```

Exit 0. 175 passed, three dependency warnings; formatting and installed dependency checks passed. SDK retry tests contacted only their local HTTP stub, not Gemini.

## Original backend regressions — separate isolated test database

```sh
cd /Users/qida/Documents/Codex/2026-09-21/you-are-taking-over-my-existing/work/mcp-validation
docker compose -p giim-mcp-test -f compose.yml --env-file .env run --rm -T \
  -e GOOGLE_API_KEY= -e DEEPSEEK_API_KEY= \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  api python -m pytest -q -p no:cacheprovider \
  -k 'not test_chat_basic and not test_chat_with_system_message' \
  > ../mcp-agent/.runs/live-gemini/ab-final-backend-tests.txt 2>&1
```

Exit 0. 130 passed, two existing paid-provider tests deselected, one existing warning. No application data was reseeded. Local Python scripts exported role responses excluding hidden thought parts/signatures, reconciled metrics against traces, checked preservation hashes and scanned candidate files without printing credential values. Repository checks used `git status`, `git diff --check` and fixed branch refs. No remote Git operation or cloud deployment command ran.
