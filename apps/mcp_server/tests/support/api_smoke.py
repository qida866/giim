"""对运行中 GIIM API 的只读 MCP/ADK 冒烟；不导入后端代码。"""

import asyncio
import json
import os
from pathlib import Path

from mcp import Client
from giim_mcp.config import Settings
from giim_mcp.fixtures import CAPS
from giim_agent.runtime import ask, stdio_target


async def main() -> None:
    settings = Settings.from_env().model_copy(update={"publisher_caps": CAPS})
    observations = {}
    async with Client(stdio_target(settings)) as client:
        assert len((await client.list_tools()).tools) == 5
        for name, args in [
            ("giim_get_today_events", {}),
            ("giim_search_events", {"query": "人工智能实验室"}),
            ("giim_get_event", {"event_id": "00000000-0000-0000-0000-000000000001"}),
            ("giim_get_coverage", {}),
            ("giim_check_ready", {}),
        ]:
            result = await client.call_tool(name, args)
            assert not result.is_error and result.structured_content["ok"], name
            observations[name] = result.structured_content
    detail = observations["giim_get_event"]["data"]
    assert isinstance(detail["articles"][0]["article_id"], int)
    assert detail["event"]["first_seen_at"] and detail["event"]["last_updated_at"]
    assert len(detail["revisions"][0]["evidence_ids"]) == 3
    assert len(observations["giim_get_today_events"]["data"]["events"]) == 1
    assert observations["giim_search_events"]["data"]["events"]
    answer = await ask("What happened at the AI laboratory?", settings=settings, trace_dir=None)
    assert answer.verified and len(answer.claims) == 3, answer.failure_category
    artifact = {
        "method": "Actual isolated GIIM REST API, PostgreSQL, Qdrant and cached CPU bge-m3; fake ADK models",
        "observations": observations,
        "answer": answer.model_dump(mode="json"),
    }
    output = Path(os.getenv("GIIM_SMOKE_OUTPUT", ".runs/actual-api-smoke.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(
        "PASS: all five tools, integer article IDs, event timestamps, revisions, multilingual semantic retrieval and grounded ADK answer."
    )


if __name__ == "__main__":
    asyncio.run(main())
