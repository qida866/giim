"""事件响应模型，定义今日 Top 事件接口的输出结构。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventResponse(BaseModel):
    """单条事件响应项。"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    rank: int
    title: str
    summary: str | None
    impact_score: float
    impact_factors: dict | None
    event_type: str | None
    stars: str
    event_type_label: str
    first_seen_at: datetime
    last_updated_at: datetime
    duration_str: str
    news_count: int
    sources_count: int


class TodayEventsResponse(BaseModel):
    """今日 Top 事件列表响应。"""

    model_config = ConfigDict(extra="forbid")

    events: list[EventResponse]
    total_events: int
    total_news: int
    total_sources: int
    generated_at: datetime
