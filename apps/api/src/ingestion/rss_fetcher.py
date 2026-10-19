"""RSS 拉取：重试、可追溯的时间、解析计数，不伪造发布时间。"""

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from src.core.logging import get_logger

logger = get_logger(__name__)
USER_AGENT = "GIIM-Bot/0.2 (+https://github.com/qida866/giim)"

from src.ingestion.source_schema import RssSource, ParsedNewsItem, RssFetchResult
from src.ingestion.safe_http import get_public


def _clean_html_text(raw_text: str | None) -> str:
    return BeautifulSoup(raw_text or "", "html.parser").get_text(" ", strip=True).strip()


def _parse_published_at(raw_value: str | None, now: datetime) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = date_parser.parse(raw_value)
        if parsed.tzinfo is None:
            return None
        parsed = parsed.astimezone(timezone.utc)
        if parsed > now + timedelta(hours=1) or parsed.year < 1990:
            return None
        return parsed
    except (ValueError, TypeError, OverflowError):
        return None


def parse_feed(text: str, source: RssSource, now: datetime) -> RssFetchResult:
    feed = feedparser.parse(text)
    result = RssFetchResult(
        source_name=source.name, success=True, fetched_at=now, fetched_count=len(feed.entries)
    )
    if not getattr(feed, "version", ""):
        result.success = False
        result.error = "InvalidFeed: response is not a usable RSS/Atom feed"
    for entry in feed.entries:
        link = str(getattr(entry, "link", "")).strip()
        title = _clean_html_text(getattr(entry, "title", None))
        full = getattr(entry, "content", [])
        raw = (
            getattr(entry, "summary", None)
            or getattr(entry, "description", None)
            or (full[0].get("value") if full else None)
        )
        content = _clean_html_text(raw)[:5000]
        if not link.startswith(("http://", "https://")) or not title or len(link) > 2048:
            result.skipped_count += 1
            continue
        # 标题本身也是证据；没有正文不再无声丢弃。
        raw_date = getattr(entry, "published", None) or dict(entry).get("updated")
        published = _parse_published_at(raw_date, now)
        if published is None:
            result.timestamp_unknown += 1
        result.items.append(
            ParsedNewsItem(
                source_name=source.name,
                source_url=link,
                title=title[:500],
                content=content,
                language=source.language,
                published_at=published,
                time_quality=source.time_quality if published else "unknown",
                raw_published_at=raw_date,
                metadata={
                    **source.provenance(),
                    "byline": _clean_html_text(getattr(entry, "author", ""))[:200],
                    "source_updated_at": dict(entry).get("updated"),
                },
            )
        )
    result.items.sort(
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    result.latest_published_at = max(
        (n.published_at for n in result.items if n.published_at), default=None
    )
    result.items = result.items[: source.max_items]
    return result


async def fetch_rss(source: RssSource, validators: dict | None = None) -> RssFetchResult:
    now = datetime.now(timezone.utc)
    result = RssFetchResult(source_name=source.name, success=False, fetched_at=now)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20, connect=8),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    ) as client:
        for attempt in range(1, 4):
            try:
                response = await get_public(client, source.url, validators)
                result.http_status = response.status_code
                if response.status_code == 304:
                    result.success = True
                    result.not_modified = True
                    result.attempts = attempt
                    break
                if source.source_type == "usgs_geojson":
                    from src.ingestion.usgs import parse_usgs

                    result = parse_usgs(response.json(), source, now)
                else:
                    result = await asyncio.to_thread(parse_feed, response.text, source, now)
                result.etag = response.headers.get("etag")
                result.last_modified = response.headers.get("last-modified")
                result.http_status = response.status_code
                result.attempts = attempt
                break
            except (httpx.HTTPError, OSError, ValueError) as exc:
                result.error = type(exc).__name__
                if isinstance(exc,httpx.HTTPStatusError):result.http_status=exc.response.status_code
                result.attempts = attempt
                retryable = (
                    (exc.response.status_code in (429, 500, 502, 503, 504))
                    if isinstance(exc, httpx.HTTPStatusError)
                    else not isinstance(exc, ValueError)
                )
                if not retryable or attempt == 3:
                    break
                await asyncio.sleep(attempt)
    logger.info(
        "rss_fetch",
        source=source.name,
        success=result.success,
        error=result.error,
        raw=result.fetched_count,
        parsed=len(result.items),
        skipped=result.skipped_count,
        unknown_time=result.timestamp_unknown,
        attempts=result.attempts,
    )
    return result
