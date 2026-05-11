"""生产级异步 Embedding 客户端。"""

from __future__ import annotations

import asyncio
import os
import threading
import time

from sentence_transformers import SentenceTransformer

from src.core.logging import get_logger
from src.embedding.schema import (
    EmbeddingBatchResponse,
    EmbeddingError,
    EmbeddingErrorType,
    EmbeddingRequest,
    EmbeddingResult,
)

logger = get_logger(__name__)


class EmbeddingClient:
    """封装 sentence-transformers 的文本向量化能力。"""

    def __init__(self) -> None:
        self._model_name = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3").strip()
        self._cache_dir = os.getenv("EMBEDDING_CACHE_DIR", "/app/.cache/huggingface").strip()
        self._device = os.getenv("EMBEDDING_DEVICE", "cpu").strip().lower()

        if not self._model_name:
            raise ValueError("EMBEDDING_MODEL_NAME 不能为空")
        if not self._cache_dir:
            raise ValueError("EMBEDDING_CACHE_DIR 不能为空")
        if self._device not in {"cpu", "cuda", "mps"}:
            raise ValueError("EMBEDDING_DEVICE 仅支持 cpu/cuda/mps")

        self._model: SentenceTransformer | None = None
        self._model_lock = threading.Lock()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatchResponse:
        """执行批量文本向量化并返回标准化响应。"""
        started_at = time.perf_counter()
        batch_size = len(request.texts)

        try:
            texts = self._validate_texts(request.texts)
            self._ensure_model_loaded()

            total_chars = sum(len(text) for text in texts)
            logger.info(
                "embedding_encode_start",
                model_name=self._model_name,
                batch_size=batch_size,
                total_chars=total_chars,
                normalize=request.normalize,
            )

            vectors = await asyncio.to_thread(self._encode_sync, texts, request.normalize)
            if len(vectors) != len(texts):
                raise RuntimeError("encode 返回向量数量与输入文本数量不一致")

            results = [
                EmbeddingResult(
                    text=text,
                    vector=vector,
                    dimension=len(vector),
                )
                for text, vector in zip(texts, vectors, strict=True)
            ]

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "embedding_encode_success",
                model_name=self._model_name,
                duration_ms=duration_ms,
                vector_count=len(results),
            )
            return EmbeddingBatchResponse(
                results=results,
                duration_ms=duration_ms,
                model_name=self._model_name,
            )
        except EmbeddingError:
            # 已在 _ensure_model_loaded / _validate_texts 内部记录日志
            raise
        except Exception as exc:  # noqa: BLE001 - 统一兜底未知异常,避免错误类型漏网
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            error_type = self._classify_error(exc)
            logger.error(
                "embedding_encode_failed",
                model_name=self._model_name,
                error_type=error_type.value,
                error_message=str(exc),
                batch_size=batch_size,
                duration_ms=duration_ms,
            )
            raise EmbeddingError(
                error_type=error_type,
                original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                batch_size=batch_size,
            ) from exc

    def _ensure_model_loaded(self) -> None:
        """确保模型已加载，首次调用时执行懒加载。"""
        if self._model is not None:
            return

        with self._model_lock:
            if self._model is not None:
                return

            load_started_at = time.perf_counter()
            logger.info(
                "embedding_model_loading",
                model_name=self._model_name,
                cache_dir=self._cache_dir,
            )

            try:
                self._model = SentenceTransformer(
                    self._model_name,
                    cache_folder=self._cache_dir,
                    device=self._device,
                )
                load_duration_ms = int((time.perf_counter() - load_started_at) * 1000)
                logger.info(
                    "embedding_model_loaded",
                    model_name=self._model_name,
                    load_duration_ms=load_duration_ms,
                )
            except Exception as exc:  # noqa: BLE001 - 需要统一包装模型加载异常
                load_duration_ms = int((time.perf_counter() - load_started_at) * 1000)
                logger.error(
                    "embedding_model_load_failed",
                    model_name=self._model_name,
                    cache_dir=self._cache_dir,
                    error_type=EmbeddingErrorType.MODEL_LOAD.value,
                    error_message=str(exc),
                    load_duration_ms=load_duration_ms,
                )
                raise EmbeddingError(
                    error_type=EmbeddingErrorType.MODEL_LOAD,
                    original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                    batch_size=None,
                ) from exc

    def _encode_sync(self, texts: list[str], normalize: bool) -> list[list[float]]:
        """在同步线程中执行模型 encode。"""
        if self._model is None:
            raise RuntimeError("模型尚未加载，无法执行 encode")

        vectors = self._model.encode(
            texts,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    @staticmethod
    def _validate_texts(texts: list[str]) -> list[str]:
        """执行业务级输入校验并返回清洗后的文本。"""
        validated_texts: list[str] = []
        batch_size = len(texts)

        for raw_text in texts:
            stripped = raw_text.strip()
            if not stripped:
                original_error = ValueError("texts 中包含空字符串或仅空白字符")
                logger.error(
                    "embedding_encode_failed",
                    error_type=EmbeddingErrorType.INVALID_INPUT.value,
                    error_message=str(original_error),
                    batch_size=batch_size,
                )
                raise EmbeddingError(
                    error_type=EmbeddingErrorType.INVALID_INPUT,
                    original_error=original_error,
                    batch_size=batch_size,
                )
            if len(stripped) > 8192:
                original_error = ValueError("单条文本长度超过 8192 字符上限")
                logger.error(
                    "embedding_encode_failed",
                    error_type=EmbeddingErrorType.INVALID_INPUT.value,
                    error_message=str(original_error),
                    batch_size=batch_size,
                )
                raise EmbeddingError(
                    error_type=EmbeddingErrorType.INVALID_INPUT,
                    original_error=original_error,
                    batch_size=batch_size,
                )
            validated_texts.append(stripped)

        return validated_texts

    @staticmethod
    def _classify_error(error: Exception) -> EmbeddingErrorType:
        """将原始异常归类为统一错误类型。"""
        if isinstance(error, ValueError):
            return EmbeddingErrorType.INVALID_INPUT
        if isinstance(error, (RuntimeError, OSError)):
            return EmbeddingErrorType.ENCODE
        return EmbeddingErrorType.UNKNOWN
