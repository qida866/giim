"""Seed only a fresh, separately named live-trial test store with authored data."""

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from src.db.session import AsyncSessionLocal
from src.embedding import EmbeddingClient, EmbeddingRequest
from src.models.event import Event, EventNews
from src.models.event_revision import EventRevision
from src.models.news import News
from src.vector_store import QdrantVectorStore, UpsertRequest, VectorPoint


async def main():
    if os.getenv("GIIM_TASK2_FIXTURE_ALLOW") != "isolated-empty-test-stack" or not os.environ[
        "DATABASE_URL"
    ].endswith("/giim_live_trial_test"):
        raise RuntimeError("Only the explicitly named isolated live-trial test database is allowed")
    rows = json.loads(Path(__file__).with_name("live_fixture.json").read_text())
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        for model in (News, Event, EventNews, EventRevision):
            if await session.scalar(select(func.count()).select_from(model)):
                raise RuntimeError("Refusing to seed nonempty stores; no rows were deleted")
        store = QdrantVectorStore()
        try:
            await store.ensure_collection()
            if await store.count():
                raise RuntimeError("Refusing to seed nonempty vectors")
            articles = []
            for row in rows:
                event_id = UUID(row["event"]["id"])
                support = [s["id"] for s in row["articles"]]
                event = Event(
                    id=event_id,
                    title=row["event"]["title"],
                    summary="Authored live-trial fixture.",
                    news_count=len(support),
                    first_seen_at=now,
                    last_updated_at=now,
                    impact_score=0.7,
                    status="active",
                    provenance={
                        "mode": "synthetic",
                        "current_support_ids": support,
                        "evidence_ids": support,
                    },
                )
                sources = [
                    News(
                        id=s["id"],
                        source_name=s["source"],
                        source_url=s["url"],
                        url_hash=hashlib.sha256(s["url"].encode()).hexdigest(),
                        title=s["title"],
                        content=s["excerpt"],
                        content_hash=hashlib.sha256(s["excerpt"].encode()).hexdigest(),
                        language=s["language"],
                        published_at=now,
                        time_quality="verified",
                        raw_metadata={
                            "synthetic": True,
                            "publisher_id": s["source"],
                            "publisher_region": "synthetic",
                            "publisher_country": "UN",
                        },
                    )
                    for s in row["articles"]
                ]
                session.add_all([event, *sources])
                await session.flush()
                session.add_all(
                    [
                        EventNews(
                            event_id=event_id, news_id=s.id, cluster_method="authored_fixture"
                        )
                        for s in sources
                    ]
                )
                session.add(
                    EventRevision(
                        event_id=event_id,
                        evidence_hash="0" * 64,
                        snapshot={
                            "title": event.title,
                            "reporting": [{"news_id": s.id} for s in sources],
                        },
                    )
                )
                articles.extend(sources)
            embeddings = await EmbeddingClient().embed(
                EmbeddingRequest(texts=[s.content for s in articles])
            )
            await store.upsert(
                UpsertRequest(
                    points=[
                        VectorPoint(
                            id=s.id,
                            vector=e.vector,
                            payload={
                                "news_id": s.id,
                                "title": s.title,
                                "source": s.source_name,
                                "url": s.source_url,
                                "published_at": now.isoformat(),
                                "language": s.language,
                                "time_quality": "verified",
                            },
                        )
                        for s, e in zip(articles, embeddings.results, strict=True)
                    ]
                )
            )
            await session.commit()
        finally:
            await store.close()
    print("Seeded 2 authored events, 5 reports and 5 real bge-m3 vectors in fresh isolated stores.")


if __name__ == "__main__":
    asyncio.run(main())
