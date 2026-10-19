"""以事件为主的检索，同时保留匹配的原始报道。"""

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.deps import get_db
from src.models.event import Event, EventNews
from src.models.news import News
from src.embedding import EmbeddingClient
from src.vector_store import QdrantVectorStore
from src.routers.search import (
    SearchAPIRequest,
    semantic_search,
    get_embedding_client,
    get_vector_store,
)
from src.utils.events import _event_to_response

router = APIRouter()


@router.post("/search/events")
async def event_search(
    body: SearchAPIRequest,
    session: AsyncSession = Depends(get_db),
    embedder: EmbeddingClient = Depends(get_embedding_client),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> dict:
    found = await semantic_search(body, session, embedder, store)
    ordered = list(dict.fromkeys(eid for hit in found.results for eid in hit.event_ids))
    events = {
        str(e.id): e
        for e in (
            await session.scalars(
                select(Event).where(
                    Event.id.in_([uuid.UUID(eid) for eid in ordered]), Event.status == "active"
                )
            )
        ).all()
    }
    reporting = (
        await session.execute(
            select(EventNews.event_id, News.source_name, News.language)
            .join(News, News.id == EventNews.news_id)
            .where(EventNews.event_id.in_([e.id for e in events.values()]))
        )
    ).all()
    results = []
    for eid in ordered:
        if eid not in events:
            continue
        event = events[eid]
        sources = sorted({name for key, name, _ in reporting if key == event.id})
        languages = sorted({lang for key, _, lang in reporting if key == event.id})
        results.append(
            _event_to_response(
                len(results) + 1, event, len(sources), sources, languages
            ).model_dump(mode="json")
        )
    return {
        "query": body.query,
        "events": results,
        "reports": [hit.model_dump(exclude={"score"}) for hit in found.results],
        "total_events": len(results),
        "total_reports": found.total,
        "duration_ms": found.duration_ms,
        "ranking_basis": "Relevance follows the best matching reporting; AI summary availability and publisher count do not override search relevance.",
    }
