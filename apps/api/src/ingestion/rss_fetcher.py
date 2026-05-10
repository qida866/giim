"""RSS 新闻源拉取与解析。

负责从单个 RSS URL 拉取 XML 内容,解析为结构化的新闻列表,
但不负责去重、不负责入库。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from pydantic import BaseModel, Field

from src.core.logging import get_logger

logger = get_logger(__name__)
USER_AGENT = "GIIM-Bot/0.1 (+https://github.com/qida866/giim)"


class RssSource(BaseModel):
    """RSS 源配置。"""

    name: str
    url: str
    language: str


class ParsedNewsItem(BaseModel):
    """解析后的新闻条目。"""

    source_name: str
    source_url: str
    title: str
    content: str
    language: str
    published_at: datetime


class RssFetchResult(BaseModel):
    """单个 RSS 源拉取结果。"""

    source_name: str
    success: bool
    items: list[ParsedNewsItem] = Field(default_factory=list)
    error: str | None = None
    fetched_at: datetime


def _clean_html_text(raw_text: str | None) -> str:
    """清洗 HTML 并返回纯文本。"""
    if not raw_text:
        return ""
    return BeautifulSoup(raw_text, "html.parser").get_text(" ", strip=True).strip()


def _parse_published_at(raw_value: str | None, fallback_dt: datetime) -> datetime:
    """解析发布时间，失败时返回当前 UTC 时间。"""
    if not raw_value:
        return fallback_dt

    try:
        parsed = date_parser.parse(raw_value)
    except (ValueError, TypeError, OverflowError):
        return datetime.now(timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def fetch_rss(source: RssSource) -> RssFetchResult:
    """拉取并解析单个 RSS 源。"""
    fetched_at = datetime.now(timezone.utc)
    logger.info("开始拉取 RSS", source_name=source.name, url=source.url)

    try:
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            response = await client.get(source.url)
            response.raise_for_status()
    except httpx.TimeoutException:
        error_msg = "Timeout after 10s"
        logger.error("拉取 RSS 失败", source_name=source.name, error=error_msg)
        return RssFetchResult(
            source_name=source.name,
            success=False,
            error=error_msg,
            fetched_at=fetched_at,
        )
    except httpx.HTTPStatusError as exc:
        error_msg = f"HTTP {exc.response.status_code}"
        logger.error("拉取 RSS 失败", source_name=source.name, error=error_msg)
        return RssFetchResult(
            source_name=source.name,
            success=False,
            error=error_msg,
            fetched_at=fetched_at,
        )
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        logger.error("拉取 RSS 失败", source_name=source.name, error=error_msg)
        return RssFetchResult(
            source_name=source.name,
            success=False,
            error=error_msg,
            fetched_at=fetched_at,
        )

    parsed_feed = await asyncio.to_thread(feedparser.parse, response.text)

    items: list[ParsedNewsItem] = []
    skipped_count = 0
    for entry in parsed_feed.entries:
        link = str(getattr(entry, "link", "")).strip()
        title = _clean_html_text(getattr(entry, "title", None))
        content_raw = getattr(entry, "summary", None) or getattr(entry, "description", None)
        content = _clean_html_text(content_raw)

        if not link or not title or not content:
            skipped_count += 1
            continue

        published_raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
        published_at = _parse_published_at(published_raw, fetched_at)

        items.append(
            ParsedNewsItem(
                source_name=source.name,
                source_url=link,
                title=title,
                content=content,
                language=source.language,
                published_at=published_at,
            )
        )

    logger.info("解析跳过脏数据", source_name=source.name, skipped_count=skipped_count)
    logger.info("拉取 RSS 成功", source_name=source.name, item_count=len(items))

    return RssFetchResult(
        source_name=source.name,
        success=True,
        items=items,
        fetched_at=fetched_at,
    )


if __name__ == "__main__":
    test_source = RssSource(
        name="BBC News - World",
        url="http://feeds.bbci.co.uk/news/world/rss.xml",
        language="en",
    )

    async def main() -> None:
        result = await fetch_rss(test_source)
        print(f"Success: {result.success}")
        print(f"Items: {len(result.items)}")
        if result.items:
            print(f"First item title: {result.items[0].title}")
            print(f"First item published_at: {result.items[0].published_at}")
        if result.error:
            print(f"Error: {result.error}")

    asyncio.run(main())
