"""公共边界、同源并发和增量发布原子性回归。"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from src.core.security import PublicLimits
from src.ingestion.deduplicator import deduplicate_and_insert
from src.ingestion.rss_fetcher import ParsedNewsItem
from src.models.news import News
from src.models.event import Event, EventNews
from src.services.event_update import PreparedEvent, publish_events


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/search", "/api/v1/search/events"])
async def test_public_rate_and_body_limits(path: str) -> None:
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route(path, endpoint, methods=["POST"])])
    app.add_middleware(PublicLimits)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        large = await client.post(path, content=b"x" * 32769)
        assert large.status_code == 413
        for _ in range(11):
            r = await client.post(path, json={})
            assert r.status_code == 200
            assert "default-src 'self'" in r.headers["content-security-policy"]
        r = await client.post(path, json={})
        assert r.status_code == 429 and r.headers["retry-after"] == "60"


@pytest.mark.asyncio
async def test_ingestion_rejects_unauthenticated(async_client_db) -> None:
    assert (await async_client_db.post("/api/v1/ingestion/trigger")).status_code == 403


@pytest.mark.asyncio
async def test_incremental_publish_rolls_back_failure(
    db_session, sample_events, monkeypatch
) -> None:
    await db_session.commit()
    event = sample_events[0]
    eid, original_title = event.id, event.title
    news = list(
        (
            await db_session.scalars(select(News).join(EventNews).where(EventNews.event_id == eid))
        ).all()
    )
    original_count = await db_session.scalar(select(func.count()).select_from(EventNews))
    real_flush = db_session.flush

    async def fail_after_flush(*args, **kwargs):
        await real_flush(*args, **kwargs)
        raise RuntimeError("Injected publication failure")

    monkeypatch.setattr(db_session, "flush", fail_after_flush)
    with pytest.raises(RuntimeError, match="Injected"):
        await publish_events(db_session, [PreparedEvent(news, "Wrong replacement", "summary", {})])
    monkeypatch.setattr(db_session, "flush", real_flush)
    assert (await db_session.get(Event, eid)).title == original_title
    assert await db_session.scalar(select(func.count()).select_from(EventNews)) == original_count


@pytest.mark.asyncio
async def test_parallel_same_source_is_serialized(test_engine) -> None:
    source = "concurrency-" + uuid.uuid4().hex
    item = ParsedNewsItem(
        source_name=source,
        source_url="https://example.test/" + source,
        title="A repeated report from the same publisher",
        content="Identical reporting body",
        language="en",
        published_at=datetime.now(timezone.utc),
    )

    async def insert_one(url: str):
        async with AsyncSession(test_engine) as session:
            return await deduplicate_and_insert(
                [item.model_copy(update={"source_url": url})], session
            )

    try:
        results = await asyncio.gather(
            insert_one(item.source_url), insert_one(item.source_url + "-copy")
        )
        assert sum(r.inserted for r in results) == 1
    finally:
        async with AsyncSession(test_engine) as session:
            await session.execute(delete(News).where(News.source_name == source))
            await session.commit()


def test_legacy_mutations_fail_closed_in_production(monkeypatch) -> None:
    from scripts.legacy_guard import allow_legacy_mutation

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GIIM_ALLOW_LEGACY_MUTATION", "true")
    assert not allow_legacy_mutation()


def test_production_alias_still_requires_secret() -> None:
    from src.core.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(APP_ENV="prod", INGESTION_TRIGGER_TOKEN="short")
