# Executed live retest commands

Audit record only. All three approved attempts are consumed; do not rerun. Working directory: the `feature/mcp-agent` worktree. No credential value appears here.

## A

```sh
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

## B

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=abc-only-max-30-model-calls-under-0.30-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --round retest-abc \
  --credential-file /run/secrets/gemini_api_key \
  --resume-from /results/approved-abc-02/results.json \
  --carry-unreported-reservation \
  --output /results/approved-abc-02-continued \
  > .runs/live-gemini/approved-abc-02-continued-console.txt 2>&1
```

## C

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=abc-only-max-30-model-calls-under-0.30-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --round retest-abc \
  --credential-file /run/secrets/gemini_api_key \
  --resume-from /results/approved-abc-02-continued/results.json \
  --carry-unreported-reservation \
  --output /results/approved-abc-02-final \
  > .runs/live-gemini/approved-abc-02-final-console.txt 2>&1
```

## Postflight: zero model calls

```sh
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --preflight --round retest-abc --output /results/abc-retest-postflight
```

## Post-fix regression: network disabled

```sh
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-live-verified:local \
  -c 'ruff format apps/agent/src/giim_agent/roles.py apps/agent/src/giim_agent/schemas.py apps/agent/tests/test_structured_tool.py && ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'
```
