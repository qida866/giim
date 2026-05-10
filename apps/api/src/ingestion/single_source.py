"""单源采集: fetch_rss + 独立会话下去重入库。"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger
from src.ingestion.deduplicator import deduplicate_and_insert
from src.ingestion.orchestrator_schema import SourceRunStats
from src.ingestion.rss_fetcher import RssSource, fetch_rss

logger = get_logger(__name__)


async def run_single_source(
    source: RssSource,
    session_factory: async_sessionmaker[AsyncSession],
) -> SourceRunStats:
    """fetch → 独立 session 下去重入库; 异常均转为 SourceRunStats。"""
    t0 = time.perf_counter()
    logger.info("单源采集开始", source_name=source.name)
    try:
        fetch_result = await fetch_rss(source)
        if not fetch_result.success:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "单源采集结束",
                source_name=source.name,
                success=False,
                fetch_error=fetch_result.error,
                duration_ms=round(duration_ms, 1),
            )
            return SourceRunStats(
                source_name=source.name,
                success=False,
                fetch_error=fetch_result.error,
                duration_ms=duration_ms,
            )
        items_fetched = len(fetch_result.items)
        try:
            async with session_factory() as session:
                insert_stats = await deduplicate_and_insert(fetch_result.items, session)
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.error(
                "单源入库失败",
                source_name=source.name,
                error=str(exc),
                duration_ms=round(duration_ms, 1),
            )
            return SourceRunStats(
                source_name=source.name,
                success=False,
                insert_error=str(exc),
                items_fetched=items_fetched,
                duration_ms=duration_ms,
            )
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "单源采集结束",
            source_name=source.name,
            success=True,
            items_fetched=items_fetched,
            inserted=insert_stats.inserted,
            skipped_url_dup=insert_stats.skipped_url_dup,
            skipped_content_dup=insert_stats.skipped_content_dup,
            failed=insert_stats.failed,
            duration_ms=round(duration_ms, 1),
        )
        return SourceRunStats(
            source_name=source.name,
            success=True,
            items_fetched=items_fetched,
            parse_skipped=0,
            inserted=insert_stats.inserted,
            skipped_url_dup=insert_stats.skipped_url_dup,
            skipped_content_dup=insert_stats.skipped_content_dup,
            failed=insert_stats.failed,
            duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "单源采集异常",
            source_name=source.name,
            error=str(exc),
            duration_ms=round(duration_ms, 1),
        )
        return SourceRunStats(
            source_name=source.name,
            success=False,
            fetch_error=str(exc),
            duration_ms=duration_ms,
        )
