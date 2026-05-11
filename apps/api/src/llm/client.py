"""生产级异步 LLM 客户端。"""

from __future__ import annotations

import asyncio
import os
import time

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from src.core.logging import get_logger
from src.llm.schema import LLMError, LLMErrorType, LLMRequest, LLMResponse, LLMUsage

logger = get_logger(__name__)


class LLMClient:
    """封装 DeepSeek(OpenAI 兼容) 聊天接口。"""

    def __init__(self) -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        resolved_base_url = os.getenv("LLM_BASE_URL", "").strip()
        resolved_model = os.getenv("LLM_MODEL", "").strip()

        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 缺失，无法初始化 LLMClient")
        if not resolved_base_url:
            raise ValueError("LLM_BASE_URL 缺失，无法初始化 LLMClient")
        if not resolved_model:
            raise ValueError("LLM_MODEL 缺失，无法初始化 LLMClient")

        self._default_model = resolved_model
        self._client = AsyncOpenAI(api_key=api_key, base_url=resolved_base_url, timeout=30.0)

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """调用聊天接口并返回标准化响应。"""
        model = request.model or self._default_model
        started_at = time.perf_counter()
        logger.info(
            "llm_chat_start",
            model=model,
            message_count=len(request.messages),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        max_retries = 3
        for attempt in range(0, max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=model,
                        messages=[message.model_dump() for message in request.messages],
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                    ),
                    timeout=60.0,
                )
                content = response.choices[0].message.content or ""
                usage = LLMUsage(
                    prompt_tokens=(response.usage.prompt_tokens if response.usage else 0),
                    completion_tokens=(response.usage.completion_tokens if response.usage else 0),
                    total_tokens=(response.usage.total_tokens if response.usage else 0),
                )
                finish_reason = response.choices[0].finish_reason or "unknown"
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                logger.info(
                    "llm_chat_success",
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    duration_ms=duration_ms,
                    finish_reason=finish_reason,
                )
                return LLMResponse(
                    content=content,
                    usage=usage,
                    model=response.model or model,
                    finish_reason=finish_reason,
                )
            except Exception as exc:  # noqa: BLE001 - 需统一分类未知异常,防止漏掉新 SDK 错误类型
                error_type = self._classify_error(exc)
                retry_count = attempt + 1
                should_retry = error_type in {LLMErrorType.RATE_LIMIT, LLMErrorType.TIMEOUT}
                if should_retry and attempt < max_retries:
                    wait_seconds = 2**attempt
                    logger.warning(
                        "llm_chat_retry",
                        error_type=error_type.value,
                        attempt=retry_count,
                        wait_seconds=wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                duration_ms = int((time.perf_counter() - started_at) * 1000)
                logger.error(
                    "llm_chat_failed",
                    error_type=error_type.value,
                    retry_count=retry_count,
                    duration_ms=duration_ms,
                )
                raise LLMError(
                    error_type=error_type,
                    original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                    retry_count=retry_count,
                ) from exc

        # 理论上不可达 (循环内每次都 return 或 raise)
        # 防御性编程保证函数签名 -> LLMResponse 永远成立
        raise LLMError(
            error_type=LLMErrorType.UNKNOWN,
            original_error=RuntimeError("chat retry loop exited without return or raise"),
            retry_count=max_retries + 1,
        )

    @staticmethod
    def _classify_error(error: Exception) -> LLMErrorType:
        """将原始异常归类为统一错误类型。"""
        if isinstance(error, (AuthenticationError,)):
            return LLMErrorType.AUTH
        if isinstance(error, (RateLimitError,)):
            return LLMErrorType.RATE_LIMIT
        if isinstance(error, (asyncio.TimeoutError, APITimeoutError)):
            return LLMErrorType.TIMEOUT
        if isinstance(error, (APIConnectionError, APIError)):
            return LLMErrorType.API_ERROR
        return LLMErrorType.UNKNOWN
