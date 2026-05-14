"""Qdrant 客户端内部工具:异常解包、集合参数解析、错误归类与辅助流程。"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from src.core.logging import get_logger
from src.vector_store.schema import SearchResult, VectorStoreError, VectorStoreErrorType

logger = get_logger(__name__)

DISTANCE_MAP: dict[str, models.Distance] = {
    "cosine": models.Distance.COSINE,
    "euclid": models.Distance.EUCLID,
    "dot": models.Distance.DOT,
}


def unwrap_unexpected(error: BaseException) -> UnexpectedResponse | None:
    """从包装异常中取出 UnexpectedResponse。"""
    if isinstance(error, UnexpectedResponse):
        return error
    if isinstance(error, ResponseHandlingException):
        src = error.source
        if isinstance(src, UnexpectedResponse):
            return src
    return None


def is_not_found(error: BaseException) -> bool:
    """判断是否为集合不存在的 HTTP 404。"""
    unwrapped = unwrap_unexpected(error)
    return unwrapped is not None and unwrapped.status_code == 404


def extract_vector_params(info: models.CollectionInfo) -> tuple[int, models.Distance]:
    """从集合信息中解析向量维度与距离度量。"""
    params = info.config.params
    if params is None or params.vectors is None:
        msg = "集合配置缺少 vectors 参数"
        raise ValueError(msg)

    vectors = params.vectors
    if isinstance(vectors, models.VectorParams):
        return vectors.size, vectors.distance
    if isinstance(vectors, dict):
        if not vectors:
            msg = "集合 vectors 字典为空"
            raise ValueError(msg)
        first = next(iter(vectors.values()))
        return first.size, first.distance
    msg = f"无法解析 vectors 配置类型: {type(vectors).__name__}"
    raise ValueError(msg)


def distance_label(distance: models.Distance) -> str:
    """将 Distance 枚举转为可读字符串。"""
    if hasattr(distance, "name"):
        return str(distance.name)
    return str(distance)


def classify_qdrant_exception(
    error: BaseException,
    *,
    default: VectorStoreErrorType,
) -> VectorStoreErrorType:
    """将底层异常归类为 VectorStoreErrorType。"""
    if isinstance(error, asyncio.TimeoutError):
        return VectorStoreErrorType.CONNECTION

    unwrapped = unwrap_unexpected(error)
    if unwrapped is not None:
        code = unwrapped.status_code
        if code == 404:
            return VectorStoreErrorType.COLLECTION_NOT_FOUND
        if code is not None and 500 <= code < 600:
            return VectorStoreErrorType.CONNECTION
        if code == 400:
            body = b""
            try:
                body = unwrapped.content
            except Exception:  # noqa: BLE001 - 仅用于分类,忽略解析失败
                pass
            lowered = body.decode(errors="replace").lower()
            if "dimension" in lowered or ("vector" in lowered and "size" in lowered):
                return VectorStoreErrorType.INVALID_VECTOR
            return default

    lowered_msg = str(error).lower()
    if "dimension" in lowered_msg or "vector size" in lowered_msg:
        return VectorStoreErrorType.INVALID_VECTOR

    return default


def scored_points_to_search_results(scored_points: Iterable[Any]) -> list[SearchResult]:
    """将 Qdrant ScoredPoint 列表转为 SearchResult 列表。"""
    results: list[SearchResult] = []
    for scored in scored_points:
        point_id = scored.id  # 接受 int 或 str
        payload_raw = scored.payload
        if isinstance(payload_raw, dict):
            payload = dict(payload_raw)
        else:
            payload = {}
        results.append(
            SearchResult(id=point_id, score=float(scored.score), payload=payload),
        )
    return results


async def ensure_qdrant_collection(
    client: AsyncQdrantClient,
    collection_name: str,
    vector_size: int,
    qdrant_distance: models.Distance,
) -> None:
    """幂等创建集合并校验已存在集合的配置。"""
    try:
        info = await client.get_collection(collection_name=collection_name)
    except Exception as exc:  # noqa: BLE001 - 需统一解析 HTTP 与包装异常
        if is_not_found(exc):
            logger.info(
                "qdrant_collection_creating",
                collection_name=collection_name,
                vector_size=vector_size,
                distance=distance_label(qdrant_distance),
            )
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=qdrant_distance,
                ),
            )
            logger.info(
                "qdrant_collection_created",
                collection_name=collection_name,
                vector_size=vector_size,
                distance=distance_label(qdrant_distance),
            )
            return

        error_type = classify_qdrant_exception(exc, default=VectorStoreErrorType.UNKNOWN)
        raise VectorStoreError(
            error_type=error_type,
            original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
            message=str(exc),
        ) from exc

    actual_size, actual_distance = extract_vector_params(info)
    if actual_size != vector_size or actual_distance != qdrant_distance:
        mismatch_msg = (
            f"collection '{collection_name}' exists but config mismatch: "
            f"expected size={vector_size} distance={distance_label(qdrant_distance)}, "
            f"got size={actual_size} distance={distance_label(actual_distance)}"
        )
        logger.error(
            "qdrant_collection_config_mismatch",
            collection_name=collection_name,
            expected_size=vector_size,
            expected_distance=distance_label(qdrant_distance),
            actual_size=actual_size,
            actual_distance=distance_label(actual_distance),
        )
        raise VectorStoreError(
            error_type=VectorStoreErrorType.COLLECTION_CONFIG_MISMATCH,
            original_error=ValueError(mismatch_msg),
            message=mismatch_msg,
        )

    logger.info("qdrant_collection_already_exists", collection_name=collection_name)

