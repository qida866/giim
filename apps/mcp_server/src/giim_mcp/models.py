"""工具输出契约；未知数据显式保留为空。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Window = Literal["24h", "3d", "7d"]
HOURS = {"24h": 24, "3d": 72, "7d": 168}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventCard(Contract):
    id: UUID
    title: str = Field(max_length=2000)
    summary: str | None = Field(default=None, max_length=2000)
    first_seen: str | None = None
    last_updated: str | None = None
    sources_count: int | None = Field(default=None, ge=0)
    languages: list[str] = Field(default_factory=list)
    evidence_status: str | None = None
    relevance_score: float | None = None


class Source(Contract):
    article_id: UUID
    event_id: UUID
    publisher: str | None = None
    url: str | None = None
    published_at: str | None = None
    language: str | None = None
    title: str | None = None
    excerpt: str | None = None
    current_support: bool | None = None
    excerpt_policy: str = "withheld"


class Listing(Contract):
    kind: Literal["listing"] = "listing"
    events: list[EventCard]
    sources: list[Source] = Field(default_factory=list)
    ranking_basis: str | None = None
    language_filter_scope: str | None = None


class Revision(Contract):
    recorded_at: str | None = None
    origin_event_id: UUID | None = None
    title: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)


class Detail(Contract):
    kind: Literal["detail"] = "detail"
    event: EventCard
    status: str | None = None
    articles: list[Source]
    total_articles: int | None = None
    evidence_ids: list[UUID] | None = None
    llm_review_status: str | None = None
    revisions: list[Revision] = Field(default_factory=list)


class Coverage(Contract):
    kind: Literal["coverage"] = "coverage"
    observed_at: str | None = None
    window_hours: int = 24
    observed_languages: list[str]
    observed_publishers: int | None = None
    current_articles: int | None = None
    supported_languages: int | None = None
    indexed_articles: int | None = None
    tracked_events: int | None = None
    by_region: dict[str, int] = Field(default_factory=dict)
    by_language: dict[str, int] | None = None
    by_publisher: dict[str, int] | None = None
    unsupported: list[str]
    basis: str


class Readiness(Contract):
    kind: Literal["readiness"] = "readiness"
    api_status: str
    search_ready: bool | None
    database: bool | None = None
    vectors: bool | None = None
    model_loaded: bool | None = None
    note: str


class ToolError(Contract):
    code: Literal[
        "not_found",
        "invalid_request",
        "rate_limited",
        "unavailable",
        "timeout",
        "malformed_response",
        "response_too_large",
    ]
    message: str
    retryable: bool = False


class Envelope(Contract):
    ok: bool = True
    data: Listing | Detail | Coverage | Readiness | None = None
    error: ToolError | None = None
    truncated: bool = False
