"""明确时间窗口的事件 Feed，以及可追溯的报道详情。"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, case, Float, cast
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.deps import get_db
from src.models.event import Event, EventNews
from src.models.news import News
from src.schemas.events import TodayEventsResponse

router = APIRouter()


from src.utils.events import _event_to_response


@router.get("/events/today", response_model=TodayEventsResponse)
async def get_today_events(
    limit: int = Query(15, ge=1, le=50),
    hours: int = Query(24, ge=1, le=168),
    offset: int = Query(0, ge=0, le=10000),
    region: str | None = Query(None, max_length=32),
    category: str | None = Query(None, max_length=32),
    session: AsyncSession = Depends(get_db),
) -> TodayEventsResponse:
    now = datetime.now(timezone.utc)
    eligible = (
        select(EventNews.event_id)
        .join(News, News.id == EventNews.news_id)
        .where(News.time_quality == "verified", News.published_at.is_not(None))
    )
    conditions = [
        Event.status == "active",
        Event.impact_score.is_not(None),
        Event.last_updated_at >= now - timedelta(hours=hours),
        Event.last_updated_at <= now,
        Event.id.in_(eligible),
    ]
    if region:
        conditions.append(Event.provenance["coverage"]["publisher_regions"].contains([region]))
    if category:
        conditions.append(Event.provenance["category"].astext == category)
    recency_weight = case((Event.impact_factors["formula"].astext == "v3", 0.22), else_=0.5)
    live_score = case(
        (
            Event.impact_factors["formula"].astext.in_(["v2", "v3"]),
            Event.impact_score
            - recency_weight * cast(Event.impact_factors["recency"].astext, Float)
            + recency_weight
            * func.exp(
                -func.greatest(func.extract("epoch", now - Event.last_updated_at) / 3600, 0) / 36
            ),
        ),
        else_=Event.impact_score,
    )
    events = list(
        (
            await session.scalars(
                select(Event)
                .where(*conditions)
                .order_by(desc(live_score), Event.last_updated_at.desc(), Event.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(EventNews.event_id, News.source_name, News.language)
            .join(News, News.id == EventNews.news_id)
            .where(EventNews.event_id.in_([e.id for e in events]))
        )
    ).all()
    sources = {}
    languages = {}
    for eid, source, language in rows:
        sources.setdefault(eid, set()).add(source)
        languages.setdefault(eid, set()).add(language)
    return TodayEventsResponse(
        events=[
            _event_to_response(
                i + offset + 1,
                e,
                len(sources.get(e.id, set())),
                sorted(sources.get(e.id, set())),
                sorted(languages.get(e.id, set())),
            )
            for i, e in enumerate(events)
        ],
        total_events=int(
            await session.scalar(select(func.count()).select_from(Event).where(*conditions)) or 0
        ),
        total_news=int(
            await session.scalar(
                select(func.count())
                .select_from(News)
                .where(
                    News.time_quality == "verified",
                    News.published_at >= now - timedelta(hours=hours),
                    News.published_at <= now,
                )
            )
            or 0
        ),
        total_sources=int(
            await session.scalar(
                select(func.count(func.distinct(News.source_name))).where(
                    News.time_quality == "verified",
                    News.published_at >= now - timedelta(hours=hours),
                    News.published_at <= now,
                )
            )
            or 0
        ),
        generated_at=now,
        window_hours=hours,
        window_start=now - timedelta(hours=hours),
    )
