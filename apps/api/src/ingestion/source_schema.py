"""源注册表与解析结果的数据契约。"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class RssSource(BaseModel):
    source_id: str = ""
    name: str
    publisher_id: str = ""
    ownership_group: str = ""
    url: str
    language: str
    country: str = ""
    region: str = ""
    coverage_regions: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=lambda: ["general"])
    source_type: Literal["rss", "usgs_geojson"] = "rss"
    role: Literal["reporting", "official", "aggregator", "analysis"] = "reporting"
    enabled: bool = True
    production_enabled: bool = True
    time_quality: str = "verified"
    max_items: int = Field(default=60, ge=1, le=200)
    poll_minutes: int = Field(default=30, ge=5, le=1440)
    discovery_url: str = ""
    usage_notes: str = "Public feed availability does not establish redistribution rights."
    disabled_reason: str = ""
    validated_at: str | None = None

    def provenance(self) -> dict:
        """总部地域仅表示报道来源，不能当作事件发生地点。"""
        return {
            "source_id": self.source_id,
            "publisher_id": self.publisher_id or self.name,
            "ownership_group": self.ownership_group or self.publisher_id or self.name,
            "publisher_country": self.country,
            "publisher_region": self.region,
            "coverage_regions": self.coverage_regions,
            "source_categories": self.categories,
            "source_role": self.role,
            "source_type": self.source_type,
        }


class ParsedNewsItem(BaseModel):
    source_name: str
    source_url: str
    title: str
    content: str
    language: str
    published_at: datetime | None = None
    time_quality: str = "verified"
    raw_published_at: str | None = None
    metadata: dict = Field(default_factory=dict)


class RssFetchResult(BaseModel):
    source_name: str
    success: bool
    items: list[ParsedNewsItem] = Field(default_factory=list)
    error: str | None = None
    fetched_at: datetime
    fetched_count: int = 0
    skipped_count: int = 0
    timestamp_unknown: int = 0
    http_status: int | None = None
    attempts: int = 0
    latest_published_at: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
