"""今日 Top 事件 HTTP 路由。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.deps import get_db
from src.models.event import Event, EventNews
from src.models.news import News
from src.schemas.events import EventResponse, TodayEventsResponse
from src.utils.display import duration_str, event_type_label, stars_for_score

router = APIRouter()


def _normalize_summary(summary: str | None) -> str | None:
    """空摘要规范为 null。"""
    if summary is None or not str(summary).strip():
        return None
    return str(summary)


def _event_to_response(rank: int, event: Event, sources_count: int) -> EventResponse:
    """将 ORM Event 转为 API EventResponse。"""
    score = float(event.impact_score)  # 主查询已过滤 IS NOT NULL
    return EventResponse(
        id=event.id,
        rank=rank,
        title=event.title,
        summary=_normalize_summary(event.summary),
        impact_score=score,
        impact_factors=event.impact_factors,
        event_type=event.event_type,
        stars=stars_for_score(score),
        event_type_label=event_type_label(event.event_type),
        first_seen_at=event.first_seen_at,
        last_updated_at=event.last_updated_at,
        duration_str=duration_str(event.first_seen_at, event.last_updated_at),
        news_count=event.news_count,
        sources_count=sources_count,
    )


async def _fetch_sources_counts(
    session: AsyncSession,
    event_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """批量查询每个事件的 distinct source_name 数量。"""
    if not event_ids:
        return {}
    stmt = (
        select(
            EventNews.event_id,
            func.count(func.distinct(News.source_name)),
        )
        .select_from(EventNews)
        .join(News, EventNews.news_id == News.id)
        .where(EventNews.event_id.in_(event_ids))
        .group_by(EventNews.event_id)
    )
    result = await session.execute(stmt)
    return {row[0]: int(row[1]) for row in result.all()}


@router.get(
    "/events/today",
    response_model=TodayEventsResponse,
    summary="今日重要事件 Top N",
    description="按 impact_score 降序返回已评分事件，含展示用 stars/标签/时长及全局统计。",
)
async def get_today_events(
    limit: int = Query(default=15, ge=1, le=50, description="返回条数上限"),
    session: AsyncSession = Depends(get_db),
) -> TodayEventsResponse:
    """按影响力分降序返回今日 Top 事件及全局计数。"""
    total_events = int(await session.scalar(select(func.count()).select_from(Event)) or 0)
    total_news = int(await session.scalar(select(func.count()).select_from(News)) or 0)
    total_sources = int(
        await session.scalar(
            select(func.count(func.distinct(News.source_name))).select_from(News),
        )
        or 0,
    )

    stmt = (
        select(Event)
        .where(Event.impact_score.is_not(None))
        .order_by(desc(Event.impact_score).nulls_last())
        .limit(limit)
    )
    rows: list[Event] = list((await session.execute(stmt)).scalars().all())

    sources_map = await _fetch_sources_counts(session, [e.id for e in rows])
    events = [
        _event_to_response(rank, event, sources_map.get(event.id, 0))
        for rank, event in enumerate(rows, start=1)
    ]

    return TodayEventsResponse(
        events=events,
        total_events=total_events,
        total_news=total_news,
        total_sources=total_sources,
        generated_at=datetime.now(timezone.utc),
    )
