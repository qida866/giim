"""通过 ID 和内容指纹对账；仅增量编码可信数据，历史向量保留。"""

from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.news import News
from src.embedding import EmbeddingClient, EmbeddingRequest
from src.vector_store import QdrantVectorStore, VectorPoint, UpsertRequest

EMBED_VERSION = "bge-m3:title-body2000:v1"


def embed_text(news: News) -> str:
    return f"{news.title or ''}\n\n{(news.content or '')[:2000]}"


def fingerprint(news: News) -> str:
    return hashlib.sha256((EMBED_VERSION + "\n" + embed_text(news)).encode()).hexdigest()


def eligible(news: News) -> bool:
    return (
        news.time_quality == "verified"
        and news.published_at is not None
        and not news.source_url.startswith("https://example.com/")
    )


def payload(news: News) -> dict:
    return {
        "news_id": news.id,
        "title": news.title,
        "url": news.source_url,
        "source": news.source_name,
        "language": news.language,
        "published_at": news.published_at.isoformat() if news.published_at else None,
        "fingerprint": fingerprint(news),
        "embedding_version": EMBED_VERSION,
        "time_quality": news.time_quality,
    }


async def audit_vectors(session: AsyncSession, store: QdrantVectorStore) -> tuple[dict, list[News]]:
    rows = list((await session.scalars(select(News).order_by(News.id))).all())
    by_id = {n.id: n for n in rows}
    client = await store._get_client()
    exists = await client.collection_exists(store._collection_name)
    points = {}
    offset = None
    while exists:
        batch, offset = await client.scroll(
            collection_name=store._collection_name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.update({p.id: p.payload or {} for p in batch})
        if offset is None:
            break
    missing = []
    stale = []
    metadata = []
    legacy = []
    for news in rows:
        p = points.get(news.id)
        if not eligible(news):
            if p is not None and "fingerprint" not in p:
                legacy.append(news.id)
            elif p is not None and any(p.get(k) != v for k, v in payload(news).items()):
                metadata.append(news.id)
            continue
        if p is None:
            missing.append(news.id)
        elif p.get("fingerprint") != fingerprint(news):
            stale.append(news.id)
        elif any(p.get(k) != v for k, v in payload(news).items()):
            metadata.append(news.id)
    report = {
        "missing": missing,
        "stale": stale,
        "metadata": metadata,
        "orphans": [str(i) for i in points if i not in by_id],
        "historical_unversioned": legacy,
        "eligible": sum(eligible(n) for n in rows),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return report, [by_id[i] for i in missing + stale]


async def reconcile_vectors(
    session: AsyncSession, store: QdrantVectorStore, embedder: EmbeddingClient
) -> dict:
    await store.ensure_collection()
    report, pending = await audit_vectors(session, store)
    for offset in range(0, len(pending), 16):
        batch = pending[offset : offset + 16]
        encoded = await embedder.embed(EmbeddingRequest(texts=[embed_text(n) for n in batch]))
        await store.upsert(
            UpsertRequest(
                points=[
                    VectorPoint(id=n.id, vector=r.vector, payload=payload(n))
                    for n, r in zip(batch, encoded.results, strict=True)
                ]
            )
        )
    client = await store._get_client()
    for news_id in report["metadata"]:
        news = await session.get(News, news_id)
        await client.set_payload(
            collection_name=store._collection_name,
            payload=payload(news),
            points=[news_id],
            wait=True,
        )
    report["embedded"] = len(pending)
    report["metadata_updated"] = len(report["metadata"])
    return report
