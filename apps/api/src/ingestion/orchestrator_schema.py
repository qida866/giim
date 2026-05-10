"""编排层数据结构与会话无关的默认 RSS 源列表。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.ingestion.rss_fetcher import RssSource

DEFAULT_SOURCES: list[RssSource] = [
    RssSource(
        name="BBC News - World",
        url="http://feeds.bbci.co.uk/news/world/rss.xml",
        language="en",
    ),
    RssSource(
        name="Hacker News - Frontpage",
        url="https://hnrss.org/frontpage",
        language="en",
    ),
    RssSource(
        name="The Verge",
        url="https://www.theverge.com/rss/index.xml",
        language="en",
    ),
    RssSource(
        name="新华网时政",
        url="http://www.xinhuanet.com/politics/news_politics.xml",
        language="zh",
    ),
    RssSource(
        name="人民网时政",
        url="http://www.people.com.cn/rss/politics.xml",
        language="zh",
    ),
]


class SourceRunStats(BaseModel):
    """单源采集统计。"""

    source_name: str
    success: bool
    fetch_error: str | None = None
    insert_error: str | None = None
    items_fetched: int = 0
    parse_skipped: int = 0
    inserted: int = 0
    skipped_url_dup: int = 0
    skipped_content_dup: int = 0
    failed: int = 0
    duration_ms: float = 0.0


class IngestionRunStats(BaseModel):
    """整次采集运行的统计。"""

    started_at: datetime
    finished_at: datetime
    total_duration_ms: float
    sources_total: int
    sources_succeeded: int
    sources_failed: int
    items_fetched_total: int
    items_inserted_total: int
    items_skipped_total: int
    items_failed_total: int
    per_source: list[SourceRunStats] = Field(default_factory=list)
