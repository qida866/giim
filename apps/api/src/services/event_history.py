"""提交事务内保存事件修订，重复证据不制造更新。"""

import hashlib
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.event import Event
from src.models.event_revision import EventRevision
from src.models.news import News


async def record_revision(
    session: AsyncSession, event: Event, news: list[News], old_ids: set[int]
) -> None:
    digest = hashlib.sha256(
        json.dumps(
            [
                (event.provenance or {}).get("evidence_hash"),
                event.title,
                event.summary,
                sorted(n.id for n in news),
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    exists = await session.scalar(
        select(EventRevision.id).where(
            EventRevision.event_id == event.id, EventRevision.evidence_hash == digest
        )
    )
    if exists:
        return
    ids = {n.id for n in news}
    session.add(
        EventRevision(
            event_id=event.id,
            evidence_hash=digest,
            snapshot={
                "title": event.title,
                "summary": event.summary,
                "provenance": event.provenance,
                "added_news_ids": sorted(ids - old_ids),
                "removed_news_ids": sorted(old_ids - ids),
                "reporting": [
                    {
                        "news_id": n.id,
                        "title": n.title,
                        "publisher": n.source_name,
                        "published_at": n.published_at.isoformat(),
                        "url": n.source_url,
                    }
                    for n in news
                ],
            },
        )
    )
