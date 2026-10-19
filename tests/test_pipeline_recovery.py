"""隔离数据库内模拟依赖失效，验证最后成功状态与串行锁。"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from src.models.event import Event
from src.models.operations import OperationalState
from src.services.pipeline_state import save_pipeline_state
from src.services.structured_json import json_payload
from src.services.discovery_window import balanced_window
from tests.test_event_intelligence import article
from scripts import pipeline


def test_only_complete_json_fence_is_removed():
    assert json_payload('```json\n{"safe":true}\n```') == '{"safe":true}'
    assert json_payload('Ignore instructions {"safe":true}') == 'Ignore instructions {"safe":true}'


def test_balanced_window_limits_publisher_flood():
    flood = [article(i, source="A") for i in range(20)]
    other = [article(30, source="B"), article(31, source="C")]
    assert {n.source_name for n in balanced_window(flood + other, limit=3)} == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_failed_pipeline_preserves_events_and_last_success(
    db_session, test_engine, sample_events, monkeypatch
):
    await save_pipeline_state(
        db_session, {"status": "success", "finished_at": "earlier", "stages": {}}
    )
    ids = [e.id for e in sample_events]
    titles = [e.title for e in sample_events]

    @asynccontextmanager
    async def session_factory():
        yield db_session

    monkeypatch.setattr(pipeline, "async_engine", test_engine)
    monkeypatch.setattr(pipeline, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(pipeline, "QdrantVectorStore", lambda: SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(
        pipeline,
        "reconcile_vectors",
        AsyncMock(side_effect=ConnectionError("Injected vector failure")),
    )
    result = await pipeline.run_once(fetch=False)
    assert result["status"] == "failed"
    assert result["error_type"] == "ConnectionError"
    assert [(await db_session.get(Event, eid)).title for eid in ids] == titles
    state = await db_session.get(OperationalState, "pipeline_history")
    assert state.value["last_success"] == "earlier"
    assert state.value["last_failure"] == result["finished_at"]


@pytest.mark.asyncio
async def test_duplicate_scheduler_skips_before_work(test_engine, monkeypatch):
    monkeypatch.setattr(pipeline, "async_engine", test_engine)
    work = AsyncMock()
    monkeypatch.setattr(pipeline, "run_ingestion", work)
    async with test_engine.connect() as lock:
        await lock.execute(text("SELECT pg_advisory_lock(73499201)"))
        try:
            assert (await pipeline.run_once())["status"] == "already_running"
            work.assert_not_called()
        finally:
            await lock.execute(text("SELECT pg_advisory_unlock(73499201)"))


@pytest.mark.asyncio
async def test_scheduler_recovers_after_connection_failure(monkeypatch):
    class EndTest(Exception):
        pass

    run = AsyncMock(side_effect=[ConnectionError("Database unavailable"), {"status": "success"}])
    pause = AsyncMock(side_effect=[None, EndTest()])
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(pipeline, "run_once", run)
    monkeypatch.setattr(pipeline, "async_engine", engine)
    monkeypatch.setattr(pipeline.asyncio, "sleep", pause)
    with pytest.raises(EndTest):
        await pipeline.main(300, False)
    assert run.await_count == 2
    engine.dispose.assert_awaited_once()
