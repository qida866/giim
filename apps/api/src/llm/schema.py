"""LLM 调用层的数据模型与错误定义。"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    """单条 LLM 消息。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """LLM 聊天请求参数。"""

    model_config = ConfigDict(extra="forbid")

    messages: list[LLMMessage] = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, gt=0, le=8192)
    model: str | None = None


class LLMUsage(BaseModel):
    """LLM Token 用量统计。"""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMResponse(BaseModel):
    """LLM 聊天响应结果。"""

    model_config = ConfigDict(extra="forbid")

    content: str
    usage: LLMUsage
    model: str
    finish_reason: str


class LLMErrorType(str, Enum):
    """LLM 错误类型枚举。"""

    AUTH = "AUTH"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    API_ERROR = "API_ERROR"
    UNKNOWN = "UNKNOWN"


class LLMError(Exception):
    """LLM 调用异常。

    retry_count=1 表示首次失败未重试，retry_count=4 表示首次+3次重试都失败。
    """

    def __init__(
        self,
        error_type: LLMErrorType,
        original_error: Exception,
        retry_count: int = 1,
    ) -> None:
        self.error_type = error_type
        self.original_error = original_error
        self.retry_count = retry_count
        super().__init__(f"{error_type.value}: {original_error}")
