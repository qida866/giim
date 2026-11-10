"""协议发现、类型验证和真实内存 MCP 调用。"""

import pytest
import respx
from mcp import Client

from giim_mcp.adapter import Adapter
from giim_mcp.config import Settings
from giim_mcp.fixtures import CAPS, RECORDS, identifier
from giim_mcp.models import Envelope
from giim_mcp.rest import RestClient
from giim_mcp.server import create_server

NAMES = {
    "giim_get_today_events",
    "giim_search_events",
    "giim_get_event",
    "giim_get_coverage",
    "giim_check_ready",
}


def server():
    return create_server(Adapter(RestClient(Settings(publisher_caps=CAPS))))


async def test_discovery_and_all_tools():
    with respx.mock(base_url="http://127.0.0.1:8000") as api:
        api.get("/api/v1/events/today").respond(json=[RECORDS[0]["event"]])
        api.post("/api/v1/search/events").respond(json={"events": [RECORDS[0]["event"]]})
        api.get("/api/v1/events/" + identifier(1)).respond(json=RECORDS[0])
        api.get("/api/v1/coverage").respond(
            json={"reporting_languages": ["en"], "coverage_basis": "observed"}
        )
        api.get("/api/v1/ready").respond(
            json={"status": "ready", "database": True, "vectors": True}
        )
        async with Client(server()) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == NAMES
            for tool in tools:
                assert tool.annotations.read_only_hint and tool.annotations.idempotent_hint
                assert not tool.annotations.destructive_hint
                assert tool.output_schema and tool.input_schema
            inputs = {
                "giim_get_today_events": {},
                "giim_search_events": {"query": "AI"},
                "giim_get_event": {"event_id": identifier(1)},
                "giim_get_coverage": {},
                "giim_check_ready": {},
            }
            for name, arguments in inputs.items():
                result = await client.call_tool(name, arguments)
                assert not result.is_error
                parsed = Envelope.model_validate(result.structured_content)
                assert parsed.ok and parsed.data
            result = await client.call_tool("giim_check_ready")
            assert result.structured_content["data"]["search_ready"] is None


@pytest.mark.parametrize(
    "name,args",
    [
        ("giim_get_today_events", {"window": "year"}),
        ("giim_get_today_events", {"limit": 26}),
        ("giim_get_today_events", {"language": "x"}),
        ("giim_search_events", {"query": ""}),
        ("giim_search_events", {"query": "a" * 301}),
        ("giim_search_events", {"query": "AI", "limit": 21}),
        ("giim_search_events", {"query": "AI", "window": "year"}),
        ("giim_get_event", {"event_id": "not-a-uuid"}),
        ("giim_get_coverage", {"admin": True}),
        ("giim_check_ready", {"path": "/admin"}),
    ],
)
async def test_invalid_inputs(name, args):
    async with Client(server()) as client:
        await client.list_tools()
        result = await client.call_tool(name, args)
        assert result.is_error


async def test_whitespace_and_unknown_tool():
    async with Client(server()) as client:
        await client.list_tools()
        result = await client.call_tool("giim_search_events", {"query": "   "})
        assert result.structured_content["error"]["code"] == "invalid_request"
        result = await client.call_tool("giim_trigger_ingestion", {})
        assert result.is_error


async def test_language_filter_scores_and_support():
    with respx.mock as api:
        api.get("http://127.0.0.1:8000/api/v1/events/today").respond(
            json=[r["event"] for r in RECORDS[:2]]
        )
        api.get("http://127.0.0.1:8000/api/v1/events/" + identifier(3)).respond(json=RECORDS[2])
        adapter = Adapter(RestClient(Settings(publisher_caps=CAPS)))
        result = await adapter.today("3d", 10, "zh")
        assert len(result.events) == 1 and "50" in result.language_filter_scope
        assert result.events[0].relevance_score is None
        event = await adapter.event(__import__("uuid").UUID(identifier(3)))
        assert event.articles[-1].current_support is False
        assert event.llm_review_status is None and len(event.revisions) == 1
