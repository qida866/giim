"""向量存储层的数据模型与错误定义。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VectorPoint(BaseModel):
    """单个向量点。"""

    model_config = ConfigDict(extra="forbid")

    id: int | str = Field(
        description="Qdrant point ID。整数 (推荐用 DB 主键) 或 UUID 字符串",
    )
    vector: list[float]
    payload: dict[str, Any] = Field(default_factory=dict)


class UpsertRequest(BaseModel):
    """批量写入向量点的请求。"""

    model_config = ConfigDict(extra="forbid")

    points: list[VectorPoint] = Field(min_length=1, max_length=256)


class UpsertResponse(BaseModel):
    """批量写入的响应。"""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class SearchRequest(BaseModel):
    """语义向量搜索请求。"""

    model_config = ConfigDict(extra="forbid")

    query_vector: list[float]
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "假设向量已 L2 归一化 (例如 bge-m3 + normalize=True),使 cosine 相似度落在 [0, 1]"
        ),
    )
    filter_conditions: dict[str, Any] | None = None


class SearchResult(BaseModel):
    """单条搜索结果。"""

    model_config = ConfigDict(extra="forbid")

    id: int | str = Field(
        description="Qdrant point ID。整数 (推荐用 DB 主键) 或 UUID 字符串",
    )
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """语义搜索响应。"""

    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult]
    duration_ms: int = Field(ge=0)


class VectorStoreErrorType(str, Enum):
    """向量存储错误类型枚举。"""

    CONNECTION = "CONNECTION"
    COLLECTION_NOT_FOUND = "COLLECTION_NOT_FOUND"
    COLLECTION_CONFIG_MISMATCH = "COLLECTION_CONFIG_MISMATCH"
    INVALID_VECTOR = "INVALID_VECTOR"
    UPSERT = "UPSERT"
    SEARCH = "SEARCH"
    UNKNOWN = "UNKNOWN"


class VectorStoreError(Exception):
    """向量存储调用异常。"""

    def __init__(
        self,
        error_type: VectorStoreErrorType,
        original_error: Exception,
        message: str | None = None,
        *,
        point_count: int | None = None,
        top_k: int | None = None,
    ) -> None:
        self.error_type = error_type
        self.original_error = original_error
        self.message = message
        self.point_count = point_count
        self.top_k = top_k
        super().__init__(f"{error_type.value}: {message or original_error}")

