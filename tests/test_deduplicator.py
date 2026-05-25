"""去重器 title_fuzzy 层测试 (savepoint 会话)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingestion.deduplicator import deduplicate_and_insert
from src.ingestion.rss_fetcher import ParsedNewsItem

pytestmark = pytest.mark.asyncio

_LONG_TITLE = "全球科技产业峰会开幕现场报道全文"


def _parsed_item(
    *,
    source_name: str,
    url_suffix: str,
    title: str = _LONG_TITLE,
) -> ParsedNewsItem:
    now = datetime.now(timezone.utc)
    return ParsedNewsItem(
        source_name=source_name,
        source_url=f"http://dedup.test/{url_suffix}",
        title=title,
        content=f"正文内容 {url_suffix}",
        language="zh",
        published_at=now,
    )


async def test_title_fuzzy_dup_skipped(db_session: AsyncSession) -> None:
    """同源同标题跨 URL 应命中 title_fuzzy 去重。"""
    first = _parsed_item(source_name="新华网", url_suffix="day1")
    second = _parsed_item(source_name="新华网", url_suffix="day2")

    stats_first = await deduplicate_and_insert([first], db_session)
    assert stats_first.inserted == 1
    assert stats_first.skipped_title_fuzzy_dup == 0

    stats_second = await deduplicate_and_insert([second], db_session)
    assert stats_second.inserted == 0
    assert stats_second.skipped_title_fuzzy_dup == 1


@pytest.mark.xfail(
    reason="fixture 架构: asyncpg event loop scope 不一致, 见 TODO 48",
)
async def test_cross_source_title_kept(db_session: AsyncSession) -> None:
    """不同源相同标题应各自入库。"""
    item_a = _parsed_item(source_name="新华网", url_suffix="a")
    item_b = _parsed_item(source_name="人民网", url_suffix="b")

    stats = await deduplicate_and_insert([item_a, item_b], db_session)
    assert stats.inserted == 2
    assert stats.skipped_title_fuzzy_dup == 0
