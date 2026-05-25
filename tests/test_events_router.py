"""今日 Top 事件路由测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event

pytestmark = pytest.mark.asyncio


@pytest.mark.xfail(
    reason="fixture 架构: lifespan engine 与 test db_session 不一致, 见 TODO 48",
)
async def test_today_endpoint_default_limit_15(
    async_client_db: AsyncClient,
    sample_events: list[Event],
) -> None:
    """默认 limit=15, 返回已评分事件且按 impact_score 降序。"""
    response = await async_client_db.get("/api/v1/events/today")
    assert response.status_code == 200
    payload = response.json()
    events = payload["events"]
    assert len(events) == len(sample_events)
    assert len(events) <= 15
    scores = [item["impact_score"] for item in events]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.xfail(
    reason="fixture 架构: asyncpg event loop scope 不一致, 见 TODO 48",
)
async def test_today_endpoint_custom_limit(
    async_client_db: AsyncClient,
    sample_events: list[Event],
) -> None:
    """自定义 limit 应限制返回条数。"""
    response = await async_client_db.get("/api/v1/events/today", params={"limit": 3})
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 3
    assert len(sample_events) >= 3


async def test_today_endpoint_limit_out_of_range_422(
    async_client_db: AsyncClient,
) -> None:
    """limit 超出 Query 约束时应返回 422。"""
    for bad_limit in (0, 51):
        response = await async_client_db.get(
            "/api/v1/events/today",
            params={"limit": bad_limit},
        )
        assert response.status_code == 422


@pytest.mark.xfail(
    reason="fixture 架构: asyncpg event loop scope 不一致, 见 TODO 48",
)
async def test_today_endpoint_no_scored_events_returns_200(
    async_client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """无 impact_score 的事件不应出现在 today 列表中。"""
    now = datetime.now(timezone.utc)
    db_session.add(
        Event(
            id=uuid.uuid4(),
            title="未评分事件",
            status="active",
            first_seen_at=now,
            last_updated_at=now,
            news_count=0,
            impact_score=None,
        ),
    )
    await db_session.flush()

    response = await async_client_db.get("/api/v1/events/today")
    assert response.status_code == 200
    assert response.json()["events"] == []
