"""真实 stdio 子进程、受控 REST 与 HTTP 认证边界。"""

import json
import os
import sys

import httpx
import pytest
from mcp import Client, StdioServerParameters

from giim_mcp.demo import demo_api
from giim_mcp.http import create_http_app
from giim_mcp.server import create_server


async def test_subprocess_stdio_all_tools():
    with demo_api() as (url, caps):
        env = {**os.environ, "GIIM_API_URL": url, "GIIM_MCP_PUBLISHER_CAPS": json.dumps(caps)}
        async with Client(
            StdioServerParameters(command=sys.executable, args=["-m", "giim_mcp"], env=env)
        ) as client:
            assert len((await client.list_tools()).tools) == 5
            for name, arguments in [
                ("giim_get_today_events", {}),
                ("giim_search_events", {"query": "AI laboratory"}),
                ("giim_get_event", {"event_id": "00000000-0000-0000-0000-000000000001"}),
                ("giim_get_coverage", {}),
                ("giim_check_ready", {}),
            ]:
                result = await client.call_tool(name, arguments)
                assert not result.is_error and result.structured_content["ok"]


async def test_http_auth_and_origin():
    app = create_http_app(create_server(), token="x" * 40, origins=("https://client.example.org",))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8001"
    ) as client:
        assert (await client.post("/mcp")).status_code == 401
        assert (
            await client.post("/mcp", headers={"Authorization": "Bearer wrong"})
        ).status_code == 401
        headers = {"Authorization": "Bearer " + "x" * 40, "Origin": "https://evil.example.org"}
        assert (await client.post("/mcp", headers=headers)).status_code == 403
        headers["Origin"] = "null"
        assert (await client.post("/mcp", headers=headers)).status_code == 403


def test_http_exposure_requires_auth_host_and_exact_origins():
    for kwargs in (
        {"host": "0.0.0.0"},
        {"host": "0.0.0.0", "token": "x" * 40},
        {"origins": ("*",)},
    ):
        with pytest.raises(ValueError):
            create_http_app(create_server(), **kwargs)


async def test_authenticated_streamable_http_roundtrip():
    import asyncio
    import socket
    import threading
    from contextlib import asynccontextmanager

    import httpx2
    import uvicorn
    from mcp.client.streamable_http import streamable_http_client
    from giim_mcp.adapter import Adapter
    from giim_mcp.config import Settings
    from giim_mcp.rest import RestClient

    with demo_api() as (url, caps):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        token = "test-only-authentication-token-" + "x" * 20
        mcp = create_server(Adapter(RestClient(Settings(api_url=url, publisher_caps=caps))))
        app = create_http_app(mcp, port=port, token=token, origins=("https://client.example.org",))
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.02)
            assert server.started

            @asynccontextmanager
            async def transport():
                async with httpx2.AsyncClient(
                    headers={
                        "Authorization": "Bearer " + token,
                        "Origin": "https://client.example.org",
                    }
                ) as http:
                    async with streamable_http_client(
                        f"http://127.0.0.1:{port}/mcp", http_client=http
                    ) as streams:
                        yield streams[0], streams[1]

            async with Client(transport()) as client:
                assert len((await client.list_tools()).tools) == 5
                for name, arguments in [
                    ("giim_get_today_events", {}),
                    ("giim_search_events", {"query": "AI laboratory"}),
                    ("giim_get_event", {"event_id": "00000000-0000-0000-0000-000000000001"}),
                    ("giim_get_coverage", {}),
                    ("giim_check_ready", {}),
                ]:
                    result = await client.call_tool(name, arguments)
                    assert not result.is_error and result.structured_content["ok"]
                    assert len(result.model_dump_json().encode()) < 20500
                    if name == "giim_get_event":
                        assert result.structured_content["data"]["articles"][0]["excerpt"]
        finally:
            server.should_exit = True
            await asyncio.to_thread(thread.join, 3)
            sock.close()
        assert not thread.is_alive()
