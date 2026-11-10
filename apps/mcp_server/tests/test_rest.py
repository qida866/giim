"""REST 错误、限制和无写权限测试。"""

import copy
from uuid import UUID

import httpx
import pytest
import respx

from giim_mcp.adapter import Adapter
from giim_mcp.config import Settings, safe_url
from giim_mcp.fixtures import CAPS, RECORDS, identifier
from giim_mcp.rest import AdapterError, RestClient


@pytest.mark.parametrize(
    "status,code,calls",
    [
        (404, "not_found", 1),
        (422, "invalid_request", 1),
        (429, "rate_limited", 2),
        (502, "unavailable", 2),
        (503, "unavailable", 2),
        (504, "unavailable", 2),
        (401, "unavailable", 1),
        (302, "unavailable", 1),
    ],
)
async def test_error_mapping(status, code, calls):
    with respx.mock as api:
        route = api.post("http://127.0.0.1:8000/api/v1/search/events").respond(
            status, text="PRIVATE"
        )
        adapter = Adapter(RestClient(Settings()))
        result = await adapter.guarded(lambda: adapter.search("AI", None, 10))
        assert result.error.code == code and route.call_count == calls
        assert "PRIVATE" not in result.model_dump_json()


async def test_timeout_retried_once_and_recovery():
    with respx.mock as api:
        route = api.get("http://127.0.0.1:8000/api/v1/coverage")
        route.side_effect = httpx.ReadTimeout("secret credential URL")
        client = RestClient(Settings())
        with pytest.raises(AdapterError, match="timeout"):
            await client.request("GET", "/api/v1/coverage")
        assert route.call_count == 2
        route.side_effect = [httpx.ConnectError("private"), httpx.Response(200, json={"ok": True})]
        assert await client.request("GET", "/api/v1/coverage") == {"ok": True}


@pytest.mark.parametrize("body", ["not json", "null", "42", "{}", '"secret"'])
async def test_malformed(body):
    with respx.mock as api:
        api.get("http://127.0.0.1:8000/api/v1/coverage").respond(text=body)
        adapter = Adapter(RestClient(Settings()))
        result = await adapter.guarded(adapter.coverage)
        assert result.error.code == "malformed_response"


async def test_oversized_upstream():
    with respx.mock as api:
        api.get("http://127.0.0.1:8000/api/v1/coverage").respond(content=b"x" * 20001)
        client = RestClient(Settings(upstream_bytes=20000))
        with pytest.raises(AdapterError, match="response_too_large"):
            await client.request("GET", "/api/v1/coverage")


async def test_licensing_excerpt_and_total_cap():
    data = copy.deepcopy(RECORDS[0])
    data["articles"] = data["articles"] * 40
    for row in data["articles"]:
        row["excerpt"] = "原" * 2000
    with respx.mock as api:
        api.get("http://127.0.0.1:8000/api/v1/events/" + identifier(1)).respond(json=data)
        adapter = Adapter(RestClient(Settings(publisher_caps=CAPS)))
        result = await adapter.guarded(lambda: adapter.event(UUID(identifier(1))))
        assert result.truncated and len(result.model_dump_json().encode()) <= 20000
        assert all(len(s.excerpt) <= 500 for s in result.data.articles)
        adapter = Adapter(RestClient(Settings()))
        result = await adapter.guarded(lambda: adapter.event(UUID(identifier(1))))
        assert all(s.excerpt is None for s in result.data.articles)
        adapter = Adapter(RestClient(Settings(publisher_caps={"Authored Demo en": 50})))
        result = await adapter.guarded(lambda: adapter.event(UUID(identifier(1))))
        assert all(s.excerpt is None or len(s.excerpt) <= 50 for s in result.data.articles)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/ingestion/trigger"),
        ("GET", "/api/v1/admin/operations"),
        ("DELETE", "/api/v1/events/today"),
        ("GET", "/api/v1/events/../admin"),
        ("GET", "https://evil.example.org"),
    ],
)
async def test_route_allowlist(method, path):
    with pytest.raises(AdapterError, match="invalid_request"):
        await RestClient(Settings()).request(method, path)


@pytest.mark.parametrize(
    "url",
    [
        "http://user:password@localhost",
        "http://external.example.org",
        "http://localhost/api",
        "https://example.org?token=secret",
    ],
)
def test_config_origin_restrictions(url):
    with pytest.raises(ValueError):
        Settings(api_url=url)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://u:p@example.org/",
        "https://example.org/?token=private",
        "https://example.org/\n",
    ],
)
def test_source_url_restrictions(url):
    assert safe_url(url) is None


async def test_actual_api_contract_integer_ids_timestamps_and_today_wrapper():
    from giim_mcp.normalize import detail
    from giim_mcp.fixtures import STAMP

    row = copy.deepcopy(RECORDS[0])
    row["revisions"] = [
        {
            "recorded_at": STAMP,
            "origin_event_id": identifier(1),
            "title": "Authored update",
            "reporting": [{"news_id": 101}],
        }
    ]
    result = detail(row, UUID(identifier(1)), Settings(publisher_caps=CAPS))
    assert result.articles[0].article_id == 101 and result.articles[0].current_support
    assert result.event.first_seen_at == STAMP and result.event.last_updated_at == STAMP
    assert result.revisions[0].evidence_ids == [101]
    with respx.mock as api:
        api.get("http://127.0.0.1:8000/api/v1/events/today").respond(
            json={"events": [row["event"]], "total_events": 1}
        )
        adapter = Adapter(RestClient(Settings()))
        assert len((await adapter.today("24h", 10, None)).events) == 1


@pytest.mark.parametrize(
    "status,model,expected",
    [
        ("ready", None, None),
        ("ready", False, False),
        ("ready", True, True),
        ("degraded", True, False),
        ("unavailable", None, False),
    ],
)
def test_readiness_never_infers_model_from_storage(status, model, expected):
    from giim_mcp.normalize import readiness

    row = {"status": status, "database": True, "vectors": True}
    if model is not None:
        row["model_loaded"] = model
    assert readiness(row).search_ready is expected
