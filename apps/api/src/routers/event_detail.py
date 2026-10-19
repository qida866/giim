"""事件详情、可追溯视角和追加式报道修订。"""

import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.deps import get_db
from src.models.event import Event, EventNews
from src.models.news import News
from src.models.event_revision import EventRevision
from src.utils.events import _event_to_response

router = APIRouter()


@router.get("/events/{event_id}")
async def event_detail(
    event_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    base = (
        select(News)
        .join(EventNews, News.id == EventNews.news_id)
        .where(EventNews.event_id == event.id)
    )
    articles = list(
        (
            await session.scalars(
                base.order_by(News.published_at.desc().nulls_last(), News.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    sources = (
        await session.execute(
            select(News.source_name, News.language, func.count())
            .join(EventNews, News.id == EventNews.news_id)
            .where(EventNews.event_id == event.id)
            .group_by(News.source_name, News.language)
        )
    ).all()
    distinct = {r[0] for r in sources}
    merged_ids = (event.provenance or {}).get("consolidation", {}).get("source_event_ids", [])
    history_ids = [event.id] + [uuid.UUID(value) for value in merged_ids]
    revisions = list(
        (
            await session.scalars(
                select(EventRevision)
                .where(EventRevision.event_id.in_(history_ids))
                .order_by(EventRevision.recorded_at.desc())
                .limit(20)
            )
        ).all()
    )
    comparison = (event.provenance or {}).get("perspectives", {})
    return {
        "event": _event_to_response(
            1, event, len(distinct), sorted(distinct), sorted({r[1] for r in sources})
        ).model_dump(mode="json"),
        "status": event.status,
        "provenance": event.provenance,
        "articles": [
            {
                "id": n.id,
                "title": n.title,
                "url": n.source_url,
                "source": n.source_name,
                "language": n.language,
                "published_at": n.published_at.isoformat() if n.published_at else None,
                "time_quality": n.time_quality,
                "excerpt": n.content[:1000],
                "provenance": {
                    k: v
                    for k, v in (n.raw_metadata or {}).items()
                    if k
                    in {
                        "publisher_id",
                        "publisher_country",
                        "publisher_region",
                        "source_role",
                        "byline",
                        "occurred_at",
                        "timestamp_semantics",
                    }
                },
            }
            for n in articles
        ],
        "total_articles": event.news_count,
        "offset": offset,
        "revisions": [{"recorded_at": r.recorded_at.isoformat(), "origin_event_id": str(r.event_id), **r.snapshot} for r in revisions],
        "canonical_event_id": (event.provenance or {}).get("canonical_event_id"),
        "current_support_ids": (event.provenance or {}).get("current_support_ids", (event.provenance or {}).get("evidence_ids", [])),
        "timeline_basis": "Reporting publication times and GIIM observation times; not inferred incident occurrence times.",
        "perspectives": {
            **comparison,
            "mode": "evidence_compared" if any(comparison.values()) else "attributed_reporting",
            "note": "Compare original reporting below. Different wording alone is not evidence of disagreement.",
            "publishers": [
                {"name": r[0], "language": r[1], "article_count": r[2]} for r in sources
            ],
        },
    }
