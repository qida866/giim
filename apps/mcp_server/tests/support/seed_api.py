"""仅用于全新隔离测试栈；不是 MCP 工具，不可在已有数据库运行。"""

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from src.db.session import AsyncSessionLocal
from src.models.event import Event, EventNews
from src.models.news import News
from src.models.event_revision import EventRevision
from src.embedding import EmbeddingClient, EmbeddingRequest
from src.vector_store import QdrantVectorStore, UpsertRequest, VectorPoint


async def main() -> None:
    if os.getenv("GIIM_TASK2_FIXTURE_ALLOW") != "isolated-empty-test-stack":
        raise RuntimeError("Explicit isolated test-stack guard required")
    now = datetime.now(timezone.utc)
    event_id = UUID("00000000-0000-0000-0000-000000000001")
    examples = [
        ("en", "The synthetic AI laboratory opened on Tuesday with 24 research desks."),
        ("zh", "合成示例：人工智能实验室于周二开放，设有24个研究席位。"),
        (
            "es",
            "El laboratorio sintético de inteligencia artificial abrió el martes con 24 puestos.",
        ),
    ]
    async with AsyncSessionLocal() as session:
        if await session.scalar(select(func.count()).select_from(News)):
            raise RuntimeError("Refusing to seed any nonempty database")
        if await session.scalar(select(func.count()).select_from(Event)):
            raise RuntimeError("Refusing to seed any nonempty event store")
        articles = []
        for index, (language, excerpt) in enumerate(examples, 1):
            url = f"https://demo.example.org/api-fixture/{index}"
            article = News(
                id=600000 + index,
                source_name="Authored Demo " + language,
                source_url=url,
                url_hash=hashlib.sha256(url.encode()).hexdigest(),
                title="Synthetic AI laboratory opens",
                content=excerpt,
                content_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
                language=language,
                published_at=now,
                time_quality="verified",
                raw_metadata={
                    "synthetic": True,
                    "publisher_id": "task2-demo-" + language,
                    "publisher_region": "synthetic",
                    "publisher_country": "UN",
                },
            )
            articles.append(article)
        event = Event(
            id=event_id,
            title="Synthetic AI laboratory opens",
            summary="Authored test fixture.",
            news_count=3,
            first_seen_at=now,
            last_updated_at=now,
            impact_score=0.7,
            status="active",
            provenance={
                "mode": "synthetic",
                "current_support_ids": [a.id for a in articles],
                "evidence_ids": [a.id for a in articles],
            },
        )
        session.add_all(articles + [event])
        await session.flush()
        session.add_all(
            [
                EventNews(event_id=event_id, news_id=a.id, cluster_method="authored_fixture")
                for a in articles
            ]
        )
        session.add(
            EventRevision(
                event_id=event_id,
                evidence_hash="0" * 64,
                snapshot={"title": event.title, "reporting": [{"news_id": a.id} for a in articles]},
            )
        )
        embedder = EmbeddingClient()
        embeddings = await embedder.embed(EmbeddingRequest(texts=[a.content for a in articles]))
        store = QdrantVectorStore()
        try:
            await store.ensure_collection()
            if await store.count() != 0:
                raise RuntimeError("Refusing to seed a nonempty vector collection")
            await store.upsert(
                UpsertRequest(
                    points=[
                        VectorPoint(
                            id=a.id,
                            vector=e.vector,
                            payload={
                                "news_id": a.id,
                                "title": a.title,
                                "source": a.source_name,
                                "url": a.source_url,
                                "published_at": now.isoformat(),
                                "language": a.language,
                                "time_quality": "verified",
                            },
                        )
                        for a, e in zip(articles, embeddings.results, strict=True)
                    ]
                )
            )
            await session.commit()
        finally:
            await store.close()
        print(
            "Seeded 1 authored event, 3 articles and 3 bge-m3 vectors in isolated empty test stores."
        )


if __name__ == "__main__":
    asyncio.run(main())
