"""同源有界去重，保留不同发布者证据；串行化同源并发写入。"""

from __future__ import annotations
import hashlib
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from sqlalchemy import select, text, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.ingestion.rss_fetcher import ParsedNewsItem
from src.models.news import News

MIN_TITLE_FUZZY_LEN = 8
DEDUP_HOURS = 36


class InsertStats(BaseModel):
    total_received: int
    inserted: int = 0
    updated: int = 0
    skipped_url_dup: int = 0
    skipped_title_fuzzy_dup: int = 0
    skipped_content_dup: int = 0
    failed: int = 0
    failed_urls: list[str] = Field(default_factory=list)
    duration_ms: float = 0


def _normalize_title_for_fuzzy(title: str) -> str:
    # 保留日期，避免每日简报被永久压成一条；中英文标点与大小写统一。
    value = unicodedata.normalize("NFKC", title).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def _compute_title_fuzzy_hash(item: ParsedNewsItem) -> str | None:
    value = _normalize_title_for_fuzzy(item.title)
    return hashlib.sha256(value.encode()).hexdigest() if len(value) >= MIN_TITLE_FUZZY_LEN else None


def compute_hashes(item: ParsedNewsItem) -> tuple[str, str, str | None]:
    return (
        hashlib.sha256(item.source_url.encode()).hexdigest(),
        hashlib.sha256((item.title + item.content).encode()).hexdigest(),
        _compute_title_fuzzy_hash(item),
    )


async def deduplicate_and_insert(items: list[ParsedNewsItem], session: AsyncSession) -> InsertStats:
    started = time.perf_counter()
    stats = InsertStats(total_received=len(items))
    now = datetime.now(timezone.utc)
    # 排序取锁防多源批次死锁；锁和提交在同一事务。
    for source in sorted({i.source_name for i in items}):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:source,0))"),
            {"source": "giim-ingest:" + source},
        )
    for item in items:
        uh, ch, th = compute_hashes(item)
        existing = await session.scalar(select(News).where(News.source_url == item.source_url))
        if existing:
            if (
                existing.source_name == item.source_name
                and existing.time_quality == "verified"
                and item.time_quality == "verified"
            ):
                previous = existing.raw_metadata or {}
                if existing.content_hash != ch:
                    history = previous.get("revisions", [])[-4:] + [
                        {
                            "content_hash": existing.content_hash,
                            "title": existing.title,
                            "content": existing.content[:5000],
                            "observed_at": now.isoformat(),
                        }
                    ]
                    existing.title = item.title
                    existing.content = item.content
                    existing.content_hash = ch
                    existing.title_fuzzy_hash = th
                    existing.raw_metadata = {
                        **previous,
                        **item.metadata,
                        "revisions": history,
                        "last_observed_revision_at": now.isoformat(),
                    }
                    stats.updated += 1
                else:
                    existing.raw_metadata = {**previous, **item.metadata}
                    stats.skipped_url_dup += 1
            else:
                stats.skipped_url_dup += 1
            continue
        stamp = item.published_at or now
        timestamp = News.published_at if item.published_at else News.fetched_at
        near = (
            await session.scalars(
                select(News).where(
                    News.source_name == item.source_name,
                    timestamp >= stamp - timedelta(hours=DEDUP_HOURS),
                    timestamp <= stamp + timedelta(hours=DEDUP_HOURS),
                    or_(News.title_fuzzy_hash == th if th else False, News.content_hash == ch),
                )
            )
        ).all()
        # 官方观测 ID 比通用震情标题更具体；不同 ID 不执行标题/正文折叠。
        official_id = item.metadata.get("official_event_id")
        if official_id:
            near = [n for n in near if (n.raw_metadata or {}).get("official_event_id") == official_id]
        if th and any(n.title_fuzzy_hash == th for n in near):
            stats.skipped_title_fuzzy_dup += 1
            continue
        if any(n.content_hash == ch for n in near):
            stats.skipped_content_dup += 1
            continue
        session.add(
            News(
                source_name=item.source_name,
                source_url=item.source_url,
                title=item.title,
                content=item.content,
                language=item.language,
                published_at=item.published_at,
                time_quality=item.time_quality if item.published_at else "unknown",
                fetched_at=now,
                url_hash=uh,
                content_hash=ch,
                title_fuzzy_hash=th,
                raw_metadata={
                    **item.metadata,
                    "ingested_via": item.metadata.get("source_type", "rss"),
                    "raw_published_at": item.raw_published_at,
                    "dedup_version": 3,
                },
            )
        )
        await session.flush()
        stats.inserted += 1
    await session.commit()
    stats.duration_ms = (time.perf_counter() - started) * 1000
    return stats
