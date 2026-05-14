"""生产级异步 Qdrant 向量存储客户端。"""

from __future__ import annotations

import os
import time
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from src.core.logging import get_logger
from src.vector_store.qdrant_helpers import (
    DISTANCE_MAP,
    classify_qdrant_exception,
    ensure_qdrant_collection,
    scored_points_to_search_results,
)
from src.vector_store.schema import (
    SearchRequest,
    SearchResponse,
    UpsertRequest,
    UpsertResponse,
    VectorStoreError,
    VectorStoreErrorType,
)

logger = get_logger(__name__)


class QdrantVectorStore:
    """封装 Qdrant 的集合管理与向量读写。"""
    def __init__(self) -> None:
        self._url = os.getenv("QDRANT_URL", "http://qdrant:6333").strip()
        self._api_key = os.getenv("QDRANT_API_KEY", "").strip()
        self._collection_name = os.getenv("QDRANT_COLLECTION_NAME", "news_embeddings").strip()
        raw_size = os.getenv("QDRANT_VECTOR_SIZE", "1024").strip()
        raw_distance = os.getenv("QDRANT_DISTANCE", "cosine").strip().lower()

        if not self._url:
            raise ValueError("QDRANT_URL 不能为空")
        if not self._collection_name:
            raise ValueError("QDRANT_COLLECTION_NAME 不能为空")

        try:
            self._vector_size = int(raw_size)
        except ValueError as exc:
            raise ValueError(f"QDRANT_VECTOR_SIZE 非法: {raw_size}") from exc
        if self._vector_size <= 0:
            raise ValueError("QDRANT_VECTOR_SIZE 必须为正整数")

        if raw_distance not in DISTANCE_MAP:
            raise ValueError(
                f"QDRANT_DISTANCE 非法: {raw_distance!r}，仅支持 cosine / euclid / dot",
            )
        self._qdrant_distance = DISTANCE_MAP[raw_distance]

        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        """懒加载 AsyncQdrantClient 单例。"""
        if self._client is None:
            kwargs: dict[str, Any] = {"url": self._url}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = AsyncQdrantClient(**kwargs)
        return self._client

    async def ensure_collection(self) -> None:
        """幂等创建集合；若已存在则校验向量维度与距离度量。"""
        client = await self._get_client()
        await ensure_qdrant_collection(
            client,
            self._collection_name,
            self._vector_size,
            self._qdrant_distance,
        )

    async def upsert(self, request: UpsertRequest) -> UpsertResponse:
        """批量写入或更新向量点。"""
        started_at = time.perf_counter()
        point_count = len(request.points)
        client = await self._get_client()

        for point in request.points:
            if len(point.vector) != self._vector_size:
                invalid = ValueError(
                    f"向量维度 {len(point.vector)} 与期望 {self._vector_size} 不一致",
                )
                raise VectorStoreError(
                    error_type=VectorStoreErrorType.INVALID_VECTOR,
                    original_error=invalid,
                    message=str(invalid),
                    point_count=point_count,
                )

        logger.info("qdrant_upsert_start", point_count=point_count)
        points_sdk = [
            models.PointStruct(id=p.id, vector=p.vector, payload=p.payload)
            for p in request.points
        ]
        try:
            await client.upsert(
                collection_name=self._collection_name,
                points=points_sdk,
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001 - 统一包装为 VectorStoreError
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            error_type = classify_qdrant_exception(exc, default=VectorStoreErrorType.UPSERT)
            logger.error(
                "qdrant_upsert_failed",
                error_type=error_type.value,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            raise VectorStoreError(
                error_type=error_type,
                original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                message=str(exc),
                point_count=point_count,
            ) from exc

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("qdrant_upsert_success", count=point_count, duration_ms=duration_ms)
        return UpsertResponse(count=point_count, duration_ms=duration_ms)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """语义检索，返回相似点列表。"""
        if request.filter_conditions is not None:
            raise NotImplementedError("filter_conditions 待 Day 6+ 实现")

        started_at = time.perf_counter()
        client = await self._get_client()

        if len(request.query_vector) != self._vector_size:
            invalid = ValueError(
                f"查询向量维度 {len(request.query_vector)} 与期望 {self._vector_size} 不一致",
            )
            raise VectorStoreError(
                error_type=VectorStoreErrorType.INVALID_VECTOR,
                original_error=invalid,
                message=str(invalid),
                top_k=request.top_k,
            )

        logger.info("qdrant_search_start", top_k=request.top_k, has_filter=False)
        try:
            response = await client.query_points(
                collection_name=self._collection_name,
                query=list(request.query_vector),
                limit=request.top_k,
                score_threshold=request.score_threshold,
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            error_type = classify_qdrant_exception(exc, default=VectorStoreErrorType.SEARCH)
            logger.error(
                "qdrant_search_failed",
                error_type=error_type.value,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            raise VectorStoreError(
                error_type=error_type,
                original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                message=str(exc),
                top_k=request.top_k,
            ) from exc

        results = scored_points_to_search_results(response.points)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "qdrant_search_success",
            result_count=len(results),
            duration_ms=duration_ms,
        )
        return SearchResponse(results=results, duration_ms=duration_ms)

    async def count(self) -> int:
        """返回集合内点的数量。"""
        client = await self._get_client()
        try:
            result = await client.count(
                collection_name=self._collection_name,
                exact=True,
            )
        except Exception as exc:  # noqa: BLE001
            error_type = classify_qdrant_exception(exc, default=VectorStoreErrorType.UNKNOWN)
            raise VectorStoreError(
                error_type=error_type,
                original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                message=str(exc),
            ) from exc
        return int(result.count)

    async def health(self) -> bool:
        """检查与 Qdrant 的连通性。"""
        try:
            client = await self._get_client()
            await client.get_collections()
        except Exception:  # noqa: BLE001 - 健康检查吞掉异常,仅返回布尔值
            return False
        return True
