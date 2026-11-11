# Local verification commands — no Gemini calls

Commands ran from the `feature/mcp-agent` worktree unless stated otherwise. `.runs` paths are private outputs, not publisher datasets. No actual credential was mounted into these test containers. The real-SDK test uses a local HTTP server and a synthetic canary credential, with network disabled.

## Complete source suite, formatting and dependencies

```sh
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint sh giim-agent-task2-live-verified:local \
  -c 'ruff format apps/agent/tests/test_live_trial.py && ruff check apps/agent apps/mcp_server scripts/live_gemini_trial.py && ruff format --check apps/agent apps/mcp_server scripts/live_gemini_trial.py && python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'
```

## Original backend (private sibling work/mcp-validation directory)

```sh
docker compose -p giim-mcp-test -f compose.yml --env-file .env run --rm -T \
  -e GOOGLE_API_KEY= -e DEEPSEEK_API_KEY= \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  api python -m pytest -q -p no:cacheprovider \
  -k 'not test_chat_basic and not test_chat_with_system_message'
```

## Deterministic evaluation

```sh
docker run --rm --network none -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/apps/agent/src:/workspace/apps/mcp_server/src \
  --entrypoint python giim-agent-task2-live-verified:local -m giim_agent.eval \
  --output .runs/live-gemini/ab-reliability/evaluation.json \
  --trace-dir .runs/live-gemini/ab-reliability/eval-traces
```

## Installed packages (no dependency downloads)

The temporary private verification Dockerfile used the existing pinned dependency image, copied current agent/MCP sources and the three reporting/trial scripts, then installed both packages with `pip install --no-index --no-build-isolation --no-deps --force-reinstall`. This verifies local wheel installation without rebuilding/downloading the dependency stack.

```sh
BUILDX_CONFIG=../mcp-validation/buildx docker build --network none \
  -f .runs/live-gemini/Dockerfile.verify -t giim-agent-task2-ab-ready:local .
docker run --rm --network none --entrypoint sh giim-agent-task2-ab-ready:local \
  -c 'python -m pytest -q -p no:cacheprovider -c apps/agent/pyproject.toml apps/agent/tests apps/mcp_server/tests && pip check'
```

## Actual API/MCP preflight — zero model calls

```sh
docker compose -p giim-gemini-trial \
  -f apps/mcp_server/tests/support/live-compose.yml \
  --env-file .runs/live-gemini/fixture.env run --rm -T \
  -v "$PWD/apps/agent/src:/trial-agent:ro" -e PYTHONPATH=/trial-agent \
  analyst --preflight --round retest-ab --output /results/ab-reliability/preflight
```

The unexecuted, approval-required live command is in [the reliability report](../../reports/TASK2_AB_RELIABILITY_REPORT.md).
