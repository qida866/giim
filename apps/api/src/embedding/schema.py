"""Embedding 调用层的数据模型与错误定义。"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


EmbeddingText = Annotated[str, Field(max_length=8192)]


class EmbeddingRequest(BaseModel):
    """Embedding 批量请求参数。"""

    model_config = ConfigDict(extra="forbid")

    texts: list[EmbeddingText] = Field(min_length=1, max_length=64)
    normalize: bool = True


class EmbeddingResult(BaseModel):
    """单条文本的向量化结果。"""

    model_config = ConfigDict(extra="forbid")

    text: str
    vector: list[float]
    dimension: int


class EmbeddingBatchResponse(BaseModel):
    """Embedding 批量响应结果。"""

    model_config = ConfigDict(extra="forbid")

    results: list[EmbeddingResult]
    duration_ms: int
    model_name: str


class EmbeddingErrorType(str, Enum):
    """Embedding 错误类型枚举。"""

    MODEL_LOAD = "MODEL_LOAD"
    ENCODE = "ENCODE"
    INVALID_INPUT = "INVALID_INPUT"
    UNKNOWN = "UNKNOWN"


class EmbeddingError(Exception):
    """Embedding 调用异常。"""

    def __init__(
        self,
        error_type: EmbeddingErrorType,
        original_error: Exception,
        message: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.error_type = error_type
        self.original_error = original_error
        self.message = message
        self.batch_size = batch_size
        super().__init__(f"{error_type.value}: {message or original_error}")
