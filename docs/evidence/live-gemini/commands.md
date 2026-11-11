# Live-trial execution record

These commands were executed from the `feature/mcp-agent` worktree. Live commands below have already consumed all five authorized workflow slots. **Do not rerun without a new authorization.** Console redirections only save private output; they do not display credentials. Private configuration contents are intentionally absent.

## Live runs (one attempt per scenario)

### A

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=five-workflows-max-50-model-calls-under-1-usd \
  analyst --live --credential-file /run/secrets/gemini_api_key \
  --output /results/approved-01 > .runs/live-gemini/approved-01-console.txt 2>&1
```

### B

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=five-workflows-max-50-model-calls-under-1-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --credential-file /run/secrets/gemini_api_key \
  --resume-from /results/approved-01/results.json \
  --output /results/approved-01-continued > .runs/live-gemini/approved-01-continued-console.txt 2>&1
```

### C

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=five-workflows-max-50-model-calls-under-1-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --credential-file /run/secrets/gemini_api_key \
  --resume-from /results/approved-01-continued/results.json \
  --carry-unreported-reservation \
  --output /results/approved-01-final > .runs/live-gemini/approved-01-final-console.txt 2>&1
```

### D and E

```sh
GIIM_GEMINI_KEY_FILE="$PWD/.runs/live-gemini/gemini_api_key" \
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -e GIIM_ENABLE_LIVE_GEMINI=1 \
  -e GIIM_LIVE_TRIAL_APPROVAL=five-workflows-max-50-model-calls-under-1-usd \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --live --credential-file /run/secrets/gemini_api_key \
  --resume-from /results/approved-01-final/results.json \
  --carry-unreported-reservation \
  --output /results/approved-01-remaining > .runs/live-gemini/approved-01-remaining-console.txt 2>&1
```

## Source regression, formatting and dependency checks (network disabled)

```sh
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-accepted:local \
  -c 'ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'

docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint python giim-agent-task2-accepted:local -m giim_agent.eval \
  --output .runs/live-gemini/postfix-evaluation.json \
  --trace-dir .runs/live-gemini/postfix-eval-traces
```

## Postflight (no model)

```sh
docker compose -p giim-gemini-trial -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T analyst \
  --preflight --output /results/postflight
```

## Packaging checks (network disabled)

The clean build below failed because its dependency-install layer was not cached and PyPI was unavailable with network disabled. It did not establish a package incompatibility.

```sh
BUILDX_CONFIG=../mcp-validation/buildx docker build --network none \
  -f apps/agent/Dockerfile -t giim-agent-task2-live-verified:local .
```

The incremental verification used this temporary private Dockerfile over the existing pinned dependency image, rebuilding and installing both local packages without dependency downloads:

```dockerfile
FROM giim-agent-task2-accepted:local
USER root
COPY apps/mcp_server /app/apps/mcp_server
COPY apps/agent /app/apps/agent
COPY scripts/summarize_runs.py scripts/sample_agent_evals.py scripts/live_gemini_trial.py /app/scripts/
RUN pip install --no-index --no-build-isolation --no-deps --force-reinstall /app/apps/mcp_server /app/apps/agent && pip check && chown -R analyst:analyst /app
USER analyst
```

```sh
BUILDX_CONFIG=../mcp-validation/buildx docker build --network none \
  -f .runs/live-gemini/Dockerfile.verify -t giim-agent-task2-live-verified:local .
docker run --rm --network none --entrypoint sh giim-agent-task2-live-verified:local \
  -c 'python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'
```

## Historical trace summary (no model)

```sh
docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint python giim-agent-task2-accepted:local \
  scripts/summarize_runs.py .runs/live-gemini/all-traces \
  > docs/evidence/live-gemini/trace-summary.json
```
