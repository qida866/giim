"""命令行入口:将 PostgreSQL news 批量向量化并写入 Qdrant。

用法示例:
    docker compose exec api python -m scripts.backfill_embeddings

临时参数(不经 .env.example):
    docker compose exec api -e BACKFILL_LIMIT=10 -e BACKFILL_RESET=true \\
        python -m scripts.backfill_embeddings

编排逻辑见设计草案 Day 5 B v2;本脚本为独立入口。
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

# 让 scripts 目录能 import src.xxx
PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy import func, select

from src.core.logging import get_logger
from src.db.session import AsyncSessionLocal
from src.embedding import EmbeddingClient, EmbeddingRequest
from src.models.news import News
from src.vector_store import QdrantVectorStore, UpsertRequest, VectorPoint

logger = get_logger(__name__)


def _parse_batch_size() -> int:
    """解析 BACKFILL_BATCH_SIZE,须在 1-64 之间。"""
    raw = os.getenv("BACKFILL_BATCH_SIZE", "32").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"BACKFILL_BATCH_SIZE 非法: {raw!r}") from exc
    if value < 1 or value > 64:
        raise ValueError(f"BACKFILL_BATCH_SIZE 须在 1-64 之间,当前为 {value}")
    return value


def _parse_limit() -> int | None:
    """解析 BACKFILL_LIMIT;未设置或空串表示不限制。"""
    raw = os.getenv("BACKFILL_LIMIT")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"BACKFILL_LIMIT 非法: {raw!r}") from exc
    if value <= 0:
        raise ValueError("BACKFILL_LIMIT 必须为正整数")
    return value


def _parse_reset() -> bool:
    """解析 BACKFILL_RESET 是否为 true。"""
    return os.getenv("BACKFILL_RESET", "false").strip().lower() == "true"


async def _delete_qdrant_collection_if_exists() -> None:
    """按与 QdrantVectorStore 同源环境变量删除集合;不存在则忽略 404。"""
    url = os.getenv("QDRANT_URL", "http://qdrant:6333").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip()
    name = os.getenv("QDRANT_COLLECTION_NAME", "news_embeddings").strip()
    kwargs: dict[str, Any] = {"url": url}
    if api_key:
        kwargs["api_key"] = api_key
    client = AsyncQdrantClient(**kwargs)
    try:
        await client.delete_collection(collection_name=name)
    except UnexpectedResponse as exc:
        if exc.status_code != 404:
            raise
    finally:
        await client.close()


def _build_embed_text(news: News) -> str:
    """拼接用于向量化的文本:title + 正文前 2000 字。"""
    title = news.title or ""
    body = news.content or ""
    return f"{title}\n\n{body[:2000]}"


def _news_to_vector_point(news: News, vector: list[float]) -> VectorPoint:
    """将单条新闻与向量转为 VectorPoint。"""
    return VectorPoint(
        id=news.id,
        vector=vector,
        payload={
            "news_id": news.id,
            "title": news.title or "",
            "url": news.source_url,
            "source": news.source_name,
            "published_at": news.published_at.isoformat(),
        },
    )


async def main() -> int:
    """执行回填主流程,返回进程退出码 (0 成功,1 失败)。"""
    try:
        batch_size = _parse_batch_size()
        limit_value = _parse_limit()
        backfill_reset = _parse_reset()
    except ValueError as exc:
        logger.error(
            "backfill_config_invalid",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return 1

    embedder = EmbeddingClient()
    store = QdrantVectorStore()

    if backfill_reset:
        logger.warning(
            "backfill_reset_enabled",
            message="将清空 collection 重建!",
        )
        await _delete_qdrant_collection_if_exists()

    await store.ensure_collection()

    async with AsyncSessionLocal() as session:
        count_stmt = select(func.count()).select_from(News)
        news_count = int((await session.execute(count_stmt)).scalar_one())

        if news_count == 0:
            logger.warning(
                "backfill_no_data",
                message="news 表为空,跳过回填",
            )
            return 0

        effective_total = news_count if limit_value is None else min(news_count, limit_value)

        qdrant_count = await store.count()
        if not backfill_reset and qdrant_count >= news_count and news_count > 0:
            logger.info(
                "backfill_skip",
                qdrant_count=qdrant_count,
                news_count=news_count,
                message="Qdrant 点数已不少于 news 条数,跳过回填",
            )
            return 0

        run_started = time.perf_counter()
        offset = 0
        processed = 0
        batch_idx = 0
        total_batches = math.ceil(effective_total / batch_size) if effective_total > 0 else 0

        while processed < effective_total:
            batch_idx += 1
            this_limit = min(batch_size, effective_total - processed)
            batch_offset = offset

            stmt = (
                select(News)
                .order_by(News.id)
                .limit(this_limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            if not rows:
                logger.error(
                    "backfill_batch_failed",
                    batch_idx=batch_idx,
                    batch_size=this_limit,
                    offset=batch_offset,
                    error_type="RuntimeError",
                    error_message="查询结果为空但尚未处理完计划条数",
                )
                return 1

            texts = [_build_embed_text(n) for n in rows]

            try:
                embed_response = await embedder.embed(
                    EmbeddingRequest(texts=texts, normalize=True),
                )
                if len(embed_response.results) != len(rows):
                    raise RuntimeError(
                        "Embedding 返回条数与输入新闻条数不一致",
                    )
                points = [
                    _news_to_vector_point(news, res.vector)
                    for news, res in zip(rows, embed_response.results, strict=True)
                ]
                await store.upsert(UpsertRequest(points=points))
            except Exception as exc:  # noqa: BLE001 - 批次失败需记录上下文后退出
                logger.error(
                    "backfill_batch_failed",
                    batch_idx=batch_idx,
                    batch_size=this_limit,
                    offset=batch_offset,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                return 1

            processed += len(rows)
            offset += len(rows)

            elapsed = time.perf_counter() - run_started
            if processed > 0 and processed < effective_total:
                eta_seconds = (elapsed / processed) * (effective_total - processed)
            else:
                eta_seconds = None

            logger.info(
                "backfill_batch_progress",
                batch_idx=batch_idx,
                total_batches=total_batches,
                processed=processed,
                total=effective_total,
                eta_seconds=round(eta_seconds, 2) if eta_seconds is not None else None,
                message=f"进度 [{batch_idx}/{total_batches}] 已处理 {processed}/{effective_total}",
            )

        qdrant_count_after = await store.count()
        total_duration_seconds = time.perf_counter() - run_started
        batches = batch_idx
        avg_per_batch_seconds = (
            total_duration_seconds / batches if batches > 0 else 0.0
        )
        logger.info(
            "backfill_completed",
            news_count=news_count,
            effective_total=effective_total,
            qdrant_count_after=qdrant_count_after,
            batches=batches,
            total_duration_seconds=round(total_duration_seconds, 3),
            avg_per_batch_seconds=round(avg_per_batch_seconds, 3),
            message="回填完成",
        )

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
