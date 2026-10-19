"""单源采集、条件请求和独立事务；保留可诊断的失败计数。"""

from __future__ import annotations
import time
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.ingestion.deduplicator import deduplicate_and_insert
from src.ingestion.orchestrator_schema import SourceRunStats
from src.ingestion.rss_fetcher import RssSource, fetch_rss
from src.models.operations import OperationalState


async def run_single_source(
    source: RssSource, session_factory: async_sessionmaker[AsyncSession]
) -> SourceRunStats:
    started = time.perf_counter()
    stats = SourceRunStats(source_name=source.name, source_id=source.source_id, fetch_url=source.url, success=False)
    try:
        async with session_factory() as session:
            state = await session.get(
                OperationalState, "source:" + (source.source_id or source.name)
            )
            previous = state.value if state else {}
        validators = {}
        if previous.get("fetch_url") == source.url and previous.get("etag"):
            validators["If-None-Match"] = previous["etag"]
        if previous.get("fetch_url") == source.url and previous.get("last_modified"):
            validators["If-Modified-Since"] = previous["last_modified"]
        fetched = await fetch_rss(source, validators)
        stats.http_status = fetched.http_status
        stats.attempts = fetched.attempts
        stats.items_fetched = len(fetched.items)
        stats.fetched_raw = fetched.fetched_count
        stats.parse_skipped = fetched.skipped_count
        stats.timestamp_unknown = fetched.timestamp_unknown
        stats.latest_published_at = fetched.latest_published_at
        stats.etag = fetched.etag
        stats.last_modified = fetched.last_modified
        stats.not_modified = fetched.not_modified
        if not fetched.success:
            stats.fetch_error = fetched.error
        else:
            try:
                async with session_factory() as session:
                    inserted = await deduplicate_and_insert(fetched.items, session)
                for key in (
                    "inserted",
                    "updated",
                    "skipped_url_dup",
                    "skipped_title_fuzzy_dup",
                    "skipped_content_dup",
                    "failed",
                ):
                    setattr(stats, key, getattr(inserted, key))
                stats.success = True
            except Exception as exc:
                stats.insert_error = type(exc).__name__
    except Exception as exc:
        stats.fetch_error = type(exc).__name__
    stats.duration_ms = (time.perf_counter() - started) * 1000
    return stats
