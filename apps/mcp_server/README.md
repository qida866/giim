# GIIM read-only MCP adapter

Install in a separate Python 3.11+ virtual environment, not the GIIM API environment:

```sh
python3.11 -m venv .agent-venv
. .agent-venv/bin/activate
pip install -e 'apps/mcp_server[test]'
export GIIM_API_URL=http://127.0.0.1:8000
python -m giim_mcp
```

The last command starts stdio and expects an MCP client. Logs go to stderr. Official MCP SDK **2.3.0** uses `MCPServer`, the renamed `FastMCP`. No database or GIIM internal modules are imported.

Tools: `giim_get_today_events(window="24h", limit=10, language=null)`, `giim_search_events(query, window=null, limit=10)`, `giim_get_event(event_id)`, `giim_get_coverage()`, `giim_check_ready()`. Discover complete schemas with an MCP client. All are read-only and idempotent. Errors use stable codes and omit upstream bodies.

For HTTP: `python -m giim_mcp --transport streamable-http --port 8001`. Defaults to loopback. Remote binding requires a >=32-character bearer token and an explicit public Host; use TLS at a trusted reverse proxy. Origin headers must exactly match `GIIM_MCP_ORIGINS` (comma-separated); no Origin is allowed for native clients. No wildcard CORS is enabled. Never place bearer tokens in command arguments or URLs.

Tool responses are limited to 20,000 JSON bytes plus small protocol overhead and explicitly mark truncation. Unknown publisher excerpts are withheld; `GIIM_MCP_PUBLISHER_CAPS` is an operator-reviewed JSON mapping of exact publisher names to permitted character limits (0–500). A character cap is not a license grant. Publisher URLs containing queries, credentials, fragments or unsafe schemes are withheld. Source URLs are references only and are never fetched.

Search ranks are preserved; absent similarity scores remain null. Coverage describes observed articles, publishers and languages, not global completeness. The Phase 3 readiness route does not expose model loading, so search readiness can remain unknown even with HTTP 200. Event aliases must be fetched by their canonical ID. History is separate from current supporting evidence.

```sh
python -m pytest -q -c apps/mcp_server/pyproject.toml apps/mcp_server/tests
```

Tests exercise the official SDK in-process, over subprocess stdio, and over authenticated Streamable HTTP with controlled authored REST fixtures. Full agent instructions and limitations are in [the integration guide](../../docs/mcp-agent.md).
