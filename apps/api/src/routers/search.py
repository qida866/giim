"""语义搜索 HTTP 路由:查询文本向量化后在 Qdrant 中检索。"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.embedding import EmbeddingClient, EmbeddingError, EmbeddingRequest
from src.vector_store import QdrantVectorStore, SearchRequest, SearchResult, VectorStoreError

router = APIRouter()


class SearchAPIRequest(BaseModel):
    """语义搜索 API 请求体。"""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, Field(min_length=1, max_length=500)]
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
    embedder: EmbeddingClient = Depends(get_embedding_client),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> SearchAPIResponse:
    """将查询文本向量化后在 Qdrant 中语义检索。"""
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
                score_threshold=body.score_threshold,
            ),
        )
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"向量检索失败: {exc.error_type.value}",
        ) from exc

    hits = [_search_hit_from_result(r) for r in search_out.results]
    duration_ms = int((time.perf_counter() - started) * 1000)

    return SearchAPIResponse(
        query=body.query,
        results=hits,
        total=len(hits),
        duration_ms=duration_ms,
    )
