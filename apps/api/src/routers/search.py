"""语义搜索 HTTP 路由:查询文本向量化后在 Qdrant 中检索。"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.deps import get_db
from src.models.news import News
from src.models.event import Event, EventNews

from src.embedding import EmbeddingClient, EmbeddingError, EmbeddingRequest
from src.vector_store import QdrantVectorStore, SearchRequest, SearchResult, VectorStoreError

router = APIRouter()


class SearchAPIRequest(BaseModel):
    """语义搜索 API 请求体。"""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, Field(min_length=1, max_length=500)]
    hours: int = Field(default=168, ge=1, le=720)
    top_k: int = Field(default=10, ge=1, le=50)
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "可选最低相似度;假设向量已 L2 归一化 (例如 bge-m3 + normalize=True),"
            "cosine 相似度落在 [0, 1]"
        ),
    )


class SearchHit(BaseModel):
    """单条检索命中,面向 API 展平 payload。"""

    model_config = ConfigDict(extra="forbid")

    news_id: int
    title: str
    url: str
    source: str
    published_at: str
    score: float
    language: str = ""
    event_ids: list[str] = Field(default_factory=list)


class SearchAPIResponse(BaseModel):
    """语义搜索 API 响应。"""

    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[SearchHit]
    total: int
    duration_ms: int


def get_embedding_client(request: Request) -> EmbeddingClient:
    """从应用状态注入 EmbeddingClient。"""
    return request.app.state.embedding_client


def get_vector_store(request: Request) -> QdrantVectorStore:
    """从应用状态注入 QdrantVectorStore。"""
    return request.app.state.vector_store


def _search_hit_from_result(result: SearchResult) -> SearchHit:
    """将向量层 SearchResult 转为 API SearchHit。"""
    payload = result.payload
    raw_news_id = payload.get("news_id", result.id)
    try:
        news_id = int(raw_news_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="向量点 payload 缺少或非法的 news_id",
        ) from exc

    title = str(payload.get("title", ""))
    url = str(payload.get("url", ""))
    source = str(payload.get("source", ""))
    published_at = str(payload.get("published_at", ""))

    return SearchHit(
        news_id=news_id,
        title=title,
        url=url,
        source=source,
        published_at=published_at,
        score=float(result.score),
    )


@router.post("/search", response_model=SearchAPIResponse)
async def semantic_search(
    body: SearchAPIRequest,
    session: AsyncSession = Depends(get_db),
    embedder: EmbeddingClient = Depends(get_embedding_client),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> SearchAPIResponse:
    """将查询文本向量化后在 Qdrant 中语义检索。"""
    if not body.query.strip():
        raise HTTPException(422, "Query must not be blank")
    started = time.perf_counter()
    try:
        embed_out = await embedder.embed(
            EmbeddingRequest(texts=[body.query.strip()], normalize=True),
        )
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"向量化失败: {exc.error_type.value}",
        ) from exc

    if not embed_out.results:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="向量化未返回结果",
        )
    query_vector = embed_out.results[0].vector

    try:
        search_out = await store.search(
            SearchRequest(
                query_vector=query_vector,
                top_k=body.top_k,
                filter_conditions={
                    "must": [
                        {"key": "time_quality", "match": {"value": "verified"}},
                        {
                            "key": "published_at",
                            "range": {
                                "gte": (
                                    datetime.now(timezone.utc) - timedelta(hours=body.hours)
                                ).isoformat(),
                                "lte": datetime.now(timezone.utc).isoformat(),
                            },
                        },
                    ]
                },
                score_threshold=body.score_threshold,
            ),
        )
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"向量检索失败: {exc.error_type.value}",
        ) from exc

    ids = [int(r.id) for r in search_out.results if str(r.id).isdigit()]
    rows = list(
        (
            await session.scalars(
                select(News).where(
                    News.id.in_(ids),
                    News.time_quality == "verified",
                    News.published_at >= datetime.now(timezone.utc) - timedelta(hours=body.hours),
                    News.published_at <= datetime.now(timezone.utc),
                )
            )
        ).all()
    )
    by_id = {n.id: n for n in rows}
    links = (
        await session.execute(
            select(EventNews.news_id, EventNews.event_id)
            .join(Event, Event.id == EventNews.event_id)
            .where(EventNews.news_id.in_(ids), Event.status == "active")
        )
    ).all()
    event_ids = {}
    for nid, eid in links:
        event_ids.setdefault(nid, []).append(str(eid))
    hits = []
    for result in search_out.results:
        n = by_id.get(result.id)
        if n is None:
            continue
        hits.append(
            SearchHit(
                news_id=n.id,
                title=n.title,
                url=n.source_url,
                source=n.source_name,
                published_at=n.published_at.isoformat(),
                score=result.score,
                language=n.language,
                event_ids=event_ids.get(n.id, []),
            )
        )
        if len(hits) >= body.top_k:
            break
    duration_ms = int((time.perf_counter() - started) * 1000)

    return SearchAPIResponse(
        query=body.query,
        results=hits,
        total=len(hits),
        duration_ms=duration_ms,
    )
