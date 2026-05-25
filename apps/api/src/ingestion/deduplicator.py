"""新闻去重与入库。

接收 ParsedNewsItem 列表,
- 计算 url_hash、content_hash、title_fuzzy_hash
- 查询数据库识别已存在的(三层去重)
- 批量插入新条目
- 返回详细统计

设计原则:
- 批量查询(IN 语句),避免 N+1
- 批量插入,但单条 IntegrityError 不影响整批
- 全程异步(SQLAlchemy 2.0 async)
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.ingestion.rss_fetcher import ParsedNewsItem
from src.models.news import News

logger = get_logger(__name__)

MIN_TITLE_FUZZY_LEN = 8

_DATE_FRAGMENT_RE = re.compile(
    r"20\d{2}[-/年]\d{1,2}(?:[-/月]\d{1,2})?(?:日)?",
)
_PUNCT_RE = re.compile(
    r"[!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~，。！？；：、「」『』（）【】《》…—·]+",
)


@dataclass(frozen=True)
class _PreparedRow:
    """单条预计算 hash 后的中间结构。"""

    item: ParsedNewsItem
    url_hash: str
    content_hash: str
    title_fuzzy_hash: str | None


class InsertStats(BaseModel):
    """去重与入库统计。"""

    total_received: int
    inserted: int
    skipped_url_dup: int
    skipped_title_fuzzy_dup: int
    skipped_content_dup: int
    failed: int
    failed_urls: list[str] = Field(default_factory=list)
    duration_ms: float


def _fullwidth_to_halfwidth(text: str) -> str:
    """全角 ASCII 与空格转半角。"""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _normalize_title_for_fuzzy(title: str) -> str:
    """标题规范化, 用于跨日重发 fuzzy 去重 (不做简繁转换)。"""
    text = unicodedata.normalize("NFKC", title.strip())
    text = _fullwidth_to_halfwidth(text)
    text = _DATE_FRAGMENT_RE.sub("", text)
    text = _PUNCT_RE.sub(" ", text)
    text = " ".join(text.split())
    return text.strip()


def _compute_title_fuzzy_hash(item: ParsedNewsItem) -> str | None:
    """同源标题 fuzzy hash; 过短标题返回 None 跳过此层。"""
    normalized = _normalize_title_for_fuzzy(item.title)
    if len(normalized) < MIN_TITLE_FUZZY_LEN:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def compute_hashes(item: ParsedNewsItem) -> tuple[str, str, str | None]:
    """计算 (url_hash, content_hash, title_fuzzy_hash)。"""
    url_hash = hashlib.sha256(item.source_url.encode()).hexdigest()
    content_hash = hashlib.sha256((item.title + item.content).encode()).hexdigest()
    title_fuzzy_hash = _compute_title_fuzzy_hash(item)
    return url_hash, content_hash, title_fuzzy_hash


def _filter_for_insert(
    prepared: list[_PreparedRow],
    existing_url_hashes: set[str],
    existing_content_hashes: set[str],
    existing_title_fuzzy_keys: set[tuple[str, str]],
) -> tuple[list[_PreparedRow], int, int, int]:
    """按 url → title_fuzzy → content 过滤; 合并库内与本批次已占用键。"""
    seen_url: set[str] = set(existing_url_hashes)
    seen_content: set[str] = set(existing_content_hashes)
    seen_title_fuzzy: set[tuple[str, str]] = set(existing_title_fuzzy_keys)
    skipped_url_dup = 0
    skipped_title_fuzzy_dup = 0
    skipped_content_dup = 0
    rows_to_insert: list[_PreparedRow] = []
    for p in prepared:
        if p.url_hash in seen_url:
            skipped_url_dup += 1
            continue
        if p.title_fuzzy_hash is not None:
            fuzzy_key = (p.item.source_name, p.title_fuzzy_hash)
            if fuzzy_key in seen_title_fuzzy:
                skipped_title_fuzzy_dup += 1
                continue
        if p.content_hash in seen_content:
            skipped_content_dup += 1
            continue
        rows_to_insert.append(p)
        seen_url.add(p.url_hash)
        if p.title_fuzzy_hash is not None:
            seen_title_fuzzy.add((p.item.source_name, p.title_fuzzy_hash))
        seen_content.add(p.content_hash)
    return rows_to_insert, skipped_url_dup, skipped_title_fuzzy_dup, skipped_content_dup


def _build_news_rows(rows_to_insert: list[_PreparedRow], fetched_at: datetime) -> list[News]:
    """将待插入行转为 News ORM 列表。"""
    out: list[News] = []
    for p in rows_to_insert:
        item = p.item
        out.append(
            News(
                source_name=item.source_name,
                source_url=item.source_url,
                title=item.title,
                content=item.content,
                language=item.language,
                published_at=item.published_at,
                url_hash=p.url_hash,
                content_hash=p.content_hash,
                title_fuzzy_hash=p.title_fuzzy_hash,
                fetched_at=fetched_at,
                raw_metadata={"source": item.source_name, "ingested_via": "rss"},
            )
        )
    return out


async def _fetch_existing_title_fuzzy_keys(
    session: AsyncSession,
    prepared: list[_PreparedRow],
) -> set[tuple[str, str]]:
    """批量查询库内已有 (source_name, title_fuzzy_hash), 忽略 NULL 老数据。"""
    pairs: list[tuple[str, str]] = []
    for p in prepared:
        if p.title_fuzzy_hash is None:
            continue
        key = (p.item.source_name, p.title_fuzzy_hash)
        if key not in pairs:
            pairs.append(key)
    if not pairs:
        return set()
    result = await session.execute(
        select(News.source_name, News.title_fuzzy_hash).where(
            News.title_fuzzy_hash.is_not(None),
            tuple_(News.source_name, News.title_fuzzy_hash).in_(pairs),
        ),
    )
    return {(row[0], row[1]) for row in result.all()}


async def _commit_batch_or_per_row(
    session: AsyncSession,
    news_objs: list[News],
) -> tuple[int, int, list[str]]:
    """整批提交;失败则逐条提交,单条 IntegrityError 记入失败列表。"""
    try:
        session.add_all(news_objs)
        await session.commit()
        return len(news_objs), 0, []
    except SQLAlchemyError:
        await session.rollback()
    inserted = 0
    failed = 0
    failed_urls: list[str] = []
    for obj in news_objs:
        try:
            session.add(obj)
            await session.commit()
            inserted += 1
        except IntegrityError:
            await session.rollback()
            failed += 1
            failed_urls.append(obj.source_url)
        except SQLAlchemyError:
            await session.rollback()
            raise
    return inserted, failed, failed_urls


async def deduplicate_and_insert(
    items: list[ParsedNewsItem],
    session: AsyncSession,
) -> InsertStats:
    """对条目做三层 hash 去重并批量写入数据库。"""
    start_time = time.perf_counter()
    if not items:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info("开始去重", total_received=0)
        return InsertStats(
            total_received=0,
            inserted=0,
            skipped_url_dup=0,
            skipped_title_fuzzy_dup=0,
            skipped_content_dup=0,
            failed=0,
            failed_urls=[],
            duration_ms=duration_ms,
        )
    total_received = len(items)
    logger.info("开始去重", total_received=total_received)
    prepared: list[_PreparedRow] = []
    for item in items:
        uh, ch, tfh = compute_hashes(item)
        prepared.append(
            _PreparedRow(item=item, url_hash=uh, content_hash=ch, title_fuzzy_hash=tfh),
        )
    existing_url_hashes = set(
        (await session.execute(select(News.url_hash).where(News.url_hash.in_([p.url_hash for p in prepared]))))
        .scalars()
        .all()
    )
    existing_content_hashes = set(
        (
            await session.execute(
                select(News.content_hash).where(
                    News.content_hash.in_([p.content_hash for p in prepared]),
                ),
            )
        )
        .scalars()
        .all()
    )
    existing_title_fuzzy_keys = await _fetch_existing_title_fuzzy_keys(session, prepared)
    rows_to_insert, skipped_url_dup, skipped_title_fuzzy_dup, skipped_content_dup = _filter_for_insert(
        prepared,
        existing_url_hashes,
        existing_content_hashes,
        existing_title_fuzzy_keys,
    )
    logger.info(
        "已存在跳过",
        skipped_url_dup=skipped_url_dup,
        skipped_title_fuzzy_dup=skipped_title_fuzzy_dup,
        skipped_content_dup=skipped_content_dup,
    )
    fetched_at = datetime.now(timezone.utc)
    news_objs = _build_news_rows(rows_to_insert, fetched_at)
    if not news_objs:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info("入库成功", inserted=0, duration_ms=round(duration_ms, 1))
        return InsertStats(
            total_received=total_received,
            inserted=0,
            skipped_url_dup=skipped_url_dup,
            skipped_title_fuzzy_dup=skipped_title_fuzzy_dup,
            skipped_content_dup=skipped_content_dup,
            failed=0,
            failed_urls=[],
            duration_ms=duration_ms,
        )
    inserted, failed, failed_urls = await _commit_batch_or_per_row(session, news_objs)
    duration_ms = (time.perf_counter() - start_time) * 1000
    if failed_urls:
        logger.error("入库部分失败", failed=failed, failed_urls=failed_urls)
    logger.info("入库成功", inserted=inserted, duration_ms=round(duration_ms, 1))
    return InsertStats(
        total_received=total_received,
        inserted=inserted,
        skipped_url_dup=skipped_url_dup,
        skipped_title_fuzzy_dup=skipped_title_fuzzy_dup,
        skipped_content_dup=skipped_content_dup,
        failed=failed,
        failed_urls=failed_urls,
        duration_ms=duration_ms,
    )


if __name__ == "__main__":
    """手动测试:从 BBC RSS 拉一批,跑去重+入库。"""
    import asyncio

    from src.db.session import AsyncSessionLocal
    from src.ingestion.rss_fetcher import RssSource, fetch_rss

    async def main() -> None:
        source = RssSource(
            name="BBC News - World",
            url="http://feeds.bbci.co.uk/news/world/rss.xml",
            language="en",
        )
        fetch_result = await fetch_rss(source)
        if not fetch_result.success:
            print(f"Fetch failed: {fetch_result.error}")
            return

        print(f"Fetched {len(fetch_result.items)} items")

        async with AsyncSessionLocal() as session:
            stats = await deduplicate_and_insert(fetch_result.items, session)

        print("=" * 50)
        print(f"Total received:       {stats.total_received}")
        print(f"Inserted:             {stats.inserted}")
        print(f"Skipped url:          {stats.skipped_url_dup}")
        print(f"Skipped title fuzzy:  {stats.skipped_title_fuzzy_dup}")
        print(f"Skipped content:      {stats.skipped_content_dup}")
        print(f"Failed:               {stats.failed}")
        print(f"Duration:             {stats.duration_ms:.1f}ms")
        if stats.failed_urls:
            print(f"Failed URLs: {stats.failed_urls}")

    asyncio.run(main())
