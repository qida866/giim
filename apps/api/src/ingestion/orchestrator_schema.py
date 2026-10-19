"""编排层数据结构与会话无关的默认 RSS 源列表。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


from src.ingestion.registry import load_registry

DEFAULT_SOURCES = load_registry()


class SourceRunStats(BaseModel):
    """单源采集统计。"""

    source_name: str
    source_id: str = ""
    fetch_url: str = ""
    updated: int = 0
    attempts: int = 0
    latest_published_at: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    success: bool
    fetch_error: str | None = None
    insert_error: str | None = None
    items_fetched: int = 0
    parse_skipped: int = 0
    fetched_raw: int = 0
    timestamp_unknown: int = 0
    skipped_title_fuzzy_dup: int = 0
    http_status: int | None = None
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
