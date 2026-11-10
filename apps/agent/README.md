# GIIM Google ADK analyst

Independent Python package with a bounded Researcher, Coordinator and Verifier workflow, real MCP tool communication, deterministic citation checks and private traces.

For a credential-free run, install the independent pinned environment from the repository root:

```sh
python3.11 -m venv .agent-venv
. .agent-venv/bin/activate
python -m pip install -r apps/agent/requirements.lock
python -m pip install --no-build-isolation --no-deps -e apps/mcp_server -e apps/agent
python -m giim_agent ask "AI laboratory" --demo --trace
```

The demo is explicitly authored data plus scripted ADK models. Live Gemini is opt-in and was not called during local validation. See the [complete guide](../../docs/mcp-agent.md), [evaluation questions](evals/questions.yaml) and [engineering report](../../docs/reports/mcp-agent-report.md).
