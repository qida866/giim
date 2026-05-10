"""新闻采集编排器: 多源 RSS 拉取 + 去重入库。

并发 asyncio.gather(return_exceptions=True)、逐源独立 AsyncSession、
完整统计。默认源与 Pydantic 模型见 `orchestrator_schema`。
单源 fetch+入库流程见 `single_source`。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger
from src.ingestion.orchestrator_schema import (
    DEFAULT_SOURCES,
    IngestionRunStats,
    SourceRunStats,
)
from src.ingestion.rss_fetcher import RssSource
from src.ingestion.single_source import run_single_source as _run_single_source

logger = get_logger(__name__)


async def run_ingestion(
    sources: list[RssSource] | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> IngestionRunStats:
    """并发拉取多个源,聚合统计。"""
    if sources is None:
        sources = DEFAULT_SOURCES
    if session_factory is None:
        from src.db.session import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    started_at = datetime.now(timezone.utc)
    run_t0 = time.perf_counter()
    logger.info("采集运行开始", sources_total=len(sources))
    tasks = [_run_single_source(src, session_factory) for src in sources]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    per_source: list[SourceRunStats] = []
    for src, res in zip(sources, raw_results, strict=True):
        if isinstance(res, SourceRunStats):
            per_source.append(res)
        else:
            per_source.append(
                SourceRunStats(
                    source_name=src.name,
                    success=False,
                    fetch_error=str(res),
                    duration_ms=0.0,
                )
            )
    finished_at = datetime.now(timezone.utc)
    total_duration_ms = (time.perf_counter() - run_t0) * 1000
    sources_total = len(per_source)
    sources_succeeded = sum(1 for s in per_source if s.success)
    sources_failed = sources_total - sources_succeeded
    items_fetched_total = sum(s.items_fetched for s in per_source)
    items_inserted_total = sum(s.inserted for s in per_source)
    items_skipped_total = sum(s.skipped_url_dup + s.skipped_content_dup for s in per_source)
    items_failed_total = sum(s.failed for s in per_source)
    logger.info(
        "采集运行结束",
        sources_total=sources_total,
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        items_inserted_total=items_inserted_total,
        total_duration_ms=round(total_duration_ms, 1),
    )
    return IngestionRunStats(
        started_at=started_at,
        finished_at=finished_at,
        total_duration_ms=total_duration_ms,
        sources_total=sources_total,
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        items_fetched_total=items_fetched_total,
        items_inserted_total=items_inserted_total,
        items_skipped_total=items_skipped_total,
        items_failed_total=items_failed_total,
        per_source=per_source,
    )


if __name__ == "__main__":
    """命令行手动测试:跑一次完整采集。"""

    async def main() -> None:
        stats = await run_ingestion()
        print("=" * 70)
        print("INGESTION RUN SUMMARY")
        print("=" * 70)
        print(f"Started:           {stats.started_at}")
        print(f"Finished:          {stats.finished_at}")
        print(f"Duration:          {stats.total_duration_ms:.1f}ms")
        print()
        print(f"Sources total:     {stats.sources_total}")
        print(f"Sources succeeded: {stats.sources_succeeded}")
        print(f"Sources failed:    {stats.sources_failed}")
        print()
        print(f"Items fetched:     {stats.items_fetched_total}")
        print(f"Items inserted:    {stats.items_inserted_total}")
        print(f"Items skipped:     {stats.items_skipped_total}")
        print(f"Items failed:      {stats.items_failed_total}")
        print()
        print("PER-SOURCE BREAKDOWN")
        print("-" * 70)
        for src_stats in stats.per_source:
            status = "✓" if src_stats.success else "✗"
            print(f"{status} {src_stats.source_name}")
            print(
                f"   duration={src_stats.duration_ms:.1f}ms  "
                f"fetched={src_stats.items_fetched}  "
                f"inserted={src_stats.inserted}  "
                f"skipped_url={src_stats.skipped_url_dup}  "
                f"skipped_content={src_stats.skipped_content_dup}"
            )
            if src_stats.fetch_error:
                print(f"   fetch_error: {src_stats.fetch_error}")
            if src_stats.insert_error:
                print(f"   insert_error: {src_stats.insert_error}")
        print("=" * 70)

    asyncio.run(main())
